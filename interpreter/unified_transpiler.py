"""
Unified Transpiler for LDmicro exports.

Supports both:
1. C code export
2. Text ladder diagram export

Auto-detects the format and uses the appropriate parser.
"""

from dataclasses import dataclass, field, asdict
from typing import Any
import json

from .ladder_parser import parse_ladder, LadderProgram
from .transpiler import transpile as transpile_c, SimulationProgram, IOPin, Timer, Counter


# ============================================================================
# Board Configuration - Physical Training Board
# ============================================================================

BOARD_INPUTS = [
    {"name": "FOTO", "type": "sensor", "color": "green", "label": "Light Sensor"},
    {"name": "SEN", "type": "sensor", "color": "blue", "label": "Proximity Sensor"},
    {"name": "MOV", "type": "sensor", "color": "green", "label": "Movement Sensor"},
    {"name": "TRIG", "type": "sensor", "color": "orange", "label": "Trigger/Door"},
    {"name": "PO1", "type": "sensor", "color": "gray", "label": "Metal Detector 1"},
    {"name": "PO2", "type": "sensor", "color": "gray", "label": "Metal Detector 2"},
    {"name": "S1", "type": "switch", "color": "white", "label": "Switch 1"},
    {"name": "S2", "type": "switch", "color": "white", "label": "Switch 2"},
    {"name": "S3", "type": "switch", "color": "white", "label": "Switch 3"},
    {"name": "BTN1", "type": "button", "color": "green", "label": "Button 1"},
    {"name": "BTN2", "type": "button", "color": "yellow", "label": "Button 2"},
    {"name": "BTN3", "type": "button", "color": "red", "label": "Button 3"},
]

BOARD_OUTPUTS = [
    {"name": "FAN1", "type": "fan", "color": "gray", "label": "Fan 1"},
    {"name": "FAN2", "type": "fan", "color": "gray", "label": "Fan 2"},
    {"name": "FAN3", "type": "fan", "color": "gray", "label": "Fan 3"},
    {"name": "H1", "type": "light", "color": "green", "label": "Green Light"},
    {"name": "H2", "type": "light", "color": "yellow", "label": "Yellow Light"},
    {"name": "H3", "type": "light", "color": "red", "label": "Red Light"},
    {"name": "PANIC", "type": "strobe", "color": "red", "label": "Panic Strobe"},
    {"name": "BELL", "type": "buzzer", "color": "silver", "label": "Bell"},
]

# Name to index mappings
INPUT_MAP = {inp["name"]: i for i, inp in enumerate(BOARD_INPUTS)}
OUTPUT_MAP = {out["name"]: i for i, out in enumerate(BOARD_OUTPUTS)}


def normalize_io_name(name: str, is_input: bool) -> str:
    """
    Normalize LDmicro I/O names to board names.
    
    LDmicro convention:
    - X prefix for inputs (e.g., XS1, XFOTO, XBTN1)
    - Y prefix for outputs (e.g., YH1, YFAN1)
    
    Board names: S1, FOTO, BTN1, H1, FAN1, etc.
    """
    if not name:
        return name
    
    # Strip X prefix for inputs
    if is_input and name.upper().startswith('X'):
        stripped = name[1:]
        # Check if stripped name matches a board input
        if stripped.upper() in [inp["name"].upper() for inp in BOARD_INPUTS]:
            return stripped.upper()
        # Also try the original (in case XYZ is actually named XYZ)
    
    # Strip Y prefix for outputs
    if not is_input and name.upper().startswith('Y'):
        stripped = name[1:]
        # Check if stripped name matches a board output
        if stripped.upper() in [out["name"].upper() for out in BOARD_OUTPUTS]:
            return stripped.upper()
    
    # Return uppercase version of name
    return name.upper()


def detect_format(source: str) -> str:
    """
    Detect whether the source is C code or ladder diagram text.
    
    Returns: 'c' or 'ladder'
    """
    # Ladder diagram indicators
    ladder_indicators = [
        "LDmicro export text",
        "LADDER DIAGRAM:",
        "I/O ASSIGNMENT:",
        "||-------",
        "] [",
        "]/[",
        "( )",
        "[END]",
    ]
    
    # C code indicators
    c_indicators = [
        "void PlcCycle",
        "void plc_cycle",
        "#include",
        "typedef",
        "SWORD",
        "int main",
    ]
    
    source_lower = source.lower()
    
    # Count matches
    ladder_score = sum(1 for ind in ladder_indicators if ind.lower() in source_lower or ind in source)
    c_score = sum(1 for ind in c_indicators if ind.lower() in source_lower)
    
    return 'ladder' if ladder_score > c_score else 'c'


