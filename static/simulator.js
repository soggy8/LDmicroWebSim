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
 *     Physical aliases: START1, STOP1, START2
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
        { name: "BTN2", type: "button", description: "Push button 2 (stop/red)" },
        { name: "BTN3", type: "button", description: "Push button 3 (start/green)" },
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

const PLC_PIN_CONFIG = {
    inputPins: ["DI1", "DI2", "DI3", "DI4", "DI5", "DI6", "DI7", "DI8", "AI1", "AI2"],
    outputPins: ["DO1", "DO2", "DO3", "DO4", "DO5", "DO6", "AO1", "AO2"],
};

const WIRE_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#17becf", "#bcbd22",
];

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
        this.rawInputs = new Array(BOARD_CONFIG.inputs.length).fill(0);
        // Ensure momentary button presses are visible to at least one PLC scan.
        this.buttonPulseLatch = new Array(BOARD_CONFIG.inputs.length).fill(0);
        this.visibleOutputs = new Array(BOARD_CONFIG.outputs.length).fill(0);
        
        // Name to index mapping
        this.inputMap = {};
        this.outputMap = {};
        BOARD_CONFIG.inputs.forEach((inp, i) => this.inputMap[inp.name] = i);
        BOARD_CONFIG.outputs.forEach((out, i) => this.outputMap[out.name] = i);
        this.inputWiring = {};
        this.outputWiring = {};
        this.wires = [];
        this.dragStart = null;
        this.dragPoint = null;
        this.selectedWireKey = null;
        /** @type {{component: string, pin: string, points: {x:number,y:number}[]}[]} */
        this.wireGeometries = [];
        
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
        this.initWiring();
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
            plcInputPins: document.getElementById('plcInputPins'),
            plcOutputPins: document.getElementById('plcOutputPins'),
            wiringCanvas: document.getElementById('wiringCanvas'),
            plcCenterBlock: document.querySelector('.plc-center-block'),
            physicalBoard: document.querySelector('.physical-board'),
        };
    }

    initWiring() {
        this.renderPinRails();
        this.attachComponentWireNodes();
        this.bindWiringEvents();
        this.wires = [];
        this.selectedWireKey = null;
        this.syncWiringMapsFromWires();
        this.renderWires();
    }

    wireKey(component, pin) {
        return `${component}|${pin}`;
    }

    handleWireKeyboard(e) {
        if (e.key !== 'Delete' && e.key !== 'Backspace' && e.key !== 'Escape') return;
        if (e.key === 'Escape') {
            if (this.selectedWireKey !== null) {
                this.selectedWireKey = null;
                this.renderWires();
                e.preventDefault();
            }
            return;
        }
        if (this.selectedWireKey === null) return;
        const t = e.target;
        if (t && (t.id === 'codeEditor' || t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) {
            return;
        }
        e.preventDefault();
        this.wires = this.wires.filter((w) => this.wireKey(w.component, w.pin) !== this.selectedWireKey);
        this.selectedWireKey = null;
        this.syncWiringMapsFromWires();
        this.renderWires();
    }

    renderPinRails() {
        if (!this.elements.plcInputPins || !this.elements.plcOutputPins) return;
        this.elements.plcInputPins.innerHTML = "";
        this.elements.plcOutputPins.innerHTML = "";

        PLC_PIN_CONFIG.inputPins.forEach((pin) => {
            this.elements.plcInputPins.insertAdjacentHTML(
                "beforeend",
                `<div class="plc-pin" data-node-type="pin-input" data-node-name="${pin}">
                    <div class="plc-pin-dot"></div>${pin}
                </div>`
            );
        });
        PLC_PIN_CONFIG.outputPins.forEach((pin) => {
            this.elements.plcOutputPins.insertAdjacentHTML(
                "beforeend",
                `<div class="plc-pin" data-node-type="pin-output" data-node-name="${pin}">
                    <div class="plc-pin-dot"></div>${pin}
                </div>`
            );
        });
    }

    attachComponentWireNodes() {
        const inputSelectors = ['.sensor-box[data-input]', '.light-switch[data-input]', '.push-button[data-input]'];
        const outputSelectors = ['[data-output="FAN1"]', '[data-output="FAN2"]', '[data-output="FAN3"]', '[data-output="H1"]', '[data-output="H2"]', '[data-output="H3"]', '[data-output="PANIC"]', '[data-output="BELL"]'];

        document.querySelectorAll('.wire-node').forEach((n) => n.remove());

        inputSelectors.forEach((selector) => {
            document.querySelectorAll(selector).forEach((el) => {
                const name = el.dataset.input;
                const host = el.closest('.input-component') || el;
                if (!name || !host) return;
                this.createWireNode(host, 'component-input', name);
            });
        });

        outputSelectors.forEach((selector) => {
            document.querySelectorAll(selector).forEach((el) => {
                const name = el.dataset.output;
                const host = el.closest('.fan-component, .indicator-light, .output-component, .panic-light') || el;
                if (!name || !host) return;
                this.createWireNode(host, 'component-output', name);
            });
        });
    }

    createWireNode(host, type, name) {
        if (!host || host.querySelector(`.wire-node[data-node-name="${name}"]`)) return;
        const node = document.createElement('div');
        node.className = 'wire-node';
        node.dataset.nodeType = type;
        node.dataset.nodeName = name;
        host.appendChild(node);
    }

    bindWiringEvents() {
        document.addEventListener('mousedown', (e) => this.handleWirePickCapture(e), true);
        document.addEventListener('mousedown', (e) => this.handleWireStart(e));
        document.addEventListener('mousemove', (e) => this.handleWireDrag(e));
        document.addEventListener('mouseup', (e) => this.handleWireEnd(e));
        document.addEventListener('pointermove', (e) => this.handleWirePointerMove(e), { passive: true });
        window.addEventListener('resize', () => this.renderWires());
    }

    /**
     * Distance² from P to segment AB (board coordinates).
     */
    distPointToSegmentSquared(px, py, x1, y1, x2, y2) {
        const dx = x2 - x1;
        const dy = y2 - y1;
        const len2 = dx * dx + dy * dy;
        if (len2 < 1e-6) return (px - x1) ** 2 + (py - y1) ** 2;
        let t = ((px - x1) * dx + (py - y1) * dy) / len2;
        t = Math.max(0, Math.min(1, t));
        const qx = x1 + t * dx;
        const qy = y1 + t * dy;
        return (px - qx) ** 2 + (py - qy) ** 2;
    }

    distPointToPolylineSquared(px, py, points) {
        let min = Infinity;
        for (let i = 0; i < points.length - 1; i++) {
            const a = points[i];
            const b = points[i + 1];
            const d = this.distPointToSegmentSquared(px, py, a.x, a.y, b.x, b.y);
            if (d < min) min = d;
        }
        return min;
    }

    /** True if topmost hit targets should take the click instead of wire picking. */
    wirePickBlockedByUiAt(clientX, clientY) {
        const board = this.elements.physicalBoard;
        const svg = this.elements.wiringCanvas;
        if (!board) return true;
        const stack = document.elementsFromPoint(clientX, clientY);
        for (let i = 0; i < stack.length; i++) {
            const el = stack[i];
            if (!board.contains(el)) {
                if (i === 0) return true;
                break;
            }
            if (el === board) return false;
            if (svg && (el === svg || svg.contains(el))) continue;
            if (el.matches('button, input, textarea, select, option')) return true;
            if (el.closest('[data-node-type]')) return true;
            if (el.closest('.sensor-box, .push-button, .light-switch')) return true;
            if (el.closest('.fan-housing, .indicator-light, .panic-light, .bell-box')) return true;
            if (el.closest('.contactor-card, .plc-module, .plc-display, .plc-key')) return true;
            if (el.closest('.board-headings, .status-section, .board-title, .board-side-title')) return true;
            return false;
        }
        return false;
    }

    pickWireByGeometry(clientX, clientY) {
        if (!this.wireGeometries.length) return null;
        if (this.wirePickBlockedByUiAt(clientX, clientY)) return null;
        const host = this.elements.physicalBoard.getBoundingClientRect();
        const px = clientX - host.left;
        const py = clientY - host.top;
        const thresh2 = 14 * 14;
        let best = null;
        let bestD = thresh2;
        for (let i = this.wireGeometries.length - 1; i >= 0; i--) {
            const g = this.wireGeometries[i];
            if (!g.points || g.points.length < 2) continue;
            const d2 = this.distPointToPolylineSquared(px, py, g.points);
            if (d2 < bestD) {
                bestD = d2;
                best = g;
            }
        }
        return best;
    }

    handleWirePickCapture(e) {
        if (e.button !== 0) return;
        const board = this.elements.physicalBoard;
        if (!board) return;
        const br = board.getBoundingClientRect();
        if (e.clientX < br.left || e.clientX > br.right || e.clientY < br.top || e.clientY > br.bottom) return;
        const picked = this.pickWireByGeometry(e.clientX, e.clientY);
        if (!picked) return;

        e.preventDefault();
        e.stopPropagation();

        const wk = this.wireKey(picked.component, picked.pin);
        if (e.detail === 2) {
            this.wires = this.wires.filter((w) => this.wireKey(w.component, w.pin) !== wk);
            this.selectedWireKey = null;
            this.syncWiringMapsFromWires();
        } else {
            this.selectedWireKey = wk;
        }
        this.renderWires();
    }

    handleWirePointerMove(e) {
        const board = this.elements.physicalBoard;
        if (!board) return;
        const br = board.getBoundingClientRect();
        const overBoard = e.clientX >= br.left && e.clientX <= br.right && e.clientY >= br.top && e.clientY <= br.bottom;
        if (!overBoard) {
            if (board.dataset.wireCursor === '1') {
                board.style.cursor = '';
                delete board.dataset.wireCursor;
            }
            return;
        }
        const near = this.pickWireByGeometry(e.clientX, e.clientY);
        if (near) {
            board.style.cursor = 'pointer';
            board.dataset.wireCursor = '1';
        } else if (board.dataset.wireCursor === '1') {
            board.style.cursor = '';
            delete board.dataset.wireCursor;
        }
    }

    handleWireStart(e) {
        const node = e.target.closest('[data-node-type]');
        if (node) {
            this.selectedWireKey = null;
            this.dragStart = { type: node.dataset.nodeType, name: node.dataset.nodeName, element: node };
            this.dragPoint = { x: e.clientX, y: e.clientY };
            this.renderWires();
            return;
        }
        this.selectedWireKey = null;
        this.renderWires();
    }

    handleWireDrag(e) {
        if (!this.dragStart) return;
        this.dragPoint = { x: e.clientX, y: e.clientY };
        this.renderWires();
    }

    handleWireEnd(e) {
        if (!this.dragStart) return;
        const endNode = e.target.closest('[data-node-type]');
        if (endNode) {
            const end = { type: endNode.dataset.nodeType, name: endNode.dataset.nodeName, element: endNode };
            this.tryCreateWire(this.dragStart, end);
        }
        this.dragStart = null;
        this.dragPoint = null;
        this.syncWiringMapsFromWires();
        this.renderWires();
    }

    tryCreateWire(a, b) {
        const pair = [a.type, b.type].sort().join('|');
        const isInputPair = pair === 'component-input|pin-input';
        const isOutputPair = pair === 'component-output|pin-output';
        if (!isInputPair && !isOutputPair) return;

        const component = a.type.startsWith('component') ? a : b;
        const pin = a.type.startsWith('pin') ? a : b;

        this.wires = this.wires.filter((w) => w.component !== component.name && w.pin !== pin.name);
        this.wires.push({
            componentType: component.type,
            pinType: pin.type,
            component: component.name,
            pin: pin.name,
        });
        this.selectedWireKey = null;
    }

    syncWiringMapsFromWires() {
        this.inputWiring = {};
        this.outputWiring = {};
        PLC_PIN_CONFIG.inputPins.forEach((pin) => { this.inputWiring[pin] = ""; });
        PLC_PIN_CONFIG.outputPins.forEach((pin) => { this.outputWiring[pin] = ""; });

        this.wires.forEach((wire) => {
            if (wire.pinType === 'pin-input') this.inputWiring[wire.pin] = wire.component;
            if (wire.pinType === 'pin-output') this.outputWiring[wire.pin] = wire.component;
        });

        document.querySelectorAll('.wire-node, .plc-pin').forEach((el) => el.classList.remove('connected'));
        this.wires.forEach((wire) => {
            const compNode = document.querySelector(`.wire-node[data-node-name="${wire.component}"]`);
            const pinNode = document.querySelector(`.plc-pin[data-node-name="${wire.pin}"]`);
            if (compNode) compNode.classList.add('connected');
            if (pinNode) pinNode.classList.add('connected');
        });
        this.updateWireActivityIndicators();
    }

    renderWires() {
        const svg = this.elements.wiringCanvas;
        const host = this.elements.physicalBoard;
        if (!svg || !host) return;

        const hostRect = host.getBoundingClientRect();
        const paths = [];

        const nodeCenter = (el) => {
            const r = el.getBoundingClientRect();
            return {
                x: r.left + (r.width / 2) - hostRect.left,
                y: r.top + (r.height / 2) - hostRect.top,
            };
        };

        const routingGrid = this.buildRoutingGrid(hostRect);

        this.wireGeometries = [];
        this.wires.forEach((wire, idx) => {
            const a = document.querySelector(`.wire-node[data-node-name="${wire.component}"]`);
            const b = document.querySelector(`.plc-pin[data-node-name="${wire.pin}"] .plc-pin-dot`);
            if (!a || !b) return;
            const p1 = nodeCenter(a);
            const p2 = nodeCenter(b);
            const routed = this.buildAutoRoutedPath(p1, p2, routingGrid);
            this.addRoutePenalty(routingGrid, routed.cells);
            if (routed.points && routed.points.length >= 2) {
                this.wireGeometries.push({
                    component: wire.component,
                    pin: wire.pin,
                    points: routed.points,
                });
            }
            const color = this.getWireColor(wire, idx);
            const wk = this.wireKey(wire.component, wire.pin);
            const sel = wk === this.selectedWireKey ? ' wire-path-selected' : '';
            paths.push(
                `<path class="wire-path${sel}" d="${routed.d}" fill="none" `
                + `style="stroke:${color}" pointer-events="none" `
                + `title="Near the line: pointer selects — Delete or double-click removes" />`
            );
        });

        if (this.dragStart && this.dragPoint) {
            const startEl = this.dragStart.type.startsWith('pin')
                ? document.querySelector(`.plc-pin[data-node-name="${this.dragStart.name}"] .plc-pin-dot`)
                : document.querySelector(`.wire-node[data-node-name="${this.dragStart.name}"]`);
            if (startEl) {
                const p1 = nodeCenter(startEl);
                const p2 = { x: this.dragPoint.x - hostRect.left, y: this.dragPoint.y - hostRect.top };
                const routedPreview = this.buildAutoRoutedPath(p1, p2, routingGrid);
                paths.push(`<path class="wire-path wire-path-preview" d="${routedPreview.d}" />`);
            }
        }

        svg.setAttribute('viewBox', `0 0 ${hostRect.width} ${hostRect.height}`);
        svg.innerHTML = paths.join('');
    }

    buildRoutingGrid(hostRect) {
        const cell = 12;
        const cols = Math.max(10, Math.floor(hostRect.width / cell));
        const rows = Math.max(10, Math.floor(hostRect.height / cell));
        const blocked = Array.from({ length: rows }, () => Array(cols).fill(false));
        const penalty = Array.from({ length: rows }, () => Array(cols).fill(0));

        const obstacles = Array.from(document.querySelectorAll(
            '.board-headings, .sensor-box, .fan-housing, .indicator-light, .light-switch, .push-button, .placeholder-box, .panic-light, .bell-box, .contactors-grid, .status-section, .plc-module, .plc-pin-rail'
        ));

        obstacles.forEach((el) => {
            const r = el.getBoundingClientRect();
            const pad = 3;
            const x1 = Math.floor((r.left - hostRect.left - pad) / cell);
            const y1 = Math.floor((r.top - hostRect.top - pad) / cell);
            const x2 = Math.ceil((r.right - hostRect.left + pad) / cell);
            const y2 = Math.ceil((r.bottom - hostRect.top + pad) / cell);

            for (let y = Math.max(0, y1); y < Math.min(rows, y2); y++) {
                for (let x = Math.max(0, x1); x < Math.min(cols, x2); x++) {
                    blocked[y][x] = true;
                }
            }
        });

        // Existing wire occupancy gets penalty (discourage overlap but don't hard block)
        this.wires.forEach((wire) => {
            const comp = document.querySelector(`.wire-node[data-node-name="${wire.component}"]`);
            const pin = document.querySelector(`.plc-pin[data-node-name="${wire.pin}"] .plc-pin-dot`);
            if (!comp || !pin) return;
            const p1 = comp.getBoundingClientRect();
            const p2 = pin.getBoundingClientRect();
            const cx1 = ((p1.left + p1.right) / 2) - hostRect.left;
            const cy1 = ((p1.top + p1.bottom) / 2) - hostRect.top;
            const cx2 = ((p2.left + p2.right) / 2) - hostRect.left;
            const cy2 = ((p2.top + p2.bottom) / 2) - hostRect.top;
            const steps = 24;
            for (let i = 0; i <= steps; i++) {
                const t = i / steps;
                const x = cx1 + (cx2 - cx1) * t;
                const y = cy1 + (cy2 - cy1) * t;
                const gx = Math.floor(x / cell);
                const gy = Math.floor(y / cell);
                if (gy >= 0 && gy < rows && gx >= 0 && gx < cols) {
                    penalty[gy][gx] += 8;
                }
            }
        });

        return { cell, cols, rows, blocked, penalty };
    }

    buildAutoRoutedPath(p1, p2, grid) {
        const start = this.pointToGrid(p1, grid);
        const goal = this.pointToGrid(p2, grid);
        this.clearGridAroundPoint(grid, start, 2);
        this.clearGridAroundPoint(grid, goal, 2);
        const cells = this.findPathAStar(start, goal, grid);

        if (!cells || cells.length === 0) {
            return this.buildEdgeBypassPath(p1, p2, grid);
        }

        const points = cells.map((c) => this.gridToPoint(c, grid));
        const simplified = this.simplifyPolyline(points);

        // Add exact endpoints so wires touch the dots exactly.
        const allPoints = [p1, ...simplified, p2];
        const pathParts = [`M ${allPoints[0].x} ${allPoints[0].y}`];
        for (let i = 1; i < allPoints.length; i++) {
            pathParts.push(`L ${allPoints[i].x} ${allPoints[i].y}`);
        }
        return { d: pathParts.join(' '), cells, points: allPoints };
    }

    clearGridAroundPoint(grid, pt, radius) {
        for (let y = pt.y - radius; y <= pt.y + radius; y++) {
            for (let x = pt.x - radius; x <= pt.x + radius; x++) {
                if (y < 0 || x < 0 || y >= grid.rows || x >= grid.cols) continue;
                grid.blocked[y][x] = false;
            }
        }
    }

    buildEdgeBypassPath(p1, p2, grid) {
        const margin = 10;
        const leftLane = margin;
        const rightLane = (grid.cols * grid.cell) - margin;
        const useLeft = Math.abs(p1.x - leftLane) + Math.abs(p2.x - leftLane)
            < Math.abs(p1.x - rightLane) + Math.abs(p2.x - rightLane);
        const laneX = useLeft ? leftLane : rightLane;
        const midY = Math.max(18, Math.min((grid.rows * grid.cell) - 18, (p1.y + p2.y) / 2));
        const d = [
            `M ${p1.x} ${p1.y}`,
            `L ${laneX} ${p1.y}`,
            `L ${laneX} ${midY}`,
            `L ${laneX} ${p2.y}`,
            `L ${p2.x} ${p2.y}`,
        ].join(' ');
        const points = [
            { x: p1.x, y: p1.y },
            { x: laneX, y: p1.y },
            { x: laneX, y: midY },
            { x: laneX, y: p2.y },
            { x: p2.x, y: p2.y },
        ];
        return { d, cells: [], points };
    }

    pointToGrid(p, grid) {
        return {
            x: Math.max(0, Math.min(grid.cols - 1, Math.floor(p.x / grid.cell))),
            y: Math.max(0, Math.min(grid.rows - 1, Math.floor(p.y / grid.cell))),
        };
    }

    gridToPoint(c, grid) {
        return {
            x: (c.x * grid.cell) + (grid.cell / 2),
            y: (c.y * grid.cell) + (grid.cell / 2),
        };
    }

    findPathAStar(start, goal, grid) {
        const key = (n) => `${n.x},${n.y}`;
        const manhattan = (a, b) => Math.abs(a.x - b.x) + Math.abs(a.y - b.y);

        const open = new Map();
        const gScore = new Map();
        const fScore = new Map();
        const cameFrom = new Map();
        const closed = new Set();

        const startKey = key(start);
        open.set(startKey, start);
        gScore.set(startKey, 0);
        fScore.set(startKey, manhattan(start, goal));

        // 8-direction routing allows clean 45-degree segments.
        const dirs = [
            { x: 1, y: 0 }, { x: -1, y: 0 },
            { x: 0, y: 1 }, { x: 0, y: -1 },
            { x: 1, y: 1 }, { x: 1, y: -1 },
            { x: -1, y: 1 }, { x: -1, y: -1 },
        ];

        // Allow start/goal cells even if inside obstacle padding.
        grid.blocked[start.y][start.x] = false;
        grid.blocked[goal.y][goal.x] = false;

        let guard = 0;
        while (open.size > 0 && guard < 40000) {
            guard++;
            let currentKey = null;
            let current = null;
            let bestF = Infinity;
            for (const [k, n] of open.entries()) {
                const f = fScore.get(k) ?? Infinity;
                if (f < bestF) {
                    bestF = f;
                    currentKey = k;
                    current = n;
                }
            }
            if (!current || !currentKey) break;

            if (current.x === goal.x && current.y === goal.y) {
                return this.reconstructPath(cameFrom, current, key);
            }

            open.delete(currentKey);
            closed.add(currentKey);

            for (const d of dirs) {
                const nx = current.x + d.x;
                const ny = current.y + d.y;
                if (nx < 0 || ny < 0 || nx >= grid.cols || ny >= grid.rows) continue;
                if (grid.blocked[ny][nx]) continue;
                // Prevent diagonal corner-cutting through blocked orthogonal neighbors.
                if (d.x !== 0 && d.y !== 0) {
                    if (grid.blocked[current.y][nx] || grid.blocked[ny][current.x]) continue;
                }

                const neighbor = { x: nx, y: ny };
                const nKey = key(neighbor);
                if (closed.has(nKey)) continue;

                const baseCost = (d.x !== 0 && d.y !== 0) ? 1.42 : 1.0;
                let turnPenalty = 0;
                const prev = cameFrom.get(currentKey);
                if (prev) {
                    const pdx = current.x - prev.x;
                    const pdy = current.y - prev.y;
                    if (pdx !== d.x || pdy !== d.y) turnPenalty = 0.22;
                }
                const tentativeG = (gScore.get(currentKey) ?? Infinity) + baseCost + turnPenalty + (grid.penalty[ny][nx] || 0);

                if (!open.has(nKey) || tentativeG < (gScore.get(nKey) ?? Infinity)) {
                    cameFrom.set(nKey, current);
                    gScore.set(nKey, tentativeG);
                    fScore.set(nKey, tentativeG + manhattan(neighbor, goal));
                    open.set(nKey, neighbor);
                }
            }
        }

        return [];
    }

    addRoutePenalty(grid, cells) {
        if (!cells || cells.length === 0) return;
        for (const c of cells) {
            for (let dy = -1; dy <= 1; dy++) {
                for (let dx = -1; dx <= 1; dx++) {
                    const x = c.x + dx;
                    const y = c.y + dy;
                    if (x < 0 || y < 0 || x >= grid.cols || y >= grid.rows) continue;
                    grid.penalty[y][x] += 10;
                }
            }
        }
    }

    getWireColor(wire, idx) {
        const seed = `${wire.component}:${wire.pin}:${idx}`;
        let hash = 0;
        for (let i = 0; i < seed.length; i++) hash = ((hash << 5) - hash) + seed.charCodeAt(i);
        const n = Math.abs(hash) % WIRE_COLORS.length;
        return WIRE_COLORS[n];
    }

    reconstructPath(cameFrom, current, keyFn) {
        const path = [current];
        let cur = current;
        while (true) {
            const prev = cameFrom.get(keyFn(cur));
            if (!prev) break;
            path.push(prev);
            cur = prev;
        }
        return path.reverse();
    }

    simplifyPolyline(points) {
        if (points.length < 3) return points;
        const out = [points[0]];
        for (let i = 1; i < points.length - 1; i++) {
            const a = out[out.length - 1];
            const b = points[i];
            const c = points[i + 1];
            const abx = b.x - a.x;
            const aby = b.y - a.y;
            const bcx = c.x - b.x;
            const bcy = c.y - b.y;
            // Keep turn points, remove near-collinear points.
            const cross = Math.abs((abx * bcy) - (aby * bcx));
            if (cross > 2) out.push(b);
        }
        out.push(points[points.length - 1]);
        return out;
    }
    
    bindEvents() {
        // Code editor
        this.elements.codeEditor.addEventListener('input', () => this.updateLineNumbers());
        this.elements.codeEditor.addEventListener('scroll', () => this.syncScroll());
        this.elements.codeEditor.addEventListener('keydown', (e) => this.handleTab(e));
        document.addEventListener('keydown', (e) => this.handleWireKeyboard(e));
        
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
                if (this.rawInputs[idx] === 1) {
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
                const newValue = this.rawInputs[idx] ? 0 : 1;
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
        const exampleCode = `LDmicro export text
for 'Microchip PIC16F877 40-PDIP', 8.000000 MHz crystal, 0.5 ms cycle time


LADDER DIAGRAM:

   ||                                  ||
   ||       XS1              YH1       ||
 1 ||-------] [--------------( )-------||
   ||                                  ||
   ||                                  ||
   ||                                  ||
   ||                                  ||
   ||       XS2              YH2       ||
 2 ||-------] [--------------( )-------||
   ||                                  ||
   ||                                  ||
   ||                                  ||
   ||------[END]-----------------------||
   ||                                  ||
   ||                                  ||


I/O ASSIGNMENT:

  Name                       | Type               | Pin
 ----------------------------+--------------------+------
  XS1                        | Digital input      | 2
  XS2                        | Digital input      | 3
  YH1                        | Digital output     | 21
  YH2                        | Digital output     | 22`;
        
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
            this.setCompileStatus('Please enter LDmicro text export', 'error');
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
        this.rawInputs.fill(0);
        this.visibleOutputs.fill(0);
        this.state.timers.fill(0);
        this.state.timerCounts.fill(0);
        this.state.counters.fill(0);
        this.state.counterCounts.fill(0);
        this.state.internals.fill(0);
        
        // Create the PlcCycle function from the generated JavaScript
        try {
            // Support both forms:
            // - function PlcCycle() { ... }    (legacy)
            // - function PlcCycle(state) { ... } (current ladder transpiler)
            this.plcCycleFunction = new Function(
                'state',
                `${config.plcCycleJs}\nreturn PlcCycle(state);`
            );
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
        this.rawInputs[index] = value;
        const inputCfg = BOARD_CONFIG.inputs[index];
        if (inputCfg && inputCfg.type === 'button' && value === 1) {
            // Hold as logical high for a couple of scans to avoid missed clicks while running.
            this.buttonPulseLatch[index] = Math.max(this.buttonPulseLatch[index], 2);
        }
        
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
        this.rawInputs.fill(0);
        this.visibleOutputs.fill(0);
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
    
    async executeCycle() {
        if (!this.plcCycleFunction) return;
        
        try {
            this.applyInputWiring();
            // Execute the PLC cycle
            this.plcCycleFunction(this.state);
            this.applyOutputWiring();
            
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
            const value = this.visibleOutputs[idx];
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

    applyInputWiring() {
        this.state.inputs.fill(0);
        PLC_PIN_CONFIG.inputPins.forEach((pin) => {
            const mappedInput = this.inputWiring[pin];
            if (!mappedInput) return;
            const idx = this.inputMap[mappedInput];
            if (idx === undefined) return;
            const latched = this.buttonPulseLatch[idx] > 0 ? 1 : 0;
            this.state.inputs[idx] = this.rawInputs[idx] || latched ? 1 : 0;
        });
        for (let i = 0; i < this.buttonPulseLatch.length; i++) {
            if (this.buttonPulseLatch[i] > 0) this.buttonPulseLatch[i]--;
        }
        this.updateWireActivityIndicators();
    }

    applyOutputWiring() {
        this.visibleOutputs.fill(0);
        PLC_PIN_CONFIG.outputPins.forEach((pin) => {
            const mappedOutput = this.outputWiring[pin];
            if (!mappedOutput) return;
            const idx = this.outputMap[mappedOutput];
            if (idx === undefined) return;
            this.visibleOutputs[idx] = this.state.outputs[idx];
        });
        this.updateWireActivityIndicators();
    }

    updateWireActivityIndicators() {
        document.querySelectorAll('.wire-node, .plc-pin').forEach((el) => el.classList.remove('active'));

        // Component-side dots
        BOARD_CONFIG.inputs.forEach((inp, idx) => {
            const node = document.querySelector(`.wire-node[data-node-type="component-input"][data-node-name="${inp.name}"]`);
            if (!node) return;
            if (this.rawInputs[idx] === 1) node.classList.add('active');
        });
        BOARD_CONFIG.outputs.forEach((out, idx) => {
            const node = document.querySelector(`.wire-node[data-node-type="component-output"][data-node-name="${out.name}"]`);
            if (!node) return;
            if (this.visibleOutputs[idx] === 1) node.classList.add('active');
        });

        // PLC-side pins
        PLC_PIN_CONFIG.inputPins.forEach((pin) => {
            const mappedInput = this.inputWiring[pin];
            if (!mappedInput) return;
            const idx = this.inputMap[mappedInput];
            if (idx === undefined || this.rawInputs[idx] !== 1) return;
            const pinNode = document.querySelector(`.plc-pin[data-node-type="pin-input"][data-node-name="${pin}"]`);
            if (pinNode) pinNode.classList.add('active');
        });
        PLC_PIN_CONFIG.outputPins.forEach((pin) => {
            const mappedOutput = this.outputWiring[pin];
            if (!mappedOutput) return;
            const idx = this.outputMap[mappedOutput];
            if (idx === undefined || this.visibleOutputs[idx] !== 1) return;
            const pinNode = document.querySelector(`.plc-pin[data-node-type="pin-output"][data-node-name="${pin}"]`);
            if (pinNode) pinNode.classList.add('active');
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
