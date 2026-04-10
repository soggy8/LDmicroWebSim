# LDmicro Web Simulator

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.100+-green.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

A web-based PLC ladder logic simulator that interprets [LDmicro](http://cq.cx/ladder.pl) text exports and runs them on a virtual training board with interactive inputs and outputs.

![LDmicro Web Simulator](https://via.placeholder.com/800x400?text=LDmicro+Web+Simulator)

## ✨ Features

- **Text Export Focus**: Import ladder logic from LDmicro text ladder diagram export
- **Interactive Virtual Board**: Simulates a physical PLC training board with:
  - 🔘 Sensors (light, proximity, motion, trigger, metal detectors)
  - 🔲 Toggle switches (S1, S2, S3)
  - 🟢 Push buttons (BTN1, BTN2, BTN3)
  - 🌀 Fans (FAN1, FAN2, FAN3)
  - 💡 Indicator lights (H1-green, H2-yellow, H3-red)
  - 🚨 Panic strobe and buzzer
- **Real-time Simulation**: Execute PLC cycles with adjustable speed
- **Step Debugging**: Single-step through the ladder logic
- **Modern UI**: Industrial control panel aesthetic with responsive design

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/soggy8/LDmicroWebSim.git
cd LDmicroWebSim

# Start with Docker Compose
docker-compose up -d

# Open in browser
open http://localhost:8000
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/soggy8/LDmicroWebSim.git
cd LDmicroWebSim

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the server
python server.py
```

Then open http://localhost:8000 in your browser.

## 📖 Usage

### Step 1: Export from LDmicro

In LDmicro, export your ladder diagram as text:
- **Text Format**: File → Export As → Text

### Step 2: Load into Simulator

Either:
- Paste the exported code directly into the editor
- Click "Upload" to load a file
- Click "Load Example" for a demo

### Step 3: Compile & Run

1. Click **Compile** to parse the ladder logic
2. Click **Run** to start the simulation
3. Interact with the virtual board inputs
4. Watch the outputs respond in real-time!

## 📋 Supported LDmicro Elements

| Element | Symbol | Description |
|---------|--------|-------------|
| Normally Open Contact | `] [` | True when input is ON |
| Normally Closed Contact | `]/[` | True when input is OFF |
| Output Coil | `( )` | Energize output |
| Set Coil | `(S)` | Latch ON |
| Reset Coil | `(R)` | Latch OFF |
| Timer On-Delay | `[TON]` | Delay before turning ON |
| Timer Off-Delay | `[TOF]` | Delay before turning OFF |
| Counter Up | `[CTU]` | Count up |
| Counter Down | `[CTD]` | Count down |

## 🎛️ Virtual Board I/O Names

Use these names in your LDmicro program to map to the virtual board:

### Inputs
| Name | Type | Description |
|------|------|-------------|
| `FOTO` / `XFOTO` | Sensor | Light sensor |
| `SEN` / `XSEN` | Sensor | Proximity sensor |
| `MOV` / `XMOV` | Sensor | Movement sensor |
| `TRIG` / `XTRIG` | Sensor | Trigger/door sensor |
| `PO1` / `XPO1` | Sensor | Metal detector 1 |
| `PO2` / `XPO2` | Sensor | Metal detector 2 |
| `S1` / `XS1` | Switch | Toggle switch 1 |
| `S2` / `XS2` | Switch | Toggle switch 2 |
| `S3` / `XS3` | Switch | Toggle switch 3 |
| `BTN1` / `XBTN1` | Button | Push button 1 (green) |
| `BTN2` / `XBTN2` | Button | Push button 2 (yellow) |
| `BTN3` / `XBTN3` | Button | Push button 3 (red) |

### Outputs
| Name | Type | Description |
|------|------|-------------|
| `FAN1` / `YFAN1` | Fan | Fan 1 |
| `FAN2` / `YFAN2` | Fan | Fan 2 |
| `FAN3` / `YFAN3` | Fan | Fan 3 |
| `H1` / `YH1` | Light | Green indicator |
| `H2` / `YH2` | Light | Yellow indicator |
| `H3` / `YH3` | Light | Red indicator |
| `PANIC` / `YPANIC` | Strobe | Panic strobe light |
| `BELL` / `YBELL` | Buzzer | Emergency bell |

> **Note**: LDmicro uses `X` prefix for inputs and `Y` prefix for outputs. The simulator automatically handles both conventions.

## 📁 Project Structure

```
LDmicroWebSim/
├── server.py              # FastAPI backend server
├── interpreter/
│   ├── __init__.py
│   ├── ladder_parser.py   # Ladder text parser
│   └── unified_transpiler.py  # Ladder text to JS transpiler
├── static/
│   ├── index.html         # Main UI
│   ├── styles.css         # Industrial theme CSS
│   └── simulator.js       # Browser simulation engine
├── examples/
│   └── simple_ladder.txt  # Example ladder text export
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 🐳 Docker Configuration

The included Docker setup provides:
- Python 3.11 slim image
- Automatic dependency installation
- Hot-reload for development
- Port 8000 exposed

```yaml
# docker-compose.yml
services:
  ldmicro-sim:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - .:/app  # For development hot-reload
```

## 🔧 Development

```bash
# Run in development mode with auto-reload
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

## 📝 Example Ladder Diagram

```
LDmicro export text
for 'Microchip PIC16F877 40-PDIP', 8.000000 MHz crystal, 0.5 ms cycle time

LADDER DIAGRAM:

   ||                                                   ||
   ||       XS1              XS2              YH1       ||
 1 ||-------] [--------------]/[--------------( )-------||
   ||                                                   ||
   ||       XS2              XS3              YH2       ||
 2 ||-------] [--------------]/[--------------( )-------||
   ||                                                   ||
   ||       XS3              XS1              YH3       ||
 3 ||-------] [--------------]/[--------------( )-------||
   ||                                                   ||
   ||------[END]----------------------------------------||

I/O ASSIGNMENT:

  Name    | Type           | Pin
 ---------+----------------+------
  XS1     | Digital input  | 2
  XS2     | Digital input  | 3
  XS3     | Digital input  | 4
  YH1     | Digital output | 21
  YH2     | Digital output | 22
  YH3     | Digital output | 23
```

This creates a "rotating light" pattern:
- S1 ON + S2 OFF → H1 (green) ON
- S2 ON + S3 OFF → H2 (yellow) ON
- S3 ON + S1 OFF → H3 (red) ON

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [LDmicro](http://cq.cx/ladder.pl) - The original ladder logic compiler
- Inspired by physical PLC training boards used in education

---

<p align="center">
  Made with ❤️ for PLC education and simulation
</p>

