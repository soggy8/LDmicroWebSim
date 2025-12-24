/**
 * LDmicro Web Simulator - Physical Board Simulation Engine
 * 
 * BOARD LAYOUT (matching physical trainer):
 * 
 * ROW 1: FOTO, SEN, MOV, FAN1, FAN2, FAN3
 * ROW 2: TRIG, PO1, PO2, H1, H2, H3
 * ROW 3: S1, S2, S3, ---, PANIC, BELL
 * ROW 4: BTN1, BTN2, BTN3
 * 
 * INPUTS:
 *   FOTO - Light sensor (click to toggle)
 *   SEN  - Proximity sensor (click to toggle)
 *   MOV  - Movement sensor (click to toggle)
 *   TRIG - Trigger/door sensor (click to toggle)
 *   PO1  - Metal detector 1 (click to toggle)
 *   PO2  - Metal detector 2 (click to toggle)
 *   S1, S2, S3 - Light switches (toggle on/off)
 *   BTN1, BTN2, BTN3 - Push buttons (hold to activate)
 * 
 * OUTPUTS:
 *   FAN1, FAN2, FAN3 - Cooling fans
 *   H1 - Green indicator light
 *   H2 - Yellow indicator light
 *   H3 - Red indicator light
 *   PANIC - Strobe panic light
 *   BELL - Emergency bell
 */

// Board configuration - matches the physical training board exactly
const BOARD_CONFIG = {
    inputs: [
        // Row 1 - Sensors
        { name: "FOTO", type: "sensor", description: "Light sensor" },
        { name: "SEN", type: "sensor", description: "Proximity sensor" },
        { name: "MOV", type: "sensor", description: "Movement sensor" },
        // Row 2 - More sensors
        { name: "TRIG", type: "sensor", description: "Trigger/door sensor" },
        { name: "PO1", type: "sensor", description: "Metal detector 1" },
        { name: "PO2", type: "sensor", description: "Metal detector 2" },
        // Row 3 - Switches
        { name: "S1", type: "switch", description: "Light switch 1" },
        { name: "S2", type: "switch", description: "Light switch 2" },
        { name: "S3", type: "switch", description: "Light switch 3" },
        // Row 4 - Buttons
        { name: "BTN1", type: "button", description: "Push button 1 (green)" },
        { name: "BTN2", type: "button", description: "Push button 2 (yellow)" },
        { name: "BTN3", type: "button", description: "Push button 3 (red)" },
    ],
    outputs: [
        // Row 1 - Fans
        { name: "FAN1", type: "fan" },
        { name: "FAN2", type: "fan" },
        { name: "FAN3", type: "fan" },
        // Row 2 - Indicator lights
        { name: "H1", type: "light", color: "green" },
        { name: "H2", type: "light", color: "yellow" },
        { name: "H3", type: "light", color: "red" },
        // Row 3 - Alarms
        { name: "PANIC", type: "strobe" },
        { name: "BELL", type: "buzzer" },
    ]
};

class PLCSimulator {
    constructor() {
        // Simulation state - fixed size based on board config
        this.state = {
            inputs: new Array(BOARD_CONFIG.inputs.length).fill(0),
            outputs: new Array(BOARD_CONFIG.outputs.length).fill(0),
            timers: [0, 0, 0, 0],
            timerCounts: [0, 0, 0, 0],
            timerDelays: [100, 100, 100, 100],
            counters: [0, 0],
            counterCounts: [0, 0],
            internals: new Array(16).fill(0),
        };
        
        // Name to index mapping
        this.inputMap = {};
        this.outputMap = {};
        BOARD_CONFIG.inputs.forEach((inp, i) => this.inputMap[inp.name] = i);
        BOARD_CONFIG.outputs.forEach((out, i) => this.outputMap[out.name] = i);
        
        // Simulation config
        this.config = null;
        this.plcCycleFunction = null;
        this.isRunning = false;
        this.cycleCount = 0;
        this.cycleTime = 50; // ms
        this.intervalId = null;
        
        // DOM elements
        this.elements = {};
        
        // Initialize
        this.init();
    }
    
    init() {
        this.cacheElements();
        this.bindEvents();
        this.bindBoardEvents();
        this.updateLineNumbers();
    }
    
