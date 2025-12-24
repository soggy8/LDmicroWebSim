"""
Transpiler for LDmicro C code.
Converts the AST to a simulation-ready JSON format.

Supports NAMED I/O mapping for the physical training board:
  Inputs:  START1, START2, STOP1, STOP2, SW1-SW4, SEN1-SEN3, EMG
  Outputs: H1, H2, H3, FAN1, FAN2, FAN3, BEL, BEACON
"""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any
from .parser import (
    Parser, Program, ASTNode,
    NumberLiteral, Identifier, ArrayAccess, BinaryOp, UnaryOp,
    Assignment, FunctionCall, IfStatement, WhileStatement, ForStatement,
    ReturnStatement, Block, VariableDeclaration, FunctionDeclaration,
    ExpressionStatement
)


# ============================================================================
# Board Configuration - Physical Training Board
# Matches the exact layout of the physical trainer board
#
# ROW 1: FOTO, SEN, MOV, FAN1, FAN2, FAN3
# ROW 2: TRIG, PO1, PO2, H1, H2, H3
# ROW 3: S1, S2, S3, ---, PANIC, BELL
# ROW 4: BTN1, BTN2, BTN3
# ============================================================================

BOARD_INPUTS = [
    # Row 1 - Sensors
    {"name": "FOTO", "type": "sensor", "color": "green", "label": "Light Sensor"},
    {"name": "SEN", "type": "sensor", "color": "blue", "label": "Proximity Sensor"},
    {"name": "MOV", "type": "sensor", "color": "green", "label": "Movement Sensor"},
    # Row 2 - More sensors
    {"name": "TRIG", "type": "sensor", "color": "orange", "label": "Trigger/Door"},
    {"name": "PO1", "type": "sensor", "color": "gray", "label": "Metal Detector 1"},
    {"name": "PO2", "type": "sensor", "color": "gray", "label": "Metal Detector 2"},
    # Row 3 - Light switches
    {"name": "S1", "type": "switch", "color": "white", "label": "Switch 1"},
    {"name": "S2", "type": "switch", "color": "white", "label": "Switch 2"},
    {"name": "S3", "type": "switch", "color": "white", "label": "Switch 3"},
    # Row 4 - Push buttons
    {"name": "BTN1", "type": "button", "color": "green", "label": "Button 1"},
    {"name": "BTN2", "type": "button", "color": "yellow", "label": "Button 2"},
    {"name": "BTN3", "type": "button", "color": "red", "label": "Button 3"},
]

BOARD_OUTPUTS = [
    # Row 1 - Fans
    {"name": "FAN1", "type": "fan", "color": "gray", "label": "Fan 1"},
    {"name": "FAN2", "type": "fan", "color": "gray", "label": "Fan 2"},
    {"name": "FAN3", "type": "fan", "color": "gray", "label": "Fan 3"},
    # Row 2 - Indicator lights
    {"name": "H1", "type": "light", "color": "green", "label": "Green Light"},
    {"name": "H2", "type": "light", "color": "yellow", "label": "Yellow Light"},
    {"name": "H3", "type": "light", "color": "red", "label": "Red Light"},
    # Row 3 - Alarms
    {"name": "PANIC", "type": "strobe", "color": "red", "label": "Panic Strobe"},
    {"name": "BELL", "type": "buzzer", "color": "silver", "label": "Bell"},
]

# Create mappings for name -> index
INPUT_NAME_TO_INDEX = {inp["name"]: i for i, inp in enumerate(BOARD_INPUTS)}
OUTPUT_NAME_TO_INDEX = {out["name"]: i for i, out in enumerate(BOARD_OUTPUTS)}


# ============================================================================
# Simulation Model
# ============================================================================

@dataclass
class IOPin:
    """Represents an I/O pin."""
    name: str
    index: int
    pin_type: str  # 'input' or 'output'
    label: str = ""
    component_type: str = ""  # button, switch, light, fan, etc.
    color: str = ""


@dataclass
class Timer:
    """Represents a timer."""
    name: str
    delay_ms: int = 1000
    timer_type: str = "TON"  # TON, TOF, RTO


@dataclass
class Counter:
    """Represents a counter."""
    name: str
    preset: int = 0
    counter_type: str = "CTU"  # CTU, CTD, CTC


@dataclass
class Variable:
    """Represents a variable."""
    name: str
    var_type: str
    initial_value: Any = 0
    is_array: bool = False
    array_size: int = 0


