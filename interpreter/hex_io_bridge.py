"""
Bridge between board signal names and VM RAM/register bits.
"""

from __future__ import annotations

from dataclasses import dataclass

from .hex_vm import Pic16VM

PORT_ADDRS = frozenset({0x05, 0x06, 0x07, 0x08, 0x09})


@dataclass
class SignalBinding:
    ram_addr: int
    bit: int
    active_low: bool = False


class BoardIOBridge:
    """
    Maps simulator board I/O names into a stable VM bit map.

    This is intentionally configurable later by target/profiles.
    """

    # Dual mapping:
    # 1) synthetic RAM map (works with toy/golden tests)
    # 2) PIC SFR-style map (matches many LDmicro HEX builds), often active-low.
    SYNTHETIC_INPUT_BINDINGS: dict[str, list[SignalBinding]] = {
        # Synthetic logical map
        "FOTO": [SignalBinding(0x20, 0), SignalBinding(0x06, 0, active_low=False)],
        "SEN": [SignalBinding(0x20, 1), SignalBinding(0x06, 1, active_low=False)],
        "MOV": [SignalBinding(0x20, 2), SignalBinding(0x06, 2, active_low=False)],
        "TRIG": [SignalBinding(0x20, 3), SignalBinding(0x06, 3, active_low=False)],
        "PO1": [SignalBinding(0x20, 4), SignalBinding(0x06, 4, active_low=False)],
        "PO2": [SignalBinding(0x20, 5), SignalBinding(0x06, 5, active_low=False)],
        "S1": [SignalBinding(0x20, 6), SignalBinding(0x05, 0, active_low=False)],
        "S2": [SignalBinding(0x20, 7), SignalBinding(0x05, 1, active_low=False)],
        "S3": [SignalBinding(0x21, 0), SignalBinding(0x05, 2, active_low=False)],
        "BTN1": [SignalBinding(0x21, 1), SignalBinding(0x05, 3, active_low=False)],
        "BTN2": [SignalBinding(0x21, 2), SignalBinding(0x05, 4, active_low=False)],
        "BTN3": [SignalBinding(0x21, 3), SignalBinding(0x05, 5, active_low=False)],
    }

    SYNTHETIC_OUTPUT_BINDINGS: dict[str, list[SignalBinding]] = {
        # Keep both synthetic output map and unique SFR-style map.
        "H1": [SignalBinding(0x30, 3), SignalBinding(0x08, 0, active_low=False)],
        "H2": [SignalBinding(0x30, 4), SignalBinding(0x08, 1, active_low=False)],
        "H3": [SignalBinding(0x30, 5), SignalBinding(0x08, 2, active_low=False)],
        "FAN1": [SignalBinding(0x30, 0), SignalBinding(0x08, 3, active_low=False)],
        "FAN2": [SignalBinding(0x30, 1), SignalBinding(0x08, 4, active_low=False)],
        "FAN3": [SignalBinding(0x30, 2), SignalBinding(0x08, 5, active_low=False)],
        "PANIC": [SignalBinding(0x30, 6), SignalBinding(0x08, 6, active_low=False)],
        "BELL": [SignalBinding(0x30, 7), SignalBinding(0x08, 7, active_low=False)],
    }

    # LDmicro PIC16F877: pin order follows the compiler's I/O list (Settings → I/O).
    # A minimal "S1 → H1" HEX from LDmicro uses PORTA,0 for the first input and
    # PORTD,2 for the first coil (see BTFSC 0x05,0 / BSF 0x08,2 in the listing).
    # We map board names to the same sequential PORTD order as the web UI output row
    # (FAN1… then H1…) so the first few coils match RD0, RD1, RD2, …
    PIC16F877_INPUT_BINDINGS: dict[str, list[SignalBinding]] = {
        "FOTO": [SignalBinding(0x06, 0, active_low=False)],   # PORTB0
        "SEN": [SignalBinding(0x06, 1, active_low=False)],    # PORTB1
        "MOV": [SignalBinding(0x06, 2, active_low=False)],    # PORTB2
        "TRIG": [SignalBinding(0x06, 3, active_low=False)],   # PORTB3
        "PO1": [SignalBinding(0x06, 4, active_low=False)],    # PORTB4
        "PO2": [SignalBinding(0x06, 5, active_low=False)],    # PORTB5
        "S1": [SignalBinding(0x05, 0, active_low=False)],     # PORTA0 (first X in typical small build)
        "S2": [SignalBinding(0x05, 1, active_low=False)],     # PORTA1
        "S3": [SignalBinding(0x05, 2, active_low=False)],     # PORTA2
        "BTN1": [SignalBinding(0x05, 3, active_low=False)],   # PORTA3
        "BTN2": [SignalBinding(0x05, 4, active_low=False)],   # PORTA4
        "BTN3": [SignalBinding(0x05, 5, active_low=False)],   # PORTA5
    }

    PIC16F877_OUTPUT_BINDINGS: dict[str, list[SignalBinding]] = {
        "FAN1": [SignalBinding(0x08, 0, active_low=False)],   # PORTD0
        "FAN2": [SignalBinding(0x08, 1, active_low=False)],   # PORTD1
        # Minimal LDmicro HEX often places the first coil on RD2 (BSF PORTD,2); map H1 there.
        "H1": [SignalBinding(0x08, 2, active_low=False)],     # PORTD2
        "FAN3": [SignalBinding(0x08, 3, active_low=False)],   # PORTD3
        "H2": [SignalBinding(0x08, 4, active_low=False)],     # PORTD4
        "H3": [SignalBinding(0x08, 5, active_low=False)],     # PORTD5
        "PANIC": [SignalBinding(0x08, 6, active_low=False)],  # PORTD6
        "BELL": [SignalBinding(0x08, 7, active_low=False)],   # PORTD7
    }

    def __init__(self, vm: Pic16VM, profile: str = "synthetic"):
        self.vm = vm
        self._profile = profile
        if profile == "pic16f877":
            self.input_bindings = self.PIC16F877_INPUT_BINDINGS
            self.output_bindings = self.PIC16F877_OUTPUT_BINDINGS
        else:
            self.input_bindings = self.SYNTHETIC_INPUT_BINDINGS
            self.output_bindings = self.SYNTHETIC_OUTPUT_BINDINGS

    def write_inputs(self, inputs: dict[str, int]):
        for name, bindings in self.input_bindings.items():
            val = 1 if inputs.get(name, 0) else 0
            for binding in bindings:
                bit_val = (0 if val else 1) if binding.active_low else val
                addr = binding.ram_addr
                if addr in PORT_ADDRS:
                    self.vm.set_external_pin(addr, binding.bit, bit_val)
                else:
                    current = self.vm.read_ram(addr)
                    if bit_val:
                        current |= 1 << binding.bit
                    else:
                        current &= ~(1 << binding.bit)
                    self.vm.write_ram(addr, current)
        if self._profile == "pic16f877":
            self.vm.strobe_ldmicro_scan_tick()

    def read_outputs(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for name, bindings in self.output_bindings.items():
            active = 0
            for binding in bindings:
                addr = binding.ram_addr
                if addr in PORT_ADDRS:
                    bit = self.vm.get_output_drive(addr, binding.bit)
                else:
                    current = self.vm.read_ram(addr)
                    bit = 1 if (current & (1 << binding.bit)) else 0
                logical = (0 if bit else 1) if binding.active_low else bit
                if logical:
                    active = 1
                    break
            out[name] = active
        return out
