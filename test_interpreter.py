#!/usr/bin/env python3
"""
Test script for the LDmicro interpreter.
Parses example C code and outputs the simulation JSON.
"""

import sys
import os

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from interpreter.lexer import Lexer, tokenize
from interpreter.parser import Parser, parse
from interpreter.transpiler import Transpiler, transpile


def test_lexer(source: str):
    """Test the lexer."""
    print("=" * 60)
    print("LEXER TEST")
    print("=" * 60)
    
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    
    print(f"Generated {len(tokens)} tokens")
    print("\nFirst 20 tokens:")
    for token in tokens[:20]:
        print(f"  {token}")
    print("  ...")
    print()


def test_parser(source: str):
    """Test the parser."""
    print("=" * 60)
    print("PARSER TEST")
    print("=" * 60)
    
    ast = parse(source)
    
    print(f"Parsed {len(ast.declarations)} top-level declarations:\n")
    
    for decl in ast.declarations:
        decl_type = type(decl).__name__
        if hasattr(decl, 'name'):
            print(f"  {decl_type}: {decl.name}")
        else:
            print(f"  {decl_type}")
    print()


def test_transpiler(source: str):
    """Test the transpiler."""
    print("=" * 60)
    print("TRANSPILER TEST")
    print("=" * 60)
    
    program = transpile(source)
    
    print("\n--- Extracted I/O ---")
    print(f"Inputs ({len(program.inputs)}):")
    for inp in program.inputs:
        print(f"  {inp.name} ({inp.label})")
    
    print(f"\nOutputs ({len(program.outputs)}):")
    for out in program.outputs:
        print(f"  {out.name} ({out.label})")
    
    print(f"\nTimers ({len(program.timers)}):")
    for timer in program.timers:
        print(f"  {timer.name} ({timer.timer_type}, {timer.delay_ms}ms)")
    
    print(f"\nCounters ({len(program.counters)}):")
    for counter in program.counters:
        print(f"  {counter.name} ({counter.counter_type})")
    
    print(f"\nVariables ({len(program.variables)}):")
    for var in program.variables:
        arr = f"[{var.array_size}]" if var.is_array else ""
        print(f"  {var.var_type} {var.name}{arr}")
    
    print("\n--- Generated JavaScript ---")
    print(program.plc_cycle_js)
    
    print("\n--- Full JSON Output ---")
    print(program.to_json())


def main():
    # Load example file
    example_path = os.path.join(
        os.path.dirname(__file__),
        'examples',
        'simple_ladder.c'
    )
    
    if not os.path.exists(example_path):
        print(f"Example file not found: {example_path}")
        print("Creating inline example...")
        source = '''
typedef signed short SWORD;
SWORD Xin[4];
SWORD Yout[4];

void PlcCycle(void) {
    if (Xin[0] && !Xin[1]) {
        Yout[0] = 1;
    } else {
        Yout[0] = 0;
    }
}
'''
    else:
        with open(example_path, 'r') as f:
            source = f.read()
        print(f"Loaded: {example_path}")
        print(f"Size: {len(source)} bytes\n")
    
    # Run tests
    test_lexer(source)
    test_parser(source)
    test_transpiler(source)
    
    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED!")
    print("=" * 60)


if __name__ == '__main__':
    main()

