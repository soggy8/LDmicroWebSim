"""
Transpiler for LDmicro text exports.
"""

from dataclasses import dataclass, field, asdict
from typing import Any
import json

from .ladder_parser import parse_ladder, LadderProgram


@dataclass
class IOPin:
    """Represents an I/O pin."""
    name: str
    index: int
    pin_type: str  # 'input' or 'output'
    label: str = ""
    component_type: str = ""
    color: str = ""


@dataclass
class Timer:
    """Represents a timer."""
    name: str
    delay_ms: int = 1000
    timer_type: str = "TON"


@dataclass
class Counter:
    """Represents a counter."""
    name: str
    preset: int = 0
    counter_type: str = "CTU"


@dataclass
class SimulationProgram:
    """Simulation payload consumed by the frontend runtime."""
    inputs: list[IOPin] = field(default_factory=list)
    outputs: list[IOPin] = field(default_factory=list)
    timers: list[Timer] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)
    variables: list[dict[str, Any]] = field(default_factory=list)
    plc_cycle_js: str = ""
    cycle_time_ms: int = 10
    use_board_layout: bool = True

    def to_dict(self) -> dict:
        return {
            "inputs": [asdict(i) for i in self.inputs],
            "outputs": [asdict(o) for o in self.outputs],
            "timers": [asdict(t) for t in self.timers],
            "counters": [asdict(c) for c in self.counters],
            "variables": self.variables,
            "plcCycleJs": self.plc_cycle_js,
            "cycleTimeMs": self.cycle_time_ms,
            "useBoardLayout": self.use_board_layout,
        }


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

# Physical board aliases mapped to canonical simulator I/O names
INPUT_ALIASES = {
    "FOTO1": "FOTO",
    "FOTO2": "SEN",
    "PIR": "MOV",
    "MAG": "TRIG",
    "IND1": "PO1",
    "IND2": "PO2",
    "START1": "BTN1",
    "STOP1": "BTN2",
    "START2": "BTN3",
}
OUTPUT_ALIASES = {
    "BEL": "BELL",
}


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
    name = name.upper()
    
    # Strip X prefix for inputs
    if is_input and name.startswith('X'):
        stripped = name[1:]
        # Check if stripped name matches a board input
        if stripped in INPUT_MAP:
            return INPUT_ALIASES.get(stripped, stripped)
        # Also map aliases on stripped name (e.g. XSTART1 -> BTN1).
        alias = INPUT_ALIASES.get(stripped)
        if alias:
            return alias
        # Also try the original (in case XYZ is actually named XYZ)
    
    # Strip Y prefix for outputs
    if not is_input and name.startswith('Y'):
        stripped = name[1:]
        # Check if stripped name matches a board output
        if stripped in OUTPUT_MAP:
            return OUTPUT_ALIASES.get(stripped, stripped)
        alias = OUTPUT_ALIASES.get(stripped)
        if alias:
            return alias
    
    if is_input:
        return INPUT_ALIASES.get(name, name)
    return OUTPUT_ALIASES.get(name, name)


