"""
PIC16-like VM skeleton with core opcode execution.

This is not yet a complete MCU emulator, but it provides:
- deterministic step loop
- instruction decode/execute table for core operations
- status flags and simple stack semantics
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .hex_runtime import ProgramImage


class VMRuntimeError(RuntimeError):
    """Raised for VM execution errors."""


@dataclass
class VMConfig:
    target: str = "pic16f"
    max_steps_per_cycle: int = 2000
    ram_size: int = 512
    stack_depth: int = 8


@dataclass
class VMState:
    pc: int = 0
    wreg: int = 0
    status_z: int = 0
    status_c: int = 0
    status_dc: int = 0
    cycles: int = 0
    halted: bool = False
    ram: list[int] = field(default_factory=list)
    stack: list[int] = field(default_factory=list)
    last_opcode: int = 0


@dataclass
class StepResult:
    executed: int
    halted: bool
    pc: int
    wreg: int
    z: int
    c: int
    last_opcode: int
    debug: dict | None = None

    def to_dict(self) -> dict:
        d = {
            "executed": self.executed,
            "halted": self.halted,
            "pc": self.pc,
            "wreg": self.wreg,
            "z": self.z,
            "c": self.c,
            "lastOpcode": self.last_opcode,
        }
        if self.debug is not None:
            d["debug"] = self.debug
        return d


class Pic16VM:
    """
    Core PIC16-like emulator for LDmicro workloads.
    """

    PORT_ADDRS = frozenset({0x05, 0x06, 0x07, 0x08, 0x09})
    TRIS_ADDRS = frozenset({0x85, 0x86, 0x87, 0x88, 0x89})
    # PIC16F877 program memory is 8K words (13-bit PC).
    PC_MASK = 0x1FFF
    INDF_HOP_LIMIT = 8

    def __init__(self, image: ProgramImage, config: VMConfig | None = None):
        self.image = image
        self.config = config or VMConfig()
        self.words = image.to_word_view(2, little_endian=True)
        self.state = VMState(ram=[0] * self.config.ram_size)
        self._ext_pins: dict[int, int] = {p: 0 for p in self.PORT_ADDRS}
        self._init_pic_sfr_defaults()

    def _init_pic_sfr_defaults(self):
        """Reset-style defaults for PIC16F877-style I/O (TRIS = all inputs)."""
        for ta in self.TRIS_ADDRS:
            ca = self._canon_addr(ta)
            if ca < len(self.state.ram):
                self.state.ram[ca] = 0xFF
        # ADCON1 = all-digital I/O (many HEX builds never touch it; 0x00 leaves PORTA analog).
        adca = self._canon_addr(0x9F)
        if adca < len(self.state.ram):
            self.state.ram[adca] = 0x07

    def reset(self):
        self.state = VMState(ram=[0] * self.config.ram_size)
        self._ext_pins = {p: 0 for p in self.PORT_ADDRS}
        self._init_pic_sfr_defaults()

    def strobe_ldmicro_scan_tick(self):
        """
        Many LDmicro PIC HEX files spin on PIR1 (file 0x0C) until a peripheral interrupt
        flag sets each scan. Without Timer2/CCP emulation, raise PIR1 bit 2 once per
        simulator cycle so one ``PlcCycle``-equivalent pass can run (matches BTFSS 0x0C,2
        patterns in generated code).
        """
        ca = self._canon_addr(0x0C)
        if ca < len(self.state.ram):
            self.state.ram[ca] = (self.state.ram[ca] | 0x04) & 0xFF

    @staticmethod
    def _canon_addr(addr: int) -> int:
        """
        Canonicalize mirrored PIC16 SFR addresses across banks.
        Keeps core mirrors coherent (STATUS/PCL/FSR/INTCON/PCLATH).
        """
        a = addr & 0x1FF
        low = a & 0x7F
        if low in (0x02, 0x03, 0x04, 0x0A, 0x0B):  # PCL, STATUS, FSR, PCLATH, INTCON
            return low
        return a

    def _tris_byte_for_port(self, port_addr: int) -> int:
        tris_addr = port_addr + 0x80
        ca = self._canon_addr(tris_addr % self.config.ram_size)
        return self.state.ram[ca] & 0xFF if ca < len(self.state.ram) else 0xFF

    def _read_port_combined(self, port_addr: int) -> int:
        """PORT read: pin levels on inputs, latch on outputs (TRIS 1 = input)."""
        ca = self._canon_addr(port_addr % self.config.ram_size)
        tris = self._tris_byte_for_port(port_addr)
        latch = self.state.ram[ca] & 0xFF if ca < len(self.state.ram) else 0
        pins = self._ext_pins.get(port_addr, 0) & 0xFF
        return (pins & tris) | (latch & ((~tris) & 0xFF))

    def _write_port_latch(self, port_addr: int, value: int):
        """PORT write: only bits configured as outputs update the latch."""
        ca = self._canon_addr(port_addr % self.config.ram_size)
        tris = self._tris_byte_for_port(port_addr)
        latch = self.state.ram[ca] & 0xFF if ca < len(self.state.ram) else 0
        v = value & 0xFF
        new_latch = (latch & tris) | (v & ((~tris) & 0xFF))
        self.state.ram[ca] = new_latch

    def set_external_pin(self, port_addr: int, bit: int, level: int):
        """Drive external pin level seen when that bit is an input (TRIS=1)."""
        port_addr &= 0xFF
        if port_addr not in self.PORT_ADDRS:
            return
        b = self._ext_pins.get(port_addr, 0) & 0xFF
        if level:
            b |= 1 << bit
        else:
            b &= ~(1 << bit) & 0xFF
        self._ext_pins[port_addr] = b

    def read_port_latch_raw(self, port_addr: int) -> int:
        ca = self._canon_addr(port_addr % self.config.ram_size)
        return self.state.ram[ca] & 0xFF if ca < len(self.state.ram) else 0

    def get_output_drive(self, port_addr: int, bit: int) -> int:
        """1 if this pin is an output and latch bit is high."""
        tris = self._tris_byte_for_port(port_addr)
        if (tris >> bit) & 1:
            return 0
        latch = self.read_port_latch_raw(port_addr)
        return 1 if (latch >> bit) & 1 else 0

    def get_debug_snapshot(self) -> dict:
        return {
            "pc": self.state.pc,
            "wreg": self.state.wreg,
            "status": self.read_ram(0x03),
            "pcl": self.read_ram(0x02),
            "PORTA": self._read_port_combined(0x05),
            "PORTB": self._read_port_combined(0x06),
            "PORTC": self._read_port_combined(0x07),
            "PORTD": self._read_port_combined(0x08),
            "PORTE": self._read_port_combined(0x09),
            "latchA": self.read_port_latch_raw(0x05),
            "latchB": self.read_port_latch_raw(0x06),
            "latchC": self.read_port_latch_raw(0x07),
            "latchD": self.read_port_latch_raw(0x08),
            "latchE": self.read_port_latch_raw(0x09),
            "TRISA": self._tris_byte_for_port(0x05),
            "TRISB": self._tris_byte_for_port(0x06),
            "TRISC": self._tris_byte_for_port(0x07),
            "TRISD": self._tris_byte_for_port(0x08),
            "TRISE": self._tris_byte_for_port(0x09),
            "extA": self._ext_pins.get(0x05, 0),
            "extB": self._ext_pins.get(0x06, 0),
            "extD": self._ext_pins.get(0x08, 0),
        }

    def read_ram(self, addr: int) -> int:
        ca = self._canon_addr(addr % self.config.ram_size)
        hops = 0
        while (ca & 0x7F) == 0 and hops < self.INDF_HOP_LIMIT:
            ca = self._indirect_target()
            hops += 1
        if (ca & 0x7F) == 0:
            return 0
        if ca in self.PORT_ADDRS:
            return self._read_port_combined(ca)
        return self.state.ram[ca] & 0xFF

    def write_ram(self, addr: int, value: int):
        ca = self._canon_addr(addr % self.config.ram_size)
        hops = 0
        while (ca & 0x7F) == 0 and hops < self.INDF_HOP_LIMIT:
            ca = self._indirect_target()
            hops += 1
        if (ca & 0x7F) == 0:
            return
        if ca in self.PORT_ADDRS:
            self._write_port_latch(ca, value)
            return
        self.state.ram[ca] = value & 0xFF

    def _status(self) -> int:
        return self.state.ram[0x03] & 0xFF

    def _indirect_target(self) -> int:
        """Effective address for INDF access (FSR + STATUS IRP)."""
        fsr = self.state.ram[0x04] & 0xFF
        irp = (self._status() >> 7) & 1
        return self._canon_addr((irp << 8) | fsr)

    def _goto_dest(self, k_low11: int) -> int:
        """Combine PCLATH<4:3> with 11-bit opcode field (PIC16 mid-range)."""
        pclath = self.state.ram[0x0A] & 0xFF
        upper = (pclath & 0x18) << 8
        return (upper | (k_low11 & 0x07FF)) & self.PC_MASK

    def _bump_pc(self, delta: int = 1):
        self.state.pc = (self.state.pc + delta) & self.PC_MASK

    def _resolve_f(self, f: int) -> int:
        """
        Resolve banked file-register address for PIC16-style core.
        f is 7-bit from instruction; bank comes from STATUS<6:5> (RP1:RP0).
        """
        f &= 0x7F
        bank = (self._status() >> 5) & 0x03
        return self._canon_addr((bank << 7) | f)

    def fetch(self) -> int:
        return self.words.get(self.state.pc, 0x0000) & 0xFFFF

    def step(self, budget: int | None = None) -> StepResult:
        limit = budget if budget is not None else self.config.max_steps_per_cycle
        if limit <= 0:
            return StepResult(
                0, self.state.halted, self.state.pc, self.state.wreg,
                self.state.status_z, self.state.status_c, self.state.last_opcode,
                self.get_debug_snapshot(),
            )

        executed = 0
        while executed < limit and not self.state.halted:
            op = self.fetch()
            self.state.last_opcode = op
            self._exec(op)
            # Keep PCL coherent for code that reads it.
            if 0x02 < len(self.state.ram):
                self.state.ram[0x02] = self.state.pc & 0xFF
            executed += 1
            self.state.cycles += 1

        dbg = self.get_debug_snapshot()
        return StepResult(
            executed=executed,
            halted=self.state.halted,
            pc=self.state.pc,
            wreg=self.state.wreg,
            z=self.state.status_z,
            c=self.state.status_c,
            last_opcode=self.state.last_opcode,
            debug=dbg,
        )

    def _set_z(self, value: int):
        self.state.status_z = 1 if (value & 0xFF) == 0 else 0

    def _set_c(self, value: int):
        self.state.status_c = 1 if value else 0

    def _sync_status_to_ram(self):
        status = self.read_ram(0x03)
        status = (status & ~(1 << 2)) | ((self.state.status_z & 1) << 2)
        status = (status & ~(1 << 0)) | (self.state.status_c & 1)
        self.write_ram(0x03, status)

    def _refresh_flags_from_ram(self):
        status = self.read_ram(0x03)
        self.state.status_z = 1 if (status & (1 << 2)) else 0
        self.state.status_c = 1 if (status & 1) else 0

    def _exec(self, op: int):
        # nop
        if op == 0x0000:
            self._bump_pc()
            return

        # movlw k : 0x30kk
        if (op & 0x3F00) == 0x3000:
            k = op & 0x00FF
            self.state.wreg = k
            self._bump_pc()
            return

        # movwf f : 0x0080 | f
        if (op & 0x3F80) == 0x0080:
            f = op & 0x007F
            self.write_ram(self._resolve_f(f), self.state.wreg)
            self._bump_pc()
            return

        # incf / decf
        if (op & 0x3F00) in (0x0A00, 0x0300):
            f = op & 0x007F
            d = (op >> 7) & 0x1
            fa = self._resolve_f(f)
            val = self.read_ram(fa)
            out = (val + 1) & 0xFF if (op & 0x3F00) == 0x0A00 else (val - 1) & 0xFF
            self._set_z(out)
            if d == 0:
                self.state.wreg = out
            else:
                self.write_ram(fa, out)
            self._bump_pc()
            return

        # decfsz / incfsz
        if (op & 0x3F00) in (0x0B00, 0x0F00):
            f = op & 0x007F
            d = (op >> 7) & 0x1
            fa = self._resolve_f(f)
            val = self.read_ram(fa)
            out = (val - 1) & 0xFF if (op & 0x3F00) == 0x0B00 else (val + 1) & 0xFF
            if d == 0:
                self.state.wreg = out
            else:
                self.write_ram(fa, out)
            # Skip next instruction when result is zero.
            self._bump_pc(2 if out == 0 else 1)
            return

        # movf f,d : 0x0800 format
        if (op & 0x3F00) == 0x0800:
            f = op & 0x007F
            d = (op >> 7) & 0x1
            fa = self._resolve_f(f)
            val = self.read_ram(fa)
            self._set_z(val)
            if d == 0:
                self.state.wreg = val
            else:
                self.write_ram(fa, val)
            self._bump_pc()
            return

        # clrf f : 0x0180 | f
        if (op & 0x3F80) == 0x0180:
            f = op & 0x007F
            self.write_ram(self._resolve_f(f), 0)
            self._set_z(0)
            self._bump_pc()
            return

        # bsf f,b : 0x1400
        if (op & 0x3C00) == 0x1400:
            f = op & 0x007F
            b = (op >> 7) & 0x7
            fa = self._resolve_f(f)
            self.write_ram(fa, self.read_ram(fa) | (1 << b))
            self._bump_pc()
            return

        # bcf f,b : 0x1000
        if (op & 0x3C00) == 0x1000:
            f = op & 0x007F
            b = (op >> 7) & 0x7
            fa = self._resolve_f(f)
            self.write_ram(fa, self.read_ram(fa) & ~(1 << b))
            self._bump_pc()
            return

        # btfsc f,b : 0x1800
        if (op & 0x3C00) == 0x1800:
            f = op & 0x007F
            b = (op >> 7) & 0x7
            bit_set = 1 if (self.read_ram(self._resolve_f(f)) & (1 << b)) else 0
            self._bump_pc(2 if bit_set == 0 else 1)
            return

        # btfss f,b : 0x1C00
        if (op & 0x3C00) == 0x1C00:
            f = op & 0x007F
            b = (op >> 7) & 0x7
            bit_set = 1 if (self.read_ram(self._resolve_f(f)) & (1 << b)) else 0
            self._bump_pc(2 if bit_set == 1 else 1)
            return

        # addwf f,d : 0x0700 class
        if (op & 0x3F00) == 0x0700:
            f = op & 0x007F
            d = (op >> 7) & 0x1
            fa = self._resolve_f(f)
            a = self.read_ram(fa)
            res = a + self.state.wreg
            self._set_c(1 if res > 0xFF else 0)
            out = res & 0xFF
            self._set_z(out)
            self._sync_status_to_ram()
            if d == 0:
                self.state.wreg = out
            else:
                self.write_ram(fa, out)
            self._bump_pc()
            return

        # subwf f,d : 0x0200 class (f - w)
        if (op & 0x3F00) == 0x0200:
            f = op & 0x007F
            d = (op >> 7) & 0x1
            fa = self._resolve_f(f)
            a = self.read_ram(fa)
            res = (a - self.state.wreg) & 0x1FF
            out = res & 0xFF
            self._set_c(1 if a >= self.state.wreg else 0)
            self._set_z(out)
            self._sync_status_to_ram()
            if d == 0:
                self.state.wreg = out
            else:
                self.write_ram(fa, out)
            self._bump_pc()
            return

        # andwf, iorwf, xorwf
        if (op & 0x3F00) in (0x0500, 0x0400, 0x0600):
            f = op & 0x007F
            d = (op >> 7) & 0x1
            fa = self._resolve_f(f)
            fv = self.read_ram(fa)
            if (op & 0x3F00) == 0x0500:
                out = fv & self.state.wreg
            elif (op & 0x3F00) == 0x0400:
                out = fv | self.state.wreg
            else:
                out = fv ^ self.state.wreg
            self._set_z(out)
            self._sync_status_to_ram()
            if d == 0:
                self.state.wreg = out
            else:
                self.write_ram(fa, out)
            self._bump_pc()
            return

        # comf / swapf / rrf / rlf
        if (op & 0x3F00) in (0x0900, 0x0E00, 0x0C00, 0x0D00):
            f = op & 0x007F
            d = (op >> 7) & 0x1
            fa = self._resolve_f(f)
            fv = self.read_ram(fa)

            if (op & 0x3F00) == 0x0900:  # comf
                out = (~fv) & 0xFF
                self._set_z(out)
                self._sync_status_to_ram()
            elif (op & 0x3F00) == 0x0E00:  # swapf
                out = ((fv & 0x0F) << 4) | ((fv & 0xF0) >> 4)
            elif (op & 0x3F00) == 0x0C00:  # rrf
                self._refresh_flags_from_ram()
                carry_in = self.state.status_c & 1
                new_c = fv & 0x01
                out = ((fv >> 1) | (carry_in << 7)) & 0xFF
                self._set_c(new_c)
                self._sync_status_to_ram()
            else:  # 0x0D00 rlf
                self._refresh_flags_from_ram()
                carry_in = self.state.status_c & 1
                new_c = 1 if (fv & 0x80) else 0
                out = ((fv << 1) & 0xFF) | carry_in
                self._set_c(new_c)
                self._sync_status_to_ram()

            if d == 0:
                self.state.wreg = out
            else:
                self.write_ram(fa, out)
            self._bump_pc()
            return

        # goto k : 0x2800
        if (op & 0x3800) == 0x2800:
            self.state.pc = self._goto_dest(op & 0x07FF)
            return

        # call k : 0x2000
        if (op & 0x3800) == 0x2000:
            if len(self.state.stack) >= self.config.stack_depth:
                raise VMRuntimeError("Stack overflow")
            self.state.stack.append((self.state.pc + 1) & self.PC_MASK)
            self.state.pc = self._goto_dest(op & 0x07FF)
            return

        # return / retlw
        if op == 0x0008:  # return
            if not self.state.stack:
                self.state.halted = True
            else:
                self.state.pc = self.state.stack.pop() & self.PC_MASK
            return

        if (op & 0x3F00) == 0x3400:  # retlw k
            self.state.wreg = op & 0x00FF
            if not self.state.stack:
                self.state.halted = True
            else:
                self.state.pc = self.state.stack.pop() & self.PC_MASK
            return

        # literal ALU ops: iorlw, andlw, xorlw, sublw, addlw
        if (op & 0x3F00) in (0x3800, 0x3900, 0x3A00, 0x3C00, 0x3E00):
            k = op & 0x00FF
            if (op & 0x3F00) == 0x3800:
                out = self.state.wreg | k
                self._set_z(out)
            elif (op & 0x3F00) == 0x3900:
                out = self.state.wreg & k
                self._set_z(out)
            elif (op & 0x3F00) == 0x3A00:
                out = self.state.wreg ^ k
                self._set_z(out)
            elif (op & 0x3F00) == 0x3C00:
                res = (k - self.state.wreg) & 0x1FF
                out = res & 0xFF
                self._set_c(1 if k >= self.state.wreg else 0)
                self._set_z(out)
            else:  # 0x3E00 addlw
                res = self.state.wreg + k
                out = res & 0xFF
                self._set_c(1 if res > 0xFF else 0)
                self._set_z(out)

            self.state.wreg = out & 0xFF
            self._sync_status_to_ram()
            self._bump_pc()
            return

        # sleep/halt-like instruction fallback
        if op in (0x0063, 0x0009):
            self.state.halted = True
            return

        # Unknown opcode fallback: advance to keep VM progressing.
        self._bump_pc()