@dataclass
class SimulationProgram:
    """The complete simulation program."""
    inputs: list[IOPin] = field(default_factory=list)
    outputs: list[IOPin] = field(default_factory=list)
    timers: list[Timer] = field(default_factory=list)
    counters: list[Counter] = field(default_factory=list)
    variables: list[Variable] = field(default_factory=list)
    plc_cycle_js: str = ""
    cycle_time_ms: int = 10
    use_board_layout: bool = True  # Use fixed board layout
    
    def to_dict(self) -> dict:
        return {
            'inputs': [asdict(i) for i in self.inputs],
            'outputs': [asdict(o) for o in self.outputs],
            'timers': [asdict(t) for t in self.timers],
            'counters': [asdict(c) for c in self.counters],
            'variables': [asdict(v) for v in self.variables],
            'plcCycleJs': self.plc_cycle_js,
            'cycleTimeMs': self.cycle_time_ms,
            'useBoardLayout': self.use_board_layout,
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ============================================================================
# Transpiler
# ============================================================================

class Transpiler:
    """
    Transpiles LDmicro C code AST to simulation-ready format.
    
    This extracts:
    - I/O declarations (Xin, Yout arrays)
    - Timers and counters
    - The PlcCycle function (converted to JavaScript)
    """
    
    # Common LDmicro variable patterns
    INPUT_PATTERNS = [
        r'^Xin$', r'^X\d+$', r'^I\d+$', r'^Uin$',
    ]
    OUTPUT_PATTERNS = [
        r'^Yout$', r'^Y\d+$', r'^Q\d+$', r'^Uout$',
    ]
    TIMER_PATTERNS = [
        r'^T\d+$', r'^TON\d*$', r'^TOF\d*$', r'^Tstate$', r'^Tcount$',
    ]
    COUNTER_PATTERNS = [
        r'^C\d+$', r'^CTU\d*$', r'^CTD\d*$', r'^Cstate$', r'^Ccount$',
    ]
    
    def __init__(self, ast: Program):
        self.ast = ast
        self.program = SimulationProgram()
        self.seen_vars: set[str] = set()
        self.seen_timers: set[str] = set()
        self.seen_counters: set[str] = set()
    
    @classmethod
    def from_source(cls, source: str) -> 'Transpiler':
        """Create a transpiler from source code."""
        parser = Parser.from_source(source)
        ast = parser.parse()
        return cls(ast)
    
    def transpile(self) -> SimulationProgram:
        """Transpile the AST to a simulation program."""
        # First pass: extract declarations
        for decl in self.ast.declarations:
            self.process_declaration(decl)
        
        # Second pass: find and convert PlcCycle
        for decl in self.ast.declarations:
            if isinstance(decl, FunctionDeclaration):
                if decl.name in ('PlcCycle', 'plc_cycle', 'PLC_CYCLE'):
                    self.program.plc_cycle_js = self.convert_function_to_js(decl)
        
        return self.program
    
    def process_declaration(self, decl: ASTNode):
        """Process a declaration and extract simulation elements."""
        if isinstance(decl, VariableDeclaration):
            self.process_variable(decl)
        elif isinstance(decl, FunctionDeclaration):
            # We'll process functions in the second pass
            pass
    
    def process_variable(self, decl: VariableDeclaration):
        """Process a variable declaration."""
        name = decl.name
        
        if name in self.seen_vars:
            return
        self.seen_vars.add(name)
        
        # Check if it's an input array
        if self.matches_patterns(name, self.INPUT_PATTERNS):
            if decl.is_array and decl.array_size:
                for i in range(decl.array_size):
                    self.program.inputs.append(IOPin(
                        name=f"{name}[{i}]",
                        index=i,
                        pin_type='input',
                        label=f"X{i}"
                    ))
            else:
                self.program.inputs.append(IOPin(
                    name=name,
                    index=len(self.program.inputs),
                    pin_type='input',
                    label=name
                ))
            return
        
        # Check if it's an output array
        if self.matches_patterns(name, self.OUTPUT_PATTERNS):
            if decl.is_array and decl.array_size:
                for i in range(decl.array_size):
                    self.program.outputs.append(IOPin(
                        name=f"{name}[{i}]",
                        index=i,
                        pin_type='output',
                        label=f"Y{i}"
                    ))
            else:
                self.program.outputs.append(IOPin(
                    name=name,
                    index=len(self.program.outputs),
                    pin_type='output',
                    label=name
                ))
            return
        
        # Check if it's a timer-related variable
        if self.matches_patterns(name, self.TIMER_PATTERNS):
            if decl.is_array and decl.array_size:
                for i in range(decl.array_size):
                    timer_name = f"T{i}"
                    if timer_name not in self.seen_timers:
                        self.seen_timers.add(timer_name)
                        self.program.timers.append(Timer(
                            name=timer_name,
                            delay_ms=1000
                        ))
            else:
                if name not in self.seen_timers:
                    self.seen_timers.add(name)
                    self.program.timers.append(Timer(name=name))
            return
        
        # Check if it's a counter-related variable
        if self.matches_patterns(name, self.COUNTER_PATTERNS):
            if decl.is_array and decl.array_size:
                for i in range(decl.array_size):
                    counter_name = f"C{i}"
                    if counter_name not in self.seen_counters:
                        self.seen_counters.add(counter_name)
                        self.program.counters.append(Counter(
                            name=counter_name,
                            preset=0
                        ))
            else:
                if name not in self.seen_counters:
                    self.seen_counters.add(name)
                    self.program.counters.append(Counter(name=name))
            return
        
        # Regular variable
        self.program.variables.append(Variable(
            name=name,
            var_type=decl.type_name,
            is_array=decl.is_array,
            array_size=decl.array_size or 0
        ))
    
    def matches_patterns(self, name: str, patterns: list[str]) -> bool:
        """Check if name matches any of the patterns."""
        for pattern in patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return True
        return False
    
    # ========================================================================
    # JavaScript Code Generation
    # ========================================================================
    
    def convert_function_to_js(self, func: FunctionDeclaration) -> str:
        """Convert a function declaration to JavaScript."""
        if not func.body:
            return ""
        
        lines = []
        lines.append(f"function {func.name}() {{")
        
        for stmt in func.body:
            js_code = self.convert_statement_to_js(stmt, indent=1)
            if js_code:
                lines.append(js_code)
        
        lines.append("}")
        return '\n'.join(lines)
    
    def convert_statement_to_js(self, stmt: ASTNode, indent: int = 0) -> str:
        """Convert a statement to JavaScript."""
        prefix = "  " * indent
        
        if isinstance(stmt, ExpressionStatement):
            expr = self.convert_expr_to_js(stmt.expression)
            return f"{prefix}{expr};"
        
        if isinstance(stmt, IfStatement):
            cond = self.convert_expr_to_js(stmt.condition)
            lines = [f"{prefix}if ({cond}) {{"]
            
            for s in stmt.then_body:
                js = self.convert_statement_to_js(s, indent + 1)
                if js:
                    lines.append(js)
            
            if stmt.else_body:
                lines.append(f"{prefix}}} else {{")
                for s in stmt.else_body:
                    js = self.convert_statement_to_js(s, indent + 1)
                    if js:
                        lines.append(js)
            
            lines.append(f"{prefix}}}")
            return '\n'.join(lines)
        
        if isinstance(stmt, WhileStatement):
            cond = self.convert_expr_to_js(stmt.condition)
            lines = [f"{prefix}while ({cond}) {{"]
            
            for s in stmt.body:
                js = self.convert_statement_to_js(s, indent + 1)
                if js:
                    lines.append(js)
            
            lines.append(f"{prefix}}}")
            return '\n'.join(lines)
        
        if isinstance(stmt, ForStatement):
            init = self.convert_expr_to_js(stmt.init) if stmt.init else ""
            cond = self.convert_expr_to_js(stmt.condition) if stmt.condition else ""
            update = self.convert_expr_to_js(stmt.update) if stmt.update else ""
            
            lines = [f"{prefix}for ({init}; {cond}; {update}) {{"]
            
            for s in stmt.body:
                js = self.convert_statement_to_js(s, indent + 1)
                if js:
                    lines.append(js)
            
            lines.append(f"{prefix}}}")
            return '\n'.join(lines)
        
        if isinstance(stmt, Block):
            lines = [f"{prefix}{{"]
            for s in stmt.statements:
                js = self.convert_statement_to_js(s, indent + 1)
                if js:
                    lines.append(js)
            lines.append(f"{prefix}}}")
            return '\n'.join(lines)
        
        if isinstance(stmt, ReturnStatement):
            if stmt.value:
                val = self.convert_expr_to_js(stmt.value)
                return f"{prefix}return {val};"
            return f"{prefix}return;"
        
        if isinstance(stmt, VariableDeclaration):
            if stmt.initial_value:
                if isinstance(stmt.initial_value, list):
                    vals = [self.convert_expr_to_js(v) for v in stmt.initial_value]
                    return f"{prefix}let {stmt.name} = [{', '.join(vals)}];"
                val = self.convert_expr_to_js(stmt.initial_value)
                return f"{prefix}let {stmt.name} = {val};"
            elif stmt.is_array and stmt.array_size:
                return f"{prefix}let {stmt.name} = new Array({stmt.array_size}).fill(0);"
            return f"{prefix}let {stmt.name} = 0;"
        
        return ""
    
    def convert_expr_to_js(self, expr: ASTNode) -> str:
        """Convert an expression to JavaScript."""
        if expr is None:
            return ""
        
        if isinstance(expr, NumberLiteral):
            return str(expr.value)
        
        if isinstance(expr, Identifier):
            # Map LDmicro-specific names to our simulation state
            name = expr.name
            return self.map_identifier(name)
        
        if isinstance(expr, ArrayAccess):
            array = self.convert_expr_to_js(expr.array)
            index = self.convert_expr_to_js(expr.index)
            return f"{array}[{index}]"
        
        if isinstance(expr, BinaryOp):
            left = self.convert_expr_to_js(expr.left)
            right = self.convert_expr_to_js(expr.right)
            op = expr.operator
            
            # JavaScript uses same operators as C for most cases
            return f"({left} {op} {right})"
        
        if isinstance(expr, UnaryOp):
            operand = self.convert_expr_to_js(expr.operand)
            op = expr.operator
            
            if expr.prefix:
                return f"({op}{operand})"
            else:
                return f"({operand}{op})"
        
        if isinstance(expr, Assignment):
            target = self.convert_expr_to_js(expr.target)
            value = self.convert_expr_to_js(expr.value)
            op = expr.operator
            return f"{target} {op} {value}"
        
        if isinstance(expr, FunctionCall):
            args = [self.convert_expr_to_js(a) for a in expr.arguments]
            name = self.map_function_call(expr.name)
            return f"{name}({', '.join(args)})"
        
        return str(expr)
    
    def map_identifier(self, name: str) -> str:
        """Map C identifiers to JavaScript simulation state."""
        # Check if it's a named INPUT (START1, STOP1, SW1, etc.)
        if name in INPUT_NAME_TO_INDEX:
            idx = INPUT_NAME_TO_INDEX[name]
            return f'state.inputs[{idx}]'
        
        # Check if it's a named OUTPUT (H1, FAN1, BEL, etc.)
        if name in OUTPUT_NAME_TO_INDEX:
            idx = OUTPUT_NAME_TO_INDEX[name]
            return f'state.outputs[{idx}]'
        
        # Map common LDmicro array names
        mappings = {
            'Xin': 'state.inputs',
            'Yout': 'state.outputs',
            'Tstate': 'state.timers',
            'Tcount': 'state.timerCounts',
            'Cstate': 'state.counters',
            'Ccount': 'state.counterCounts',
            'Rinternal': 'state.internals',
            'Tdelay': 'state.timerDelays',
        }
        return mappings.get(name, name)
    
    def map_function_call(self, name: str) -> str:
        """Map C function calls to JavaScript runtime functions."""
        mappings = {
            # Timer functions
            'Read_U_b_I_0': 'runtime.readInput',
            'Write_U_b_Y_0': 'runtime.writeOutput',
        }
        return mappings.get(name, name)


def transpile(source: str, use_board_layout: bool = True) -> SimulationProgram:
    """
    Transpile source code to simulation program.
    
    Args:
        source: The C source code
        use_board_layout: If True, use the fixed training board layout
    """
    transpiler = Transpiler.from_source(source)
    program = transpiler.transpile()
    
    if use_board_layout:
        # Use the fixed board components instead of auto-detected ones
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
        program.use_board_layout = True
        
        # Default timers and counters
        if not program.timers:
            program.timers = [
                Timer(name="T0", delay_ms=1000),
                Timer(name="T1", delay_ms=1000),
                Timer(name="T2", delay_ms=1000),
                Timer(name="T3", delay_ms=1000),
            ]
        if not program.counters:
            program.counters = [
                Counter(name="C0", preset=10),
                Counter(name="C1", preset=10),
            ]
    
    return program

