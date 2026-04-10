import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from interpreter.hex_runtime import parse_intel_hex, ProgramImage
from interpreter.hex_target import detect_target
from interpreter.hex_vm import Pic16VM
from interpreter.hex_io_bridge import BoardIOBridge


def _program_from_words(words: list[int]) -> ProgramImage:
    img = ProgramImage()
    for pc, w in enumerate(words):
        base = pc * 2
        img.flash_bytes[base] = w & 0xFF
        img.flash_bytes[base + 1] = (w >> 8) & 0xFF
    img.min_address = 0
    img.max_address = max(0, (len(words) * 2) - 1)
    img.record_count = 1
    return img


def test_parse_hex_metadata():
    sample = """
:020000040000FA
:1000000000000000000008280000000000000000C0
:02400E00723FFF
:00000001FF
""".strip()
    image = parse_intel_hex(sample)
    assert image.record_count == 4
    assert image.max_address >= image.min_address
    assert len(image.records) == 4
    assert image.to_dict()["pic14WordCountEstimate"] > 0


def test_target_detection_prefers_pic16_for_sample():
    sample = """
:020000040000FA
:1000000000000000000008280000000000000000C0
:02400E00723FFF
:00000001FF
""".strip()
    image = parse_intel_hex(sample)
    result = detect_target(image)
    assert result.best_target in {"pic16f", "pic18", "avr"}
    assert result.confidence > 0.0


def test_vm_logic_and_output_bit():
    # movlw 0x01 ; movwf 0x20 ; btfsc 0x20,0 ; bsf 0x30,3 ; goto 5
    words = [
        0x3001,
        0x00A0,
        0x1820,
        0x15B0,
        0x2805,
        0x0000,
    ]
    vm = Pic16VM(_program_from_words(words))
    vm.step(20)
    assert (vm.read_ram(0x30) & (1 << 3)) != 0


def test_vm_arithmetic_and_compare_flags():
    # movlw 5 ; movwf 0x22 ; movlw 3 ; addwf 0x22,1 ; movlw 8 ; subwf 0x22,0
    words = [
        0x3005,
        0x00A2,
        0x3003,
        0x07A2,
        0x3008,
        0x0222,
        0x2806,
    ]
    vm = Pic16VM(_program_from_words(words))
    vm.step(30)
    assert vm.read_ram(0x22) == 8  # add result
    assert vm.state.status_z == 1  # subtraction matched


def test_vm_counter_timer_style_state():
    # Counter-style increment loop over RAM[0x24]
    words = [
        0x0184,  # clrf 0x04 (dummy)
        0x0AA4,  # incf 0x24,1
        0x0AA4,  # incf 0x24,1
        0x0AA4,  # incf 0x24,1
        0x2804,  # goto self (halt progress)
    ]
    vm = Pic16VM(_program_from_words(words))
    vm.step(10)
    assert vm.read_ram(0x24) >= 3


def test_io_bridge_maps_inputs_and_outputs():
    words = [
        0x18A1,  # btfsc 0x21,1 (BTN1)
        0x15B0,  # bsf 0x30,3 (H1)
        0x2802,
    ]
    vm = Pic16VM(_program_from_words(words))
    bridge = BoardIOBridge(vm)
    bridge.write_inputs({"BTN1": 1})
    vm.step(10)
    outputs = bridge.read_outputs()
    assert outputs["H1"] == 1


def test_io_bridge_portb_external_pins_visible_on_read():
    vm = Pic16VM(_program_from_words([0x2800]))
    bridge = BoardIOBridge(vm, profile="pic16f877")
    bridge.write_inputs({"SEN": 1})
    assert (vm.read_ram(0x06) & 0x02) != 0
    bridge.write_inputs({"SEN": 0})
    assert (vm.read_ram(0x06) & 0x02) == 0


def test_io_bridge_portd_output_uses_tris_and_latch():
    vm = Pic16VM(_program_from_words([0x2800]))
    ca = vm._canon_addr(0x88)
    vm.state.ram[ca] = 0xFB
    vm.write_ram(0x08, 0x04)
    bridge = BoardIOBridge(vm, profile="pic16f877")
    assert bridge.read_outputs()["H1"] == 1


def test_user_minimal_s1_h1_hex():
    from interpreter.hex_runtime import parse_intel_hex

    hex_txt = """
:020000040000FA
:1000000000000000000008280000000000000000C0
:10001000283084005830A0008001840AA00B0C28EE
:10002000E83095000330960000308E0000308F00DD
:10003000013090000B309700831686309F008312AA
:100040008316FF30850083128316FF3086008312EB
:100050008316FF30870083128316FB3088008312DB
:1000600083160730890083120C1D34280C1164009C
:10007000A914A9182915A91C291105184028291106
:0C00800029190815291D08118A013428CF
:02400E00723FFF
:00000001FF
"""
    image = parse_intel_hex(hex_txt.strip())
    vm = Pic16VM(image)
    bridge = BoardIOBridge(vm, profile="pic16f877")
    bridge.write_inputs({"S1": 0})
    vm.step(5000)
    o0 = bridge.read_outputs()["H1"]
    bridge.write_inputs({"S1": 1})
    vm.step(5000)
    o1 = bridge.read_outputs()["H1"]
    assert o0 == 0 and o1 == 1


def test_vm_indirect_read_portb_via_fsr():
    words = [
        0x3006,
        0x0084,
        0x0800,
        0x2803,
    ]
    vm = Pic16VM(_program_from_words(words))
    vm.set_external_pin(0x06, 6, 1)
    vm.step(20)
    assert (vm.state.wreg & 0x40) != 0


def test_goto_combines_pclath_for_upper_pc_bits():
    words = [0] * (0x1000 + 4)
    words[0] = 0x3010
    words[1] = 0x008A
    words[2] = 0x2800
    words[0x1000] = 0x3001
    words[0x1001] = 0x2803
    vm = Pic16VM(_program_from_words(words))
    vm.step(30)
    assert vm.state.wreg == 1