def transpile_ladder(ladder: LadderProgram) -> SimulationProgram:
    """
    Convert a parsed ladder program to a simulation program.
    """
    program = SimulationProgram()
    program.use_board_layout = True
    program.cycle_time_ms = int(ladder.cycle_time) if ladder.cycle_time else 10
    
    # Build I/O lists from the ladder program's I/O assignments
    # Map ladder names to board names, handling X/Y prefixes
    input_names = []
    output_names = []
    
    for io in ladder.io_assignments:
        if "input" in io.io_type.lower():
            input_names.append(io.name)
        elif "output" in io.io_type.lower():
            output_names.append(io.name)
    
    # Create input mappings (normalize names and map to board)
    # Maps original ladder name -> board index
    input_index_map = {}
    for i, name in enumerate(input_names):
        # Normalize the name (strip X prefix if present)
        normalized = normalize_io_name(name, is_input=True)
        
        # Check if normalized name matches a board input
        if normalized in INPUT_MAP:
            input_index_map[name] = INPUT_MAP[normalized]
        elif name in INPUT_MAP:
            input_index_map[name] = INPUT_MAP[name]
        else:
            # Map to board position based on order, or add extra
            board_idx = i if i < len(BOARD_INPUTS) else i
            input_index_map[name] = board_idx
    
    # Create output mappings
    output_index_map = {}
    for i, name in enumerate(output_names):
        # Normalize the name (strip Y prefix if present)
        normalized = normalize_io_name(name, is_input=False)
        
        if normalized in OUTPUT_MAP:
            output_index_map[name] = OUTPUT_MAP[normalized]
        elif name in OUTPUT_MAP:
            output_index_map[name] = OUTPUT_MAP[name]
        else:
            board_idx = i if i < len(BOARD_OUTPUTS) else i
            output_index_map[name] = board_idx
    
    # Build the JavaScript code
    js_lines = ["function PlcCycle() {"]
    js_lines.append("  // Input mapping")
    js_lines.append(f"  const inputMap = {json.dumps(input_index_map)};")
    js_lines.append("  // Output mapping")
    js_lines.append(f"  const outputMap = {json.dumps(output_index_map)};")
    js_lines.append("")
    
    for rung in ladder.rungs:
        if not rung.contacts and not rung.coils:
            continue
            
        # Build condition from contacts
        conditions = []
        for contact in rung.contacts:
            idx = input_index_map.get(contact.name, 0)
            if contact.normally_closed:
                conditions.append(f"!state.inputs[{idx}]")
            else:
                conditions.append(f"state.inputs[{idx}]")
        
        # Build actions for coils
        if conditions and rung.coils:
            condition_str = " && ".join(conditions)
            js_lines.append(f"  // Rung {rung.number}: {' AND '.join(c.name + ('(NC)' if c.normally_closed else '') for c in rung.contacts)} -> {', '.join(c.name for c in rung.coils)}")
            js_lines.append(f"  if ({condition_str}) {{")
            
            for coil in rung.coils:
                idx = output_index_map.get(coil.name, 0)
                js_lines.append(f"    state.outputs[{idx}] = 1;")
            
            js_lines.append("  } else {")
            
            for coil in rung.coils:
                if coil.coil_type == "OUT":
                    idx = output_index_map.get(coil.name, 0)
                    js_lines.append(f"    state.outputs[{idx}] = 0;")
            
            js_lines.append("  }")
            js_lines.append("")
    
    js_lines.append("}")
    
    program.plc_cycle_js = "\n".join(js_lines)
    
    # Use board layout for inputs/outputs
    program.inputs = [
        IOPin(
            name=inp["name"],
            index=i,
            pin_type="input",
            label=inp["label"],
            component_type=inp["type"],
            color=inp["color"]
        )
        for i, inp in enumerate(BOARD_INPUTS)
    ]
    
    program.outputs = [
        IOPin(
            name=out["name"],
            index=i,
            pin_type="output",
            label=out["label"],
            component_type=out["type"],
            color=out["color"]
        )
        for i, out in enumerate(BOARD_OUTPUTS)
    ]
    
    # Add timers and counters
    program.timers = [
        Timer(name="T0", delay_ms=1000),
        Timer(name="T1", delay_ms=1000),
        Timer(name="T2", delay_ms=1000),
        Timer(name="T3", delay_ms=1000),
    ]
    program.counters = [
        Counter(name="C0", preset=10),
        Counter(name="C1", preset=10),
    ]
    
    return program


def transpile_unified(source: str) -> SimulationProgram:
    """
    Auto-detect format and transpile to simulation program.
    
    Supports:
    - C code exports from LDmicro
    - Text ladder diagram exports from LDmicro
    """
    format_type = detect_format(source)
    
    if format_type == 'ladder':
        # Parse ladder diagram
        ladder = parse_ladder(source)
        return transpile_ladder(ladder)
    else:
        # Parse C code
        return transpile_c(source, use_board_layout=True)


# Export for use in server
__all__ = ['transpile_unified', 'detect_format', 'SimulationProgram']