def transpile_ladder(ladder: LadderProgram) -> SimulationProgram:
    """
    Convert a parsed ladder program to a simulation program.
    """
    program = SimulationProgram()
    program.use_board_layout = True
    program.cycle_time_ms = max(1, int(round(ladder.cycle_time))) if ladder.cycle_time else 10
    
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
    used_output_indexes: set[int] = set()
    for i, name in enumerate(output_names):
        # Normalize the name (strip Y prefix if present)
        normalized = normalize_io_name(name, is_input=False)
        idx = None
        if normalized in OUTPUT_MAP:
            cand = OUTPUT_MAP[normalized]
            if cand not in used_output_indexes:
                idx = cand
        elif name in OUTPUT_MAP:
            cand = OUTPUT_MAP[name]
            if cand not in used_output_indexes:
                idx = cand
        if idx is None:
            board_idx = i if i < len(BOARD_OUTPUTS) else i
            while board_idx in used_output_indexes:
                board_idx += 1
            idx = board_idx
        output_index_map[name] = idx
        used_output_indexes.add(idx)
    
    relay_names = [io.name for io in ladder.io_assignments if "relay" in io.io_type.lower()]
    timer_names = [io.name for io in ladder.io_assignments if "delay" in io.io_type.lower()]
    counter_names = [io.name for io in ladder.io_assignments if "counter" in io.io_type.lower()]

    # Build the JavaScript code
    js_lines = ["function PlcCycle(state) {"]
    js_lines.append("  // Input/output symbol maps from LDmicro names to board indexes.")
    js_lines.append(f"  const inputMap = {json.dumps(input_index_map)};")
    js_lines.append(f"  const outputMap = {json.dumps(output_index_map)};")
    js_lines.append(f"  const relayNames = {json.dumps(relay_names)};")
    js_lines.append(f"  const timerNames = {json.dumps(timer_names)};")
    js_lines.append(f"  const counterNames = {json.dumps(counter_names)};")
    js_lines.append(f"  const cycleMs = {program.cycle_time_ms};")
    js_lines.append("")
    js_lines.append("  const rt = state.__ld || (state.__ld = { relays: {}, timers: {}, counters: {}, edges: {} });")
    js_lines.append("  for (const n of relayNames) if (rt.relays[n] == null) rt.relays[n] = 0;")
    js_lines.append("  for (const n of timerNames) if (!rt.timers[n]) rt.timers[n] = { acc: 0, out: 0 };")
    js_lines.append("  for (const n of counterNames) if (rt.counters[n] == null) rt.counters[n] = 0;")
    js_lines.append("")
    js_lines.append("  const keyRise = (k, on) => { const p = rt.edges[k] ? 1 : 0; rt.edges[k] = on ? 1 : 0; return !!on && !p; };")
    js_lines.append("  const signal = (name) => {")
    js_lines.append("    if (inputMap[name] != null) return state.inputs[inputMap[name]] ? 1 : 0;")
    js_lines.append("    if (outputMap[name] != null) return state.outputs[outputMap[name]] ? 1 : 0;")
    js_lines.append("    if (rt.relays[name] != null) return rt.relays[name] ? 1 : 0;")
    js_lines.append("    return 0;")
    js_lines.append("  };")
    js_lines.append("  const setTarget = (name, v) => {")
    js_lines.append("    if (outputMap[name] != null) state.outputs[outputMap[name]] = v ? 1 : 0;")
    js_lines.append("    else rt.relays[name] = v ? 1 : 0;")
    js_lines.append("  };")
    js_lines.append("  const timerTon = (name, inp, delayMs) => {")
    js_lines.append("    const t = rt.timers[name] || (rt.timers[name] = { acc: 0, out: 0 });")
    js_lines.append("    if (inp) t.acc += cycleMs; else t.acc = 0;")
    js_lines.append("    t.out = t.acc >= delayMs ? 1 : 0;")
    js_lines.append("    return t.out;")
    js_lines.append("  };")
    js_lines.append("  const timerTof = (name, inp, delayMs) => {")
    js_lines.append("    const t = rt.timers[name] || (rt.timers[name] = { acc: 0, out: 0 });")
    js_lines.append("    if (inp) { t.acc = delayMs; t.out = 1; }")
    js_lines.append("    else { t.acc = Math.max(0, t.acc - cycleMs); t.out = t.acc > 0 ? 1 : 0; }")
    js_lines.append("    return t.out;")
    js_lines.append("  };")
    js_lines.append("  const ctuCond = (name, inp, preset) => {")
    js_lines.append("    if (keyRise(`ctu:${name}`, inp)) rt.counters[name] = (rt.counters[name] || 0) + 1;")
    js_lines.append("    return (rt.counters[name] || 0) >= preset ? 1 : 0;")
    js_lines.append("  };")
    js_lines.append("  const ctcAction = (name, inp, lo, hi) => {")
    js_lines.append("    if (!keyRise(`ctc:${name}`, inp)) return;")
    js_lines.append("    const span = Math.max(1, (hi - lo + 1));")
    js_lines.append("    const cur = rt.counters[name] == null ? lo : rt.counters[name];")
    js_lines.append("    const n = lo + (((cur - lo + 1) % span + span) % span);")
    js_lines.append("    rt.counters[name] = n;")
    js_lines.append("  };")
    js_lines.append("  const resAction = (name, inp) => { if (inp) rt.counters[name] = 0; };")
    js_lines.append("")

    for rung in ladder.rungs:
        paths = [rung, *rung.parallel_branches]
        if not paths:
            continue
        js_lines.append(f"  // Rung {rung.number}")
        out_targets: set[str] = set()
        for p in paths:
            for coil in p.coils:
                if coil.coil_type == "OUT":
                    out_targets.add(coil.name)
        for t in sorted(out_targets):
            js_lines.append(f"  let out_{t} = 0;")

        for idx, p in enumerate(paths):
            js_lines.append("  {")
            js_lines.append("    let cond = 1;")
            for c in p.contacts:
                if getattr(c, "kind", "contact") == "compare":
                    op = c.operator or "=="
                    val = c.value if c.value is not None else 0
                    js_lines.append(f"    cond = cond && ((rt.counters[{json.dumps(c.name)}] || 0) {op} {int(val)});")
                else:
                    if c.normally_closed:
                        js_lines.append(f"    cond = cond && !signal({json.dumps(c.name)});")
                    else:
                        js_lines.append(f"    cond = cond && !!signal({json.dumps(c.name)});")
            for t in p.timers:
                tname = json.dumps(t.name)
                delay = int(t.delay)
                if t.timer_type == "TON":
                    js_lines.append(f"    cond = cond && timerTon({tname}, cond, {delay});")
                elif t.timer_type == "TOF":
                    js_lines.append(f"    cond = cond && timerTof({tname}, cond, {delay});")
            for c in p.counters:
                if c.counter_type in ("CTUCOND", "CTDCOND"):
                    js_lines.append(f"    cond = cond && ctuCond({json.dumps(c.name)}, cond, {int(c.preset)});")
            for c in p.counters:
                name = json.dumps(c.name)
                if c.counter_type == "CTC":
                    lo = int(c.min_value if c.min_value is not None else 0)
                    hi = int(c.max_value if c.max_value is not None else max(lo, 1))
                    # Must run every scan to update edge history; ctcAction does its own rising-edge gate.
                    js_lines.append(f"    ctcAction({name}, cond, {lo}, {hi});")
                elif c.counter_type == "RES":
                    js_lines.append(f"    resAction({name}, cond);")
            js_lines.append("    if (cond) {")
            for coil in p.coils:
                target = json.dumps(coil.name)
                if coil.coil_type == "OUT":
                    js_lines.append(f"      out_{coil.name} = 1;")
                elif coil.coil_type == "SET":
                    js_lines.append(f"      setTarget({target}, 1);")
                elif coil.coil_type == "RESET":
                    js_lines.append(f"      setTarget({target}, 0);")
            js_lines.append("    }")
            js_lines.append("  }")

        for t in sorted(out_targets):
            js_lines.append(f"  setTarget({json.dumps(t)}, out_{t});")
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
    Transpile LDmicro text export to simulation program.
    """
    ladder = parse_ladder(source)
    return transpile_ladder(ladder)


# Export for use in server
__all__ = ['transpile_unified', 'transpile_ladder', 'SimulationProgram']

