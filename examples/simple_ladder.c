/*
 * Example LDmicro C output
 * This simulates a simple ladder diagram with:
 * - Input X0: Start button
 * - Input X1: Stop button  
 * - Output Y0: Motor
 * - Output Y1: Indicator light
 * - Timer T0: Delay timer (1 second)
 */

// Type definitions (LDmicro style)
typedef signed short SWORD;
typedef signed char SBYTE;

// Input pins - directly connected to physical buttons/switches
SWORD Xin[4];

// Output pins - connected to relays/LEDs/motors
SWORD Yout[4];

// Timer state and count arrays
SWORD Tstate[2];
SWORD Tcount[2];

// Counter state and count arrays  
SWORD Cstate[2];
SWORD Ccount[2];

// Internal relay/memory
SWORD Rinternal[4];

// Timer delay values (in PLC cycles)
SWORD Tdelay[2] = {100, 200};  // 100 cycles = 1 second at 10ms cycle

/*
 * Main PLC cycle function
 * Called every scan cycle (typically 10ms)
 * 
 * Ladder Logic:
 * |--[X0]--+--[/X1]--+--------(Y0)--|  Start/Stop circuit with latch
 * |        |         |              |
 * |--[Y0]--+         |              |
 * |                                 |
 * |--[Y0]--[TON T0 1000ms]--(Y1)--| Motor running indicator with delay
 * |                                 |
 * |--[X2]--[CTU C0 10]-----(Y2)--|   Counter output after 10 counts
 */
void PlcCycle(void) {
    // Rung 1: Start/Stop latch circuit
    // X0 = Start button (NO), X1 = Stop button (NC)
    // Y0 latches on when X0 pressed, off when X1 pressed
    if ((Xin[0] || Yout[0]) && !Xin[1]) {
        Yout[0] = 1;
    } else {
        Yout[0] = 0;
    }
    
    // Rung 2: Timer - Turn on Y1 after Y0 has been on for 1 second
    // TON (Timer On-Delay)
    if (Yout[0]) {
        if (Tcount[0] < Tdelay[0]) {
            Tcount[0]++;
        } else {
            Tstate[0] = 1;
        }
    } else {
        Tcount[0] = 0;
        Tstate[0] = 0;
    }
    Yout[1] = Tstate[0];
    
    // Rung 3: Counter - Count rising edges on X2
    // CTU (Count Up)
    if (Xin[2] && !Rinternal[0]) {
        // Rising edge detected
        if (Ccount[0] < 10) {
            Ccount[0]++;
        }
    }
    Rinternal[0] = Xin[2];  // Store previous state
    
    if (Ccount[0] >= 10) {
        Cstate[0] = 1;
        Yout[2] = 1;
    } else {
        Cstate[0] = 0;
        Yout[2] = 0;
    }
    
    // Rung 4: Reset counter when X3 is pressed
    if (Xin[3]) {
        Ccount[0] = 0;
        Cstate[0] = 0;
    }
    
    // Rung 5: Simple AND logic - Y3 on when both X0 and X2 are on
    if (Xin[0] && Xin[2]) {
        Yout[3] = 1;
    } else {
        Yout[3] = 0;
    }
}

/*
 * Hardware interface functions (normally provided by LDmicro)
 * These would read/write actual GPIO pins
 */
void ReadInputs(void) {
    // Read physical input pins into Xin array
    // In simulation, this is handled by the web UI
}

void WriteOutputs(void) {
    // Write Yout array to physical output pins
    // In simulation, this is handled by the web UI
}

/*
 * Main program loop (not used in simulation)
 */
int main(void) {
    // Initialize
    int i;
    for (i = 0; i < 4; i++) {
        Xin[i] = 0;
        Yout[i] = 0;
        Rinternal[i] = 0;
    }
    for (i = 0; i < 2; i++) {
        Tstate[i] = 0;
        Tcount[i] = 0;
        Cstate[i] = 0;
        Ccount[i] = 0;
    }
    
    // Main loop
    while (1) {
        ReadInputs();
        PlcCycle();
        WriteOutputs();
        // Delay would go here (10ms typical)
    }
    
    return 0;
}