    cacheElements() {
        this.elements = {
            codeEditor: document.getElementById('codeEditor'),
            lineNumbers: document.getElementById('lineNumbers'),
            compileBtn: document.getElementById('compileBtn'),
            compileStatus: document.getElementById('compileStatus'),
            loadExampleBtn: document.getElementById('loadExampleBtn'),
            fileInput: document.getElementById('fileInput'),
            runBtn: document.getElementById('runBtn'),
            stepBtn: document.getElementById('stepBtn'),
            stopBtn: document.getElementById('stopBtn'),
            resetBtn: document.getElementById('resetBtn'),
            speedSlider: document.getElementById('speedSlider'),
            speedValue: document.getElementById('speedValue'),
            cycleCount: document.getElementById('cycleCount'),
            statusIndicator: document.getElementById('statusIndicator'),
            statusText: document.querySelector('.status-text'),
            timerStatus: document.getElementById('timerStatus'),
            counterStatus: document.getElementById('counterStatus'),
        };
    }
    
    bindEvents() {
        // Code editor
        this.elements.codeEditor.addEventListener('input', () => this.updateLineNumbers());
        this.elements.codeEditor.addEventListener('scroll', () => this.syncScroll());
        this.elements.codeEditor.addEventListener('keydown', (e) => this.handleTab(e));
        
        // Buttons
        this.elements.compileBtn.addEventListener('click', () => this.compile());
        this.elements.loadExampleBtn.addEventListener('click', () => this.loadExample());
        this.elements.fileInput.addEventListener('change', (e) => this.handleFileUpload(e));
        this.elements.runBtn.addEventListener('click', () => this.run());
        this.elements.stepBtn.addEventListener('click', () => this.step());
        this.elements.stopBtn.addEventListener('click', () => this.stop());
        this.elements.resetBtn.addEventListener('click', () => this.reset());
        
        // Speed slider
        this.elements.speedSlider.addEventListener('input', (e) => {
            this.cycleTime = 101 - parseInt(e.target.value);
            this.elements.speedValue.textContent = `${this.cycleTime}ms`;
            
            if (this.isRunning) {
                this.stop();
                this.run();
            }
        });
    }
    
    bindBoardEvents() {
        // Push buttons (momentary - BTN1, BTN2, BTN3)
        document.querySelectorAll('.push-button[data-input]').forEach(btn => {
            const inputName = btn.dataset.input;
            const idx = this.inputMap[inputName];
            
            // Mouse events
            btn.addEventListener('mousedown', () => this.setInput(idx, 1, btn));
            btn.addEventListener('mouseup', () => this.setInput(idx, 0, btn));
            btn.addEventListener('mouseleave', () => {
                if (this.state.inputs[idx] === 1) {
                    this.setInput(idx, 0, btn);
                }
            });
            
            // Touch events
            btn.addEventListener('touchstart', (e) => {
                e.preventDefault();
                this.setInput(idx, 1, btn);
            });
            btn.addEventListener('touchend', (e) => {
                e.preventDefault();
                this.setInput(idx, 0, btn);
            });
        });
        
        // Light switches (latching - S1, S2, S3)
        document.querySelectorAll('.light-switch[data-input]').forEach(sw => {
            const inputName = sw.dataset.input;
            const idx = this.inputMap[inputName];
            const checkbox = sw.querySelector('input');
            
            checkbox.addEventListener('change', () => {
                const value = checkbox.checked ? 1 : 0;
                this.setInput(idx, value, sw);
            });
        });
        
        // Sensors (click to toggle - FOTO, SEN, MOV, TRIG, PO1, PO2)
        document.querySelectorAll('.sensor-box[data-input]').forEach(sensor => {
            const inputName = sensor.dataset.input;
            const idx = this.inputMap[inputName];
            
            sensor.addEventListener('click', () => {
                const newValue = this.state.inputs[idx] ? 0 : 1;
                this.setInput(idx, newValue, sensor);
            });
        });
    }
    
    // ========================================================================
    // Code Editor
    // ========================================================================
    
    updateLineNumbers() {
        const lines = this.elements.codeEditor.value.split('\n');
        const numbers = lines.map((_, i) => i + 1).join('\n');
        this.elements.lineNumbers.textContent = numbers;
    }
    
    syncScroll() {
        this.elements.lineNumbers.scrollTop = this.elements.codeEditor.scrollTop;
    }
    
    handleTab(e) {
        if (e.key === 'Tab') {
            e.preventDefault();
            const start = this.elements.codeEditor.selectionStart;
            const end = this.elements.codeEditor.selectionEnd;
            const value = this.elements.codeEditor.value;
            
            this.elements.codeEditor.value = value.substring(0, start) + '    ' + value.substring(end);
            this.elements.codeEditor.selectionStart = this.elements.codeEditor.selectionEnd = start + 4;
            this.updateLineNumbers();
        }
    }
    
    // ========================================================================
    // API Communication
    // ========================================================================
    
