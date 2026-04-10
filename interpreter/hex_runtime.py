"""
Intel HEX loader and initial VM scaffolding for LDmicro .hex execution.

This module is intentionally phase-1:
- Parse and validate Intel HEX records
- Build a normalized flash image
- Provide a minimal runtime state container for upcoming instruction emulation
"""

from __future__ import annotations

from dataclasses import dataclass, field


class HexParseError(ValueError):
    """Raised when an Intel HEX payload is invalid."""


@dataclass
class IntelHexRecord:
    line_no: int
    length: int
    address: int
    record_type: int
    data: bytes
    checksum: int


@dataclass
class ProgramImage:
    """Normalized image from Intel HEX."""

    flash_bytes: dict[int, int] = field(default_factory=dict)
    records: list[IntelHexRecord] = field(default_factory=list)
    min_address: int = 0
    max_address: int = 0
    record_count: int = 0
    extended_linear_blocks: list[int] = field(default_factory=list)
    start_linear_address: int | None = None
    start_segment_address: int | None = None

    def to_dict(self) -> dict:
        pic14_words = self.to_word_view(2)
        cfg_words = self.extract_config_region_words()
        return {
            "minAddress": self.min_address,
            "maxAddress": self.max_address,
            "byteCount": len(self.flash_bytes),
            "recordCount": self.record_count,
            "extendedLinearBlocks": self.extended_linear_blocks,
            "hasStartLinearAddress": self.start_linear_address is not None,
            "hasStartSegmentAddress": self.start_segment_address is not None,
            "pic14WordCountEstimate": len(pic14_words),
            "configWordCandidates": cfg_words,
        }

    def ordered_bytes(self) -> list[tuple[int, int]]:
        return sorted(self.flash_bytes.items(), key=lambda it: it[0])

    def to_word_view(self, word_size: int = 2, little_endian: bool = True) -> dict[int, int]:
        """
        Convert dense bytes to word-addressed view.
        Missing bytes in a word are padded with 0x00.
        """
        if word_size <= 0:
            raise ValueError("word_size must be > 0")

        words: dict[int, int] = {}
        if not self.flash_bytes:
            return words

        min_addr = min(self.flash_bytes.keys())
        max_addr = max(self.flash_bytes.keys())

        aligned_start = min_addr - (min_addr % word_size)
        for base in range(aligned_start, max_addr + 1, word_size):
            chunk = [self.flash_bytes.get(base + i, 0) for i in range(word_size)]
            if little_endian:
                val = 0
                for i, b in enumerate(chunk):
                    val |= (b & 0xFF) << (8 * i)
            else:
                val = 0
                for b in chunk:
                    val = (val << 8) | (b & 0xFF)
            words[base // word_size] = val
        return words

    def reset_vector_candidate(self) -> int:
        """
        Return best-effort reset vector address candidate.
        For many MCUs this is address 0; keep heuristic simple for now.
        """
        return 0

    def extract_config_region_words(self) -> list[dict]:
        """
        Extract potential config words. PIC families commonly place these near
        addresses starting around 0x4000 in Intel HEX output.
        """
        words = self.to_word_view(2)
        out: list[dict] = []
        for word_addr, value in words.items():
            byte_addr = word_addr * 2
            if byte_addr >= 0x4000:
                out.append({"wordAddress": word_addr, "byteAddress": byte_addr, "value": value})
        return out[:32]


@dataclass
class VMState:
    """
    Placeholder runtime state for future PIC instruction execution.
    """

    pc: int = 0
    wreg: int = 0
    cycles: int = 0
    ram: list[int] = field(default_factory=lambda: [0] * 512)
    stack: list[int] = field(default_factory=list)


def _parse_record(line: str, line_no: int) -> IntelHexRecord:
    if not line.startswith(":"):
        raise HexParseError(f"Line {line_no}: Intel HEX record must start with ':'")

    payload = line[1:].strip()
    if len(payload) < 10 or (len(payload) % 2) != 0:
        raise HexParseError(f"Line {line_no}: malformed HEX record length")

    try:
        raw = bytes.fromhex(payload)
    except ValueError as exc:
        raise HexParseError(f"Line {line_no}: invalid hex digits") from exc

    length = raw[0]
    if len(raw) != 5 + length:
        raise HexParseError(f"Line {line_no}: byte count mismatch")

    address = (raw[1] << 8) | raw[2]
    record_type = raw[3]
    data = raw[4: 4 + length]
    checksum = raw[-1]

    # Intel HEX checksum: sum(all bytes incl checksum) & 0xFF == 0
    if (sum(raw) & 0xFF) != 0:
        raise HexParseError(f"Line {line_no}: checksum mismatch")

    return IntelHexRecord(
        line_no=line_no,
        length=length,
        address=address,
        record_type=record_type,
        data=data,
        checksum=checksum,
    )


def parse_intel_hex(source: str) -> ProgramImage:
    lines = [ln.strip() for ln in source.splitlines() if ln.strip()]
    if not lines:
        raise HexParseError("Empty HEX input")

    image = ProgramImage()
    upper_linear = 0
    eof_seen = False
    seen_addresses: set[int] = set()

    for idx, line in enumerate(lines, start=1):
        rec = _parse_record(line, idx)
        image.records.append(rec)
        image.record_count += 1

        if rec.record_type == 0x00:  # data
            base = (upper_linear << 16) | rec.address
            for off, byte_val in enumerate(rec.data):
                addr = base + off
                image.flash_bytes[addr] = byte_val
                seen_addresses.add(addr)
        elif rec.record_type == 0x01:  # EOF
            eof_seen = True
            break
        elif rec.record_type == 0x04:  # extended linear address
            if rec.length != 2:
                raise HexParseError(f"Line {idx}: ELA record must contain 2 data bytes")
            upper_linear = (rec.data[0] << 8) | rec.data[1]
            image.extended_linear_blocks.append(upper_linear)
        elif rec.record_type == 0x05:  # start linear address
            if rec.length != 4:
                raise HexParseError(f"Line {idx}: SLA record must contain 4 data bytes")
            image.start_linear_address = (
                (rec.data[0] << 24)
                | (rec.data[1] << 16)
                | (rec.data[2] << 8)
                | rec.data[3]
            )
        elif rec.record_type == 0x03:  # start segment address
            if rec.length != 4:
                raise HexParseError(f"Line {idx}: SSA record must contain 4 data bytes")
            image.start_segment_address = (
                (rec.data[0] << 24)
                | (rec.data[1] << 16)
                | (rec.data[2] << 8)
                | rec.data[3]
            )
        else:
            # Keep parser tolerant for future records (02/03/05), ignored for now.
            continue

    if not eof_seen:
        raise HexParseError("HEX file missing EOF record (:00000001FF)")

    if seen_addresses:
        image.min_address = min(seen_addresses)
        image.max_address = max(seen_addresses)
    else:
        image.min_address = 0
        image.max_address = 0

    return image


def looks_like_intel_hex(source: str) -> bool:
    lines = [ln.strip() for ln in source.splitlines() if ln.strip()]
    if not lines:
        return False
    return all(ln.startswith(":") for ln in lines[: min(4, len(lines))])
