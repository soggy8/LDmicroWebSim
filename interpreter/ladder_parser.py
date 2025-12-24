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
  [CTU] = Count Up
  [CTD] = Count Down
  [END] = End of program
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Contact:
    """A contact (input) in the ladder."""
    name: str
    normally_closed: bool = False  # NC if True, NO if False


@dataclass
class Coil:
    """A coil (output) in the ladder."""
    name: str
    coil_type: str = "OUT"  # OUT, SET, RESET


@dataclass
class Timer:
    """A timer element."""
    name: str
    timer_type: str = "TON"  # TON, TOF, RTO
    delay: int = 1000  # ms


@dataclass
class Counter:
    """A counter element."""
    name: str
    counter_type: str = "CTU"  # CTU, CTD
    preset: int = 10


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
        current_rung_num = 0
        name_line = ""
        
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
                        name_line = line
                        continue
            
            # Check for rung line (starts with number)
            rung_match = re.match(r'\s*(\d+)\s*\|\|(.+)\|\|', line)
            if rung_match:
                rung_num = int(rung_match.group(1))
                rung_content = rung_match.group(2)
                
                # Check for END
                if "[END]" in rung_content:
                    break
                
                # Parse this rung
                rung = self.parse_rung(rung_num, name_line, rung_content)
                if rung:
                    self.program.rungs.append(rung)
                
                name_line = ""
                current_rung_num = rung_num
    
    def parse_rung(self, rung_num: int, name_line: str, content_line: str) -> Optional[Rung]:
        """Parse a single rung from name line and content line."""
        rung = Rung(number=rung_num)
        
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
        
        # Find positions of elements in content line
        elements = []
        
        # Find contacts: ] [ (NO) and ]/[ (NC)
        # Pattern matches both: ] [ (with dashes/spaces) and ]/[ 
        for match in re.finditer(r'(\/)?\]\s*-*\s*(\/)?\[', content_line):
            # NC if there's a / either before ] or between ] and [
            is_nc = match.group(1) == '/' or match.group(2) == '/'
            elements.append({
                'pos': match.start(),
                'center': match.start() + len(match.group(0)) // 2,
                'type': 'contact',
                'nc': is_nc
            })
        
        # Find coils ( )
        for match in re.finditer(r'\(\s*([SR]?)\s*\)', content_line):
            coil_type = match.group(1)
            if coil_type == 'S':
                ctype = 'SET'
            elif coil_type == 'R':
                ctype = 'RESET'
            else:
                ctype = 'OUT'
            elements.append({
                'pos': match.start(),
                'center': match.start() + len(match.group(0)) // 2,
                'type': 'coil',
                'coil_type': ctype
            })
        
        # Find timers [TON], [TOF], etc.
        for match in re.finditer(r'\[(TON|TOF|RTO)\]', content_line):
            elements.append({
                'pos': match.start(),
                'center': match.start() + len(match.group(0)) // 2,
                'type': 'timer',
                'timer_type': match.group(1)
            })
        
        # Find counters [CTU], [CTD]
        for match in re.finditer(r'\[(CTU|CTD)\]', content_line):
            elements.append({
                'pos': match.start(),
                'center': match.start() + len(match.group(0)) // 2,
                'type': 'counter',
                'counter_type': match.group(1)
            })
        
        # Sort elements by position
        elements.sort(key=lambda x: x['pos'])
        
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
            elif elem['type'] == 'coil':
                rung.coils.append(Coil(
                    name=name,
                    coil_type=elem.get('coil_type', 'OUT')
                ))
            elif elem['type'] == 'timer':
                rung.timers.append(Timer(
                    name=name,
                    timer_type=elem['timer_type']
                ))
            elif elem['type'] == 'counter':
                rung.counters.append(Counter(
                    name=name,
                    counter_type=elem['counter_type']
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

