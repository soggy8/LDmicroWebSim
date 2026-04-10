"""
Parser for LDmicro text export format (ladder diagram).

Parses ladder diagrams like:
   ||       XS1              XS2              YH1       ||
 1 ||-------] [--------------]/[--------------( )-------||

Symbols:
  ] [   = Normally Open contact (NO) - true when input is ON
  ]/[   = Normally Closed contact (NC) - true when input is OFF
  ( )   = Output coil - energize output
  (S)   = Set coil - latch ON
  (R)   = Reset coil - latch OFF
  [TON] = Timer On-Delay
  [TOF] = Timer Off-Delay
  [RTO] = Retentive On-Delay (accumulator holds when input drops before done)
  [CTU] = Count Up
  [CTD] = Count Down
  {CTC lo:hi} = Circular counter (wraps between lo and hi inclusive)
  {RES} = Reset counter
  [END] = End of program
  Compare: [var ==] / [var >] / [1 >=] … with second operand ``[var2]`` or ``[-4]`` (signed 16-bit).
  ``/=`` in exports means not-equal (``!=``).
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Contact:
    """A contact (input) in the ladder."""
    name: str
    normally_closed: bool = False  # NC if True, NO if False
    kind: str = "contact"  # contact, compare
    operator: str | None = None  # ==, !=, >, >=, <, <=
    value: int | None = None  # RHS literal (signed), when RHS is a constant
    compare_lhs_const: int | None = None  # LHS literal e.g. ``[1 >=]`` … ``[Ton]``
    compare_rhs_name: str | None = None  # RHS variable name


@dataclass
class Coil:
    """A coil (output) in the ladder."""
    name: str
    coil_type: str = "OUT"  # OUT, SET, RESET


@dataclass
class Timer:
    """A timer element from the ladder diagram (preset only if shown in export)."""
    name: str
    timer_type: str = "TON"  # TON, TOF, RTO
    delay: int | None = None  # ms; set when export has e.g. [TON 500.0 ms]


@dataclass
class Counter:
    """Counter symbol from the ladder export.

    counter_type:
      CTU / CTD — plain count-up / count-down block.
      CTUCOND / CTDCOND — compare block ``[CTU >=n]`` / ``[CTD >=n]`` (uses preset).
      CTC — circular counter ``{CTC lo:hi}`` (uses min_value, max_value).
      RES — reset coil ``{RES}`` for the nearest associated counter name.
    """
    name: str
    counter_type: str = "CTU"
    preset: int | None = None  # CTUCOND / CTDCOND target; unused for CTC/RES
    min_value: int | None = None  # CTC low bound
    max_value: int | None = None  # CTC high bound


@dataclass
class Rung:
    """A single rung in the ladder diagram."""
    number: int
    contacts: list[Contact] = field(default_factory=list)
    coils: list[Coil] = field(default_factory=list)
    timers: list[Timer] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)
    parallel_branches: list['Rung'] = field(default_factory=list)


@dataclass
class IOAssignment:
    """I/O pin assignment."""
    name: str
    io_type: str  # "Digital input", "Digital output"
    pin: int


@dataclass
class LadderProgram:
    """Complete ladder program."""
    target: str = ""
    crystal_freq: float = 0.0
    cycle_time: float = 0.0
    rungs: list[Rung] = field(default_factory=list)
    io_assignments: list[IOAssignment] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)


class LadderParser:
    """
    Parser for LDmicro text export format.
    """
    
    def __init__(self, text: str):
        self.text = text
        self.lines = text.split('\n')
        self.program = LadderProgram()
        self.pos = 0
    
    def parse(self) -> LadderProgram:
        """Parse the entire ladder diagram text."""
        self.parse_header()
        self.parse_ladder_diagram()
        self.parse_io_assignment()
        self.extract_io_names()
        return self.program
    
    def parse_header(self):
        """Parse the header section."""
        for line in self.lines[:5]:
            # Parse target MCU
            if "for '" in line.lower():
                match = re.search(r"for '([^']+)'", line)
                if match:
                    self.program.target = match.group(1)
            
            # Parse crystal frequency
            if "mhz" in line.lower():
                match = re.search(r'(\d+\.?\d*)\s*MHz', line, re.IGNORECASE)
                if match:
                    self.program.crystal_freq = float(match.group(1))
            
            # Parse cycle time
            if "cycle time" in line.lower():
                match = re.search(r'(\d+\.?\d*)\s*ms\s*cycle', line, re.IGNORECASE)
                if match:
                    self.program.cycle_time = float(match.group(1))
    
    def parse_ladder_diagram(self):
        """Parse the LADDER DIAGRAM section."""
        in_diagram = False
        current_rung_num: int | None = None
        pending_name_line = ""
        current_rows: list[tuple[str, str]] = []
        
        for i, line in enumerate(self.lines):
            # Find start of ladder diagram
            if "LADDER DIAGRAM:" in line:
                in_diagram = True
                continue
            
            # End at I/O ASSIGNMENT section
            if "I/O ASSIGNMENT:" in line:
                break
            
            if not in_diagram:
                continue
            
            # Skip empty lines and pure rail lines
            if not line.strip() or line.strip() == "||" or "||" not in line:
                continue
            
            # Check if this is a name line (has element names but no rung number)
            # Name lines have || but no contacts/coils symbols AND no leading number
            if "||" in line and not re.match(r'\s*\d+\s*\|\|', line):
                # Check if it contains element names (letters/numbers between ||)
                content = line.split("||")[1] if "||" in line else ""
                if content.strip() and not any(sym in line for sym in [']-[', ']/[', ') ', '( ', '[END]', '---']):
                    # This might be a name line - but only if it has actual names
                    if re.search(r'[A-Za-z]\w*', content):
                        pending_name_line = line
                        continue
            
            # Check for rung line (starts with number)
            rung_match = re.match(r'\s*(\d+)\s*\|\|(.+)\|\|', line)
            if rung_match:
                rung_num = int(rung_match.group(1))
                rung_content = rung_match.group(2)
                
                # Check for END
                if "[END]" in rung_content:
                    break
                
                # Finalize previous rung block.
                if current_rung_num is not None and current_rows:
                    rung = self.parse_rung_rows(current_rung_num, current_rows)
                    if rung:
                        self.program.rungs.append(rung)

                current_rung_num = rung_num
                current_rows = [(pending_name_line, rung_content)]
                pending_name_line = ""
                continue

            # Continuation row inside current rung: no leading number but has symbols.
            cont_match = re.match(r'\s*\|\|(.+)\|\|', line)
            if current_rung_num is not None and cont_match:
                content = cont_match.group(1)
                if any(
                    sym in content
                    for sym in ["]", "(", "{", "[TON", "[TOF", "[CT", "+", "[RES", "==", "/="]
                ):
                    current_rows.append((pending_name_line, content))
                    pending_name_line = ""

        # Finalize trailing rung block.
        if current_rung_num is not None and current_rows:
            rung = self.parse_rung_rows(current_rung_num, current_rows)
            if rung:
                self.program.rungs.append(rung)

    def parse_rung_rows(self, rung_num: int, rows: list[tuple[str, str]]) -> Optional[Rung]:
        if not rows:
            return None
        base = self.parse_rung(rung_num, rows[0][0], rows[0][1])
        if not base:
            return None
        for name_line, content_line in rows[1:]:
            branch = self.parse_rung(rung_num, name_line, content_line)
            if not branch:
                continue
            # Continuation rows commonly branch from the first path; inherit shared
            # leading series conditions from the base row.
            inherited_contacts = [
                Contact(
                    c.name,
                    c.normally_closed,
                    c.kind,
                    c.operator,
                    c.value,
                    c.compare_lhs_const,
                    c.compare_rhs_name,
                )
                for c in base.contacts
                if c.kind in ("contact", "compare")
            ]
            inherited_timers = [Timer(t.name, t.timer_type, t.delay) for t in base.timers]
            inherited_counters = [
                Counter(c.name, c.counter_type, c.preset, c.min_value, c.max_value)
                for c in base.counters
                if c.counter_type in ("CTUCOND", "CTDCOND", "CTC")
            ]
            branch.contacts = inherited_contacts + branch.contacts
            branch.timers = inherited_timers + branch.timers
            branch.counters = inherited_counters + branch.counters
            base.parallel_branches.append(branch)
        return base

    def _merge_compare_pair(self, lhs: dict, rhs: dict | None) -> dict:
        op = lhs["operator"]
        merged: dict = {
            "type": "compare_merged",
            "pos": lhs["pos"],
            "center": lhs["center"],
            "operator": op,
            "lhs_var": None,
            "lhs_const": None,
            "rhs_const": None,
            "rhs_var": None,
        }
        if lhs["type"] == "compare_lhs_var":
            merged["lhs_var"] = lhs["var"]
        else:
            merged["lhs_const"] = lhs["const"]
        if rhs:
            if rhs["type"] == "compare_rhs_const":
                merged["rhs_const"] = rhs["value"]
            else:
                merged["rhs_var"] = rhs["var"]
        else:
            merged["rhs_const"] = 0
        return merged

    def _collapse_compare_elements(self, elements: list[dict]) -> list[dict]:
        """Pair compare LHS with the next RHS bracket; drop orphan RHS fragments."""
        out: list[dict] = []
        i = 0
        n = len(elements)
        while i < n:
            e = elements[i]
            if e["type"] in ("compare_lhs_var", "compare_lhs_const"):
                rhs = None
                if i + 1 < n and elements[i + 1]["type"] in (
                    "compare_rhs_const",
                    "compare_rhs_var",
                ):
                    rhs = elements[i + 1]
                    i += 2
                else:
                    i += 1
                out.append(self._merge_compare_pair(e, rhs))
                continue
            if e["type"] in ("compare_rhs_const", "compare_rhs_var"):
                i += 1
                continue
            out.append(e)
            i += 1
        return out

    def parse_rung(self, rung_num: int, name_line: str, content_line: str) -> Optional[Rung]:
        """Parse a single rung from name line and content line."""
        rung = Rung(number=rung_num)
        nl = name_line or ""
        cl = content_line or ""
        merged = f"{nl}\n{cl}" if nl else cl
        content_offset = len(nl) + (1 if nl else 0)

        # Extract element names and their positions from name line
        name_positions = []
        if name_line:
            name_content = name_line.split("||")[1] if "||" in name_line else name_line
            # Find all names with their positions
            for match in re.finditer(r'\b([A-Za-z_]\w*)\b', name_content):
                name_positions.append({
                    'name': match.group(1),
                    'pos': match.start(),
                    'center': match.start() + len(match.group(1)) // 2
                })

        elements = []

        # Find contacts: ] [ (NO) and ]/[ (NC) — horizontal layout in content row only
        for match in re.finditer(r'\]/\[|\]\s+\[', cl):
            is_nc = match.group(0) == ']/['
            elements.append({
                'pos': content_offset + match.start(),
                'center': content_offset + match.start() + len(match.group(0)) // 2,
                'type': 'contact',
                'nc': is_nc
            })

        # Find coils ( )
        for match in re.finditer(r'\(\s*([SR]?)\s*\)', cl):
            coil_type = match.group(1)
            if coil_type == 'S':
                ctype = 'SET'
            elif coil_type == 'R':
                ctype = 'RESET'
            else:
                ctype = 'OUT'
            elements.append({
                'pos': content_offset + match.start(),
                'center': content_offset + match.start() + len(match.group(0)) // 2,
                'type': 'coil',
                'coil_type': ctype
            })

        # Find timed blocks, e.g. [TON 250.0 ms], [TOF 1.500 s]
        for match in re.finditer(r'\[(TON|TOF|RTO)\s+(\d+\.?\d*)\s*(ms|s)\]', cl, re.IGNORECASE):
            val = float(match.group(2))
            unit = match.group(3).lower()
            delay_ms = int(val if unit == "ms" else val * 1000.0)
            elements.append({
                'pos': content_offset + match.start(),
                'center': content_offset + match.start() + len(match.group(0)) // 2,
                'type': 'timer',
                'timer_type': match.group(1).upper(),
                'delay': delay_ms,
            })

        # Find timers [TON], [TOF], etc.
        for match in re.finditer(r'\[(TON|TOF|RTO)\]', cl, re.IGNORECASE):
            elements.append({
                'pos': content_offset + match.start(),
                'center': content_offset + match.start() + len(match.group(0)) // 2,
                'type': 'timer',
                'timer_type': match.group(1).upper(),
            })

        # Find counters [CTU], [CTD]
        for match in re.finditer(r'\[(CTU|CTD)\]', cl):
            elements.append({
                'pos': content_offset + match.start(),
                'center': content_offset + match.start() + len(match.group(0)) // 2,
                'type': 'counter',
                'counter_type': match.group(1)
            })

        # Find counter condition blocks, e.g. [CTU >=4]
        for match in re.finditer(r'\[(CTU|CTD)\s*>=\s*(\d+)\]', cl):
            elements.append({
                'pos': content_offset + match.start(),
                'center': content_offset + match.start() + len(match.group(0)) // 2,
                'type': 'counter',
                'counter_type': f"{match.group(1)}COND",
                'preset': int(match.group(2)),
            })

        # Compare: scan name + content so [C1 ==] on name row pairs with [ 0 ] on content row.
        _cmp_op = r'(==|>=|<=|!=|>|<|\/=)'
        for match in re.finditer(
            rf'\[\s*([A-Za-z_]\w*)\s*{_cmp_op}\s*\]',
            merged,
        ):
            raw_op = match.group(2)
            op = "!=" if raw_op == "/=" else raw_op
            elements.append({
                'pos': match.start(),
                'center': match.start() + len(match.group(0)) // 2,
                'type': 'compare_lhs_var',
                'var': match.group(1),
                'operator': op,
            })
        for match in re.finditer(
            rf'\[\s*(-?\d+)\s*{_cmp_op}\s*\]',
            merged,
        ):
            raw_op = match.group(2)
            op = "!=" if raw_op == "/=" else raw_op
            elements.append({
                'pos': match.start(),
                'center': match.start() + len(match.group(0)) // 2,
                'type': 'compare_lhs_const',
                'const': int(match.group(1)),
                'operator': op,
            })
        _compare_kw = frozenset(
            w.upper() for w in ("CTU", "CTD", "TON", "TOF", "RTO", "END")
        )
        for match in re.finditer(r'\[\s*(-?\d+)\s*\]', merged):
            elements.append({
                'pos': match.start(),
                'center': match.start() + len(match.group(0)) // 2,
                'type': 'compare_rhs_const',
                'value': int(match.group(1)),
            })
        for match in re.finditer(r'\[\s*([A-Za-z_]\w*)\s*\]', merged):
            inner = match.group(1)
            if inner.upper() in _compare_kw:
                continue
            elements.append({
                'pos': match.start(),
                'center': match.start() + len(match.group(0)) // 2,
                'type': 'compare_rhs_var',
                'var': inner,
            })

        # Counter actions, e.g. {CTC 0:2}, {RES}
        for match in re.finditer(r'\{\s*CTC\s+(\d+)\s*:\s*(\d+)\s*\}', cl):
            elements.append({
                'pos': content_offset + match.start(),
                'center': content_offset + match.start() + len(match.group(0)) // 2,
                'type': 'counter',
                'counter_type': 'CTC',
                'min_value': int(match.group(1)),
                'max_value': int(match.group(2)),
            })
        for match in re.finditer(r'\{\s*RES\s*\}', cl):
            elements.append({
                'pos': content_offset + match.start(),
                'center': content_offset + match.start() + len(match.group(0)) // 2,
                'type': 'counter',
                'counter_type': 'RES',
            })

        elements.sort(key=lambda x: x['pos'])
        elements = self._collapse_compare_elements(elements)
        
        # Match names to elements by closest position
        for elem in elements:
            # Find the closest name by position
            best_name = None
            best_dist = float('inf')
            
            for np in name_positions:
                dist = abs(np['center'] - elem['center'])
                if dist < best_dist:
                    best_dist = dist
                    best_name = np['name']
            
            name = best_name if best_name else f"UNKNOWN"
            
            if elem['type'] == 'contact':
                rung.contacts.append(Contact(
                    name=name,
                    normally_closed=elem['nc']
                ))
            elif elem['type'] == 'compare_merged':
                rhs_v = elem.get("rhs_var")
                rhs_c = elem.get("rhs_const")
                rung.contacts.append(Contact(
                    name=elem.get("lhs_var") or "",
                    normally_closed=False,
                    kind="compare",
                    operator=elem["operator"],
                    value=None if rhs_v is not None else rhs_c,
                    compare_lhs_const=elem.get("lhs_const"),
                    compare_rhs_name=rhs_v,
                ))
            elif elem['type'] == 'coil':
                rung.coils.append(Coil(
                    name=name,
                    coil_type=elem.get('coil_type', 'OUT')
                ))
            elif elem['type'] == 'timer':
                rung.timers.append(Timer(
                    name=name,
                    timer_type=elem['timer_type'],
                    delay=elem.get('delay'),
                ))
            elif elem['type'] == 'counter':
                rung.counters.append(Counter(
                    name=name,
                    counter_type=elem['counter_type'],
                    preset=elem.get('preset'),
                    min_value=elem.get('min_value'),
                    max_value=elem.get('max_value'),
                ))
        
        return rung if (rung.contacts or rung.coils or rung.timers or rung.counters) else None
    
    def parse_io_assignment(self):
        """Parse the I/O ASSIGNMENT section."""
        in_io = False
        
        for line in self.lines:
            if "I/O ASSIGNMENT:" in line:
                in_io = True
                continue
            
            if not in_io:
                continue
            
            # Skip header and separator lines
            if "----" in line or "Name" in line or "Type" in line:
                continue
            
            # Parse I/O line: "  XS1                        | Digital input      | 2"
            parts = line.split("|")
            if len(parts) >= 3:
                name = parts[0].strip()
                io_type = parts[1].strip()
                pin_str = parts[2].strip()
                
                if name and io_type:
                    try:
                        pin = int(pin_str) if pin_str.isdigit() else 0
                    except:
                        pin = 0
                    
                    self.program.io_assignments.append(IOAssignment(
                        name=name,
                        io_type=io_type,
                        pin=pin
                    ))
    
    def extract_io_names(self):
        """Extract input and output names from I/O assignments."""
        for io in self.program.io_assignments:
            if "input" in io.io_type.lower():
                if io.name not in self.program.inputs:
                    self.program.inputs.append(io.name)
            elif "output" in io.io_type.lower():
                if io.name not in self.program.outputs:
                    self.program.outputs.append(io.name)
    
    def to_javascript(self) -> str:
        """Convert the ladder program to JavaScript code."""
        lines = ["function PlcCycle() {"]
        
        for rung in self.program.rungs:
            # Build condition from contacts
            conditions = []
            for contact in rung.contacts:
                if contact.normally_closed:
                    conditions.append(f"!state.inputs[inputMap['{contact.name}']]")
                else:
                    conditions.append(f"state.inputs[inputMap['{contact.name}']]")
            
            # Build actions for coils
            if conditions and rung.coils:
                condition_str = " && ".join(conditions)
                lines.append(f"  // Rung {rung.number}")
                lines.append(f"  if ({condition_str}) {{")
                
                for coil in rung.coils:
                    lines.append(f"    state.outputs[outputMap['{coil.name}']] = 1;")
                
                lines.append("  } else {")
                
                for coil in rung.coils:
                    if coil.coil_type == "OUT":  # Only reset for normal coils
                        lines.append(f"    state.outputs[outputMap['{coil.name}']] = 0;")
                
                lines.append("  }")
        
        lines.append("}")
        return "\n".join(lines)


def parse_ladder(text: str) -> LadderProgram:
    """Convenience function to parse ladder diagram text."""
    parser = LadderParser(text)
    return parser.parse()