    async loadExample() {
        const exampleCode = `/*
 * Example: Automatic Fan Control with Sensors
 * 
 * - FOTO (light sensor) controls H1 (green light)
 * - MOV (motion sensor) turns on FAN1
 * - BTN1 starts FAN2, BTN3 stops it (with latch)
 * - S1 switch controls H2 (yellow light)
 * - TRIG sensor activates PANIC and BELL
 */

void PlcCycle(void) {
    // Light sensor controls green indicator
    if (FOTO) {
        H1 = 1;
    } else {
        H1 = 0;
    }
    
    // Motion sensor controls FAN1
    if (MOV) {
        FAN1 = 1;
    } else {
        FAN1 = 0;
    }
    
    // Start/Stop latch for FAN2
    // BTN1 (green) = Start, BTN3 (red) = Stop
    if ((BTN1 || FAN2) && !BTN3) {
        FAN2 = 1;
    } else {
        FAN2 = 0;
    }
    
    // Switch S1 controls yellow light
    if (S1) {
        H2 = 1;
    } else {
        H2 = 0;
    }
    
    // Switch S2 controls FAN3
    if (S2) {
        FAN3 = 1;
    } else {
        FAN3 = 0;
    }
    
    // Trigger sensor (door) activates alarm
    if (TRIG) {
        PANIC = 1;
        BELL = 1;
        H3 = 1;  // Red warning light
    } else {
        PANIC = 0;
        BELL = 0;
        H3 = 0;
    }
    
    // Metal detectors PO1/PO2 - both needed for H3
    if (PO1 && PO2) {
        // Both metal detectors active
    }
}`;
        
        this.elements.codeEditor.value = exampleCode;
        this.updateLineNumbers();
        this.setStatus('Ready', 'ready');
        this.setCompileStatus('Example loaded - click Compile', '');
    }
    
    handleFileUpload(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        const reader = new FileReader();
        reader.onload = (e) => {
            this.elements.codeEditor.value = e.target.result;
            this.updateLineNumbers();
            this.setCompileStatus(`Loaded: ${file.name}`, '');
        };
        reader.readAsText(file);
    }
    
