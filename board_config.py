"""
Board Configuration - Physical PLC Training Board Layout

This defines the exact components on the physical training board.
When writing ladder logic, use these EXACT names to control components.

INPUTS (buttons, switches, sensors):
  - START1, START2    : Green start buttons
  - STOP1, STOP2      : Red stop buttons  
  - SW1, SW2, SW3, SW4: Toggle switches
  - SEN1, SEN2, SEN3  : Sensors (proximity/photo)
  - EMG               : Emergency stop (red mushroom)

OUTPUTS (lights, fans, alarms):
  - H1    : Green indicator light
  - H2    : Yellow indicator light
  - H3    : Red indicator light
  - FAN1  : Cooling fan 1
  - FAN2  : Cooling fan 2
  - FAN3  : Cooling fan 3
  - BEL   : Bell/buzzer
  - BEACON: Red warning beacon
"""

# Board component definitions
BOARD_CONFIG = {
    "name": "PLC Training Board",
    "description": "Програмабилен Логички Управувач - Training Board",
    
    "inputs": [
        # Push buttons
        {"name": "START1", "type": "button", "color": "green", "label": "START 1"},
        {"name": "START2", "type": "button", "color": "green", "label": "START 2"},
        {"name": "STOP1", "type": "button", "color": "red", "label": "STOP 1"},
        {"name": "STOP2", "type": "button", "color": "red", "label": "STOP 2"},
        
        # Toggle switches
        {"name": "SW1", "type": "switch", "color": "black", "label": "SW1"},
        {"name": "SW2", "type": "switch", "color": "black", "label": "SW2"},
        {"name": "SW3", "type": "switch", "color": "black", "label": "SW3"},
        {"name": "SW4", "type": "switch", "color": "black", "label": "SW4"},
        
        # Sensors
        {"name": "SEN1", "type": "sensor", "color": "blue", "label": "SENSOR 1"},
        {"name": "SEN2", "type": "sensor", "color": "blue", "label": "SENSOR 2"},
        {"name": "SEN3", "type": "sensor", "color": "blue", "label": "SENSOR 3"},
        
        # Emergency
        {"name": "EMG", "type": "emergency", "color": "red", "label": "EMERGENCY"},
    ],
    
    "outputs": [
        # Indicator lights
        {"name": "H1", "type": "light", "color": "green", "label": "H1"},
        {"name": "H2", "type": "light", "color": "yellow", "label": "H2"},
        {"name": "H3", "type": "light", "color": "red", "label": "H3"},
        
        # Fans
        {"name": "FAN1", "type": "fan", "color": "gray", "label": "FAN1"},
        {"name": "FAN2", "type": "fan", "color": "gray", "label": "FAN2"},
        {"name": "FAN3", "type": "fan", "color": "gray", "label": "FAN3"},
        
        # Alarms
        {"name": "BEL", "type": "buzzer", "color": "silver", "label": "BELL"},
        {"name": "BEACON", "type": "beacon", "color": "red", "label": "BEACON"},
    ],
    
    "timers": [
        {"name": "T0", "delay_ms": 1000},
        {"name": "T1", "delay_ms": 1000},
        {"name": "T2", "delay_ms": 1000},
        {"name": "T3", "delay_ms": 1000},
    ],
    
    "counters": [
        {"name": "C0", "preset": 10},
        {"name": "C1", "preset": 10},
    ],
}


def get_io_mapping():
    """
    Returns mapping of component names to array indices.
    Use these names in your ladder logic!
    """
    mapping = {
        "inputs": {},
        "outputs": {},
    }
    
    for i, inp in enumerate(BOARD_CONFIG["inputs"]):
        mapping["inputs"][inp["name"]] = i
    
    for i, out in enumerate(BOARD_CONFIG["outputs"]):
        mapping["outputs"][out["name"]] = i
    
    return mapping


def get_board_config():
    """Returns the full board configuration."""
    return BOARD_CONFIG


# Print mapping when run directly
if __name__ == "__main__":
    print("=== PLC Training Board I/O Mapping ===\n")
    
    mapping = get_io_mapping()
    
    print("INPUTS (use these names in ladder code):")
    for name, idx in mapping["inputs"].items():
        inp = BOARD_CONFIG["inputs"][idx]
        print(f"  {name:8} -> index {idx} ({inp['type']})")
    
    print("\nOUTPUTS (use these names in ladder code):")
    for name, idx in mapping["outputs"].items():
        out = BOARD_CONFIG["outputs"][idx]
        print(f"  {name:8} -> index {idx} ({out['type']})")

