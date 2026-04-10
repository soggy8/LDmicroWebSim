import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interpreter.ladder_parser import parse_ladder
from interpreter.unified_transpiler import transpile_ladder


COMPLEX_TEXT = """
LDmicro export text
for 'Microchip PIC16F877 40-PDIP', 8.000000 MHz crystal, 0.5 ms cycle time

LADDER DIAGRAM:
   ||      XPIR                                                                                  R1        ||
 1 ||-------] [------+---------------------------------------------------------------------------( )-------||
   ||                |                                                                           C2        ||
   ||                +--------------------------------------------------------------------------{RES}------||
   ||      R2             [C1 ==]                                                              YFAN1      ||
 2 ||-------] [------+-----[ 0   ]---------------------------------------------------------------( )-------||
   ||                |     [C1 ==]                                                              YFAN2      ||
   ||                +-----[ 1   ]---------------------------------------------------------------( )-------||
   ||                |     [C1 ==]                                                              YFAN3      ||
   ||                +-----[ 2   ]---------------------------------------------------------------( )-------||
   ||      R3               C2                                                                  R4        ||
 3 ||-------] [-----------[CTU >=4]---+----------------------------------------------------------( )-------||
   ||                                 |                                                          R5        ||
   ||                                 +----------------------------------------------------------( )-------||
   ||------[END]----------------------||

I/O ASSIGNMENT:
  Name                       | Type               | Pin
 ----------------------------+--------------------+------
  XPIR                       | Digital input      | 2
  YFAN1                      | Digital output     | 21
  YFAN2                      | Digital output     | 22
  YFAN3                      | Digital output     | 23
  R1                         | int. relay         |
  R2                         | int. relay         |
  R3                         | int. relay         |
  R4                         | int. relay         |
  R5                         | int. relay         |
  C1                         | counter            |
  C2                         | counter            |
""".strip()


def test_complex_text_parses_and_transpiles_features():
    ladder = parse_ladder(COMPLEX_TEXT)
    assert len(ladder.rungs) == 3
    assert ladder.rungs[0].parallel_branches  # RES branch
    assert ladder.rungs[1].parallel_branches  # compare branches

    program = transpile_ladder(ladder)
    js = program.plc_cycle_js
    assert "ctcAction" in js
    assert "ctuCond" in js
    assert "resAction" in js
    assert "rt.counters" in js