    async compile() {
        const sourceCode = this.elements.codeEditor.value.trim();
        
        if (!sourceCode) {
            this.setCompileStatus('Please enter some C code', 'error');
            return;
        }
        
        try {
            this.setStatus('Compiling...', 'running');
            this.setCompileStatus('Compiling...', '');
            
            const response = await fetch('/api/compile', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ source_code: sourceCode })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.loadSimulation(data.simulation);
                this.setStatus('Ready', 'ready');
                this.setCompileStatus('✓ Compilation successful', 'success');
                this.enableControls(true);
            } else {
                this.setStatus('Error', 'error');
                this.setCompileStatus('✗ ' + data.message, 'error');
            }
        } catch (error) {
            this.setStatus('Error', 'error');
            this.setCompileStatus('✗ Network error: ' + error.message, 'error');
        }
    }
    
    // ========================================================================
    // Simulation Setup
    // ========================================================================
    
    loadSimulation(config) {
        this.config = config;
        
        // Reset state
        this.state.inputs.fill(0);
        this.state.outputs.fill(0);
        this.state.timers.fill(0);
        this.state.timerCounts.fill(0);
        this.state.counters.fill(0);
        this.state.counterCounts.fill(0);
        this.state.internals.fill(0);
        
        // Create the PlcCycle function from the generated JavaScript
        try {
            const functionBody = config.plcCycleJs.replace('function PlcCycle()', '');
            this.plcCycleFunction = new Function('state', functionBody);
            console.log('Generated JS:', config.plcCycleJs);
        } catch (error) {
            console.error('Failed to create PlcCycle function:', error);
            this.setCompileStatus('✗ Invalid generated code: ' + error.message, 'error');
            return;
        }
        
        // Reset UI
        this.resetBoardUI();
        this.updateStatusDisplay();
        
        this.cycleCount = 0;
        this.elements.cycleCount.textContent = '0';
    }
    
    resetBoardUI() {
        // Reset all input visuals
        document.querySelectorAll('.push-button').forEach(btn => {
            btn.classList.remove('active');
        });
        
        document.querySelectorAll('.light-switch').forEach(sw => {
            sw.classList.remove('active');
            sw.querySelector('input').checked = false;
        });
        
        document.querySelectorAll('.sensor-box').forEach(sensor => {
            sensor.classList.remove('active');
        });
        
        // Reset all output visuals
        this.updateOutputDisplay();
    }
    
    // ========================================================================
    // Simulation Control
    // ========================================================================
    
    setInput(index, value, element) {
        this.state.inputs[index] = value;
        
        // Update visual
        if (element) {
            element.classList.toggle('active', value === 1);
        }
        
        // If not running, do a step to show immediate feedback
        if (!this.isRunning && this.plcCycleFunction) {
            this.executeCycle();
        }
    }
    
    run() {
        if (this.isRunning) return;
        
        this.isRunning = true;
        this.setStatus('Running', 'running');
        this.elements.runBtn.disabled = true;
        this.elements.stopBtn.disabled = false;
        
        this.intervalId = setInterval(() => {
            this.executeCycle();
        }, this.cycleTime);
    }
    
    stop() {
        if (!this.isRunning) return;
        
        this.isRunning = false;
        this.setStatus('Stopped', 'ready');
        this.elements.runBtn.disabled = false;
        this.elements.stopBtn.disabled = true;
        
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
    }
    
    step() {
        if (this.isRunning) {
            this.stop();
        }
        this.executeCycle();
    }
    
    reset() {
        this.stop();
        
        // Reset all state
        this.state.inputs.fill(0);
        this.state.outputs.fill(0);
        this.state.timers.fill(0);
        this.state.timerCounts.fill(0);
        this.state.counters.fill(0);
        this.state.counterCounts.fill(0);
        this.state.internals.fill(0);
        
        this.cycleCount = 0;
        this.elements.cycleCount.textContent = '0';
        
        // Reset UI
        this.resetBoardUI();
        this.updateStatusDisplay();
        
        this.setStatus('Reset', 'ready');
    }
    
    executeCycle() {
        if (!this.plcCycleFunction) return;
        
        try {
            // Execute the PLC cycle
            this.plcCycleFunction(this.state);
            
            // Update cycle count
            this.cycleCount++;
            this.elements.cycleCount.textContent = this.cycleCount.toLocaleString();
            
            // Update displays
            this.updateOutputDisplay();
            this.updateStatusDisplay();
        } catch (error) {
            console.error('Cycle execution error:', error);
            this.stop();
            this.setStatus('Error', 'error');
        }
    }
    
    // ========================================================================
    // UI Updates
    // ========================================================================
    
    updateOutputDisplay() {
        // Update each output component based on state
        BOARD_CONFIG.outputs.forEach((output, idx) => {
            const value = this.state.outputs[idx];
            const isActive = value === 1;
            
            // Find elements by data-output attribute
            const element = document.querySelector(`[data-output="${output.name}"]`);
            if (!element) return;
            
            if (output.type === 'fan') {
                const fanComponent = element.closest('.fan-component');
                if (fanComponent) {
                    fanComponent.classList.toggle('active', isActive);
                }
            } else if (output.type === 'light') {
                const lightComponent = element.closest('.indicator-light');
                if (lightComponent) {
                    lightComponent.classList.toggle('active', isActive);
                }
            } else if (output.type === 'strobe') {
                const panicComponent = element.closest('.panic-light') || element;
                panicComponent.classList.toggle('active', isActive);
            } else if (output.type === 'buzzer') {
                element.classList.toggle('active', isActive);
            }
        });
    }
    
    updateStatusDisplay() {
        // Update timer status
        const timerInfo = this.state.timerCounts.map((count, i) => {
            return `T${i}: ${count}`;
        }).join(' | ');
        this.elements.timerStatus.textContent = timerInfo;
        
        // Update counter status
        const counterInfo = this.state.counterCounts.map((count, i) => {
            return `C${i}: ${count}`;
        }).join(' | ');
        this.elements.counterStatus.textContent = counterInfo;
    }
    
    setStatus(text, state) {
        this.elements.statusIndicator.className = 'status-indicator ' + state;
        this.elements.statusText.textContent = text;
    }
    
    setCompileStatus(text, type) {
        this.elements.compileStatus.textContent = text;
        this.elements.compileStatus.className = 'compile-status ' + type;
    }
    
    enableControls(enabled) {
        this.elements.runBtn.disabled = !enabled;
        this.elements.stepBtn.disabled = !enabled;
        this.elements.resetBtn.disabled = !enabled;
        this.elements.stopBtn.disabled = true;
    }
}

// Initialize the simulator when the page loads
document.addEventListener('DOMContentLoaded', () => {
    window.simulator = new PLCSimulator();
    console.log('PLC Simulator initialized');
    console.log('INPUTS:', BOARD_CONFIG.inputs.map(i => i.name).join(', '));
    console.log('OUTPUTS:', BOARD_CONFIG.outputs.map(o => o.name).join(', '));
});
