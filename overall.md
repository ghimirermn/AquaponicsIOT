# 🌿 Aquaponics IoT System - Complete Guide

A step-by-step explanation of how the entire system works, from sensors to mobile app.

---

## System Overview

```
┌─────────────────┐     MQTT      ┌─────────────────┐      HTTP      ┌─────────────────┐
│  Raspberry Pi   │ ───────────► │   Windows PC    │ ◄────────────► │   Android App   │
│                 │    :1883     │                 │     :8000      │                 │
│ • Sensors       │ ◄─────────── │ • MQTT Broker   │                │ • View data     │
│ • Simulator     │   Controls   │ • API Server    │                │ • Send commands │
└─────────────────┘              │ • Data Storage  │                └─────────────────┘
                                 └─────────────────┘
```

**Three main components:**
1. **Raspberry Pi** - Collects sensor data and receives control commands
2. **Windows PC** - Runs MQTT broker + API server (the "brain")
3. **Android App** - User interface for monitoring and control

---

## Part 1: Raspberry Pi Sensor Simulator

**File:** `rpi_sensor_simulator.py`

### What it does
Generates realistic sensor readings that mimic a real aquaponics system and publishes them via MQTT.

### Simulated Sensors

| Sensor | Value Range | Simulation Method |
|--------|-------------|-------------------|
| Water Temperature | 22-25°C | Daily sinusoidal cycle |
| Air Temperature | 20-24°C | Daily sinusoidal cycle |
| pH | 6.5-7.0 | Slow downward drift |
| Dissolved Oxygen | 5.5-7.0 mg/L | Daily cycle with noise |
| Ammonia | 0.1-0.2 mg/L | Random gaussian |
| Water Level | 90-100% | Random with pump effects |
| Humidity | 50-70% | Daily cycle |
| Light | 0-20000 lux | Day/night cycle |
| Pump Status | ON/OFF/FAILURE | Controllable |

### How simulation works

```python
# Daily temperature cycle - warmer at noon, cooler at night
def daily_cycle(mean, amplitude, noise):
    hour = current_hour  # 0-23
    value = mean + amplitude * sin(2π * hour / 24)
    value += random_noise
    return value

# Example: Water temp with mean=23.5°C, varies ±1.5°C
water_temp = daily_cycle(23.5, 1.5, 0.2)
```

### Control handling
The simulator listens for control commands from the API server:

```python
# Topics it subscribes to:
"aquaponics/control/pump"    → Toggle pump on/off
"aquaponics/control/light"   → Toggle light on/off
"aquaponics/control/simulate" → Enable/disable failure simulation
```

### Running it

```bash
python rpi_sensor_simulator.py --broker <PC_IP_ADDRESS>
```

---

## Part 2: MQTT Communication

### What is MQTT?
A lightweight messaging protocol perfect for IoT. Uses publish/subscribe pattern.

### Topic Structure

```
aquaponics/
├── sensors/
│   ├── water_temp     → Individual sensor values
│   ├── ph
│   ├── ...
│   └── all            → Combined JSON with ALL sensors
│
└── control/
    ├── pump           → {"action": "pump", "state": "toggle"}
    ├── light          → {"action": "light", "state": "on"}
    └── simulate       → {"action": "simulate_failure", "enable": true}
```

### Message Flow Example

```
1. Simulator generates readings every 5 seconds
        ↓
2. Publishes to "aquaponics/sensors/all"
        ↓
3. MQTT Broker (Mosquitto) receives message
        ↓
4. API Server (subscriber) gets the data
        ↓
5. API Server processes, diagnoses, stores, serves via HTTP
```

### Mosquitto Broker Setup (Windows)

```bash
# Install Mosquitto from https://mosquitto.org/download/

# Start the service
net start mosquitto

# Test it's running (optional)
mosquitto_sub -t "test" -v  # Subscribe
mosquitto_pub -t "test" -m "hello"  # Publish in another terminal
```

---

## Part 3: API Server

**File:** `api_server.py`

### What it does
- Subscribes to MQTT sensor data
- Runs diagnostic algorithm on each reading
- Stores data in memory (deque) and CSV file
- Serves REST API for Android app and web dashboard
- Forwards control commands to Raspberry Pi via MQTT

### Diagnostic Algorithm

```python
THRESHOLDS = {
    "do_low": 5.0,           # Dissolved oxygen critical
    "ammonia_high": 0.5,     # Ammonia toxic level
    "water_level_low": 80.0, # Pump may be failing
    "temp_high": 26.0,       # Fish stress
    "ph_low": 6.0            # Too acidic
}

def diagnose(reading):
    if low_water_level AND low_dissolved_oxygen:
        return "Pump failure suspected"
    elif high_ammonia AND low_dissolved_oxygen:
        return "Overfeeding / biofilter stress"
    elif high_temp AND low_dissolved_oxygen:
        return "Thermal oxygen stress"
    elif low_water_level:
        return "Leak or evaporation"
    elif low_ph:
        return "pH too low - add buffer"
    else:
        return "Normal operation"
```

### REST API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | API info |
| `/latest` | GET | Most recent sensor reading |
| `/data?limit=N` | GET | Historical readings |
| `/status` | GET | MQTT connection status |
| `/alerts` | GET | Current threshold violations |
| `/dashboard` | GET | Web dashboard (HTML) |
| `/download-csv` | GET | Export all data |
| `/control/pump` | POST | Control pump (on/off/toggle) |
| `/control/light` | POST | Control light |
| `/control/simulate-failure` | POST | Test failure alerts |

### Data Storage

```python
# In-memory (fast, limited to 500 readings)
sensor_readings = deque(maxlen=500)

# Persistent (CSV file)
log_to_csv(reading)  # Appends each reading
```

### Running it

```bash
cd d:\IoT
.\venv\Scripts\activate
python api_server.py
# Server runs on http://0.0.0.0:8000
```

---

## Part 4: Android App

**File:** `IoTLabApp/.../MainActivity.java`

### What it does
- Displays real-time sensor data
- Auto-refreshes every 5 seconds
- Provides control buttons for pump, light, failure simulation
- Color-codes status (green = normal, red = alert)

### App Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     MainActivity                         │
├─────────────────────────────────────────────────────────┤
│  onCreate()                                              │
│    ├── Initialize views (TextViews, Buttons)            │
│    ├── Setup click listeners                            │
│    ├── Fetch initial data                               │
│    └── Start auto-refresh timer (5s)                    │
│                                                          │
│  fetchSensorData()                                       │
│    └── HTTP GET /latest → updateUI()                    │
│                                                          │
│  sendControlCommand()                                    │
│    └── HTTP POST /control/pump?state=toggle             │
│                                                          │
│  updateUI()                                              │
│    └── Update TextViews with sensor values              │
│    └── Change colors based on diagnosis                 │
└─────────────────────────────────────────────────────────┘
```

### Network Operations

Android requires network calls on background threads:

```java
// Background thread for network
executor = Executors.newSingleThreadExecutor();

// Main thread for UI updates
mainHandler = new Handler(Looper.getMainLooper());

executor.execute(() -> {
    // Network call (background)
    String json = httpGet("/latest");
    
    // Update UI (main thread)
    mainHandler.post(() -> updateUI(json));
});
```

### Control Flow

```
┌─────────────┐   HTTP POST   ┌─────────────┐   MQTT   ┌─────────────┐
│ Tap "Pump"  │ ────────────► │ API Server  │ ───────► │ Simulator   │
│ Button      │               │ /control/   │          │ set_pump()  │
└─────────────┘               │ pump        │          └─────────────┘
                              └─────────────┘
```

### Configuration

Change the API URL in `MainActivity.java`:

```java
private static final String API_BASE_URL = "http://YOUR_PC_IP:8000";
```

---

## Part 5: Running the Complete System

### Prerequisites

| Component | Requirements |
|-----------|--------------|
| Windows PC | Python 3.8+, Mosquitto MQTT |
| Raspberry Pi | Python 3, paho-mqtt |
| Android | Android 7.0+ (API 24) |

### Startup Sequence

```bash
# Step 1: Start MQTT Broker (Windows)
net start mosquitto

# Step 2: Start API Server (Windows)
cd d:\IoT
.\venv\Scripts\activate
python api_server.py

# Step 3: Start Sensor Simulator (Raspberry Pi or Windows for testing)
python rpi_sensor_simulator.py --broker 192.168.x.x

# Step 4: Open Android App or Web Dashboard
# Web: http://YOUR_PC_IP:8000/dashboard
# App: Install APK and run
```

### Testing Locally (Single PC)

You can run everything on one Windows PC for testing:

```bash
# Terminal 1: MQTT Broker
net start mosquitto

# Terminal 2: API Server
python api_server.py

# Terminal 3: Simulator (using localhost)
python rpi_sensor_simulator.py --broker localhost

# Browser: http://localhost:8000/dashboard
```

---

## Data Flow Summary

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           COMPLETE DATA FLOW                              │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  1. SENSOR DATA (every 5 seconds)                                        │
│     Simulator → MQTT Broker → API Server → Memory/CSV                    │
│                                               ↓                          │
│                                          Diagnosis                       │
│                                               ↓                          │
│                                    Android App / Dashboard               │
│                                                                          │
│  2. CONTROL COMMANDS                                                     │
│     Android App → HTTP POST → API Server → MQTT Broker → Simulator       │
│                                                                          │
│  3. STATUS UPDATES                                                       │
│     Android App ← HTTP GET ← API Server (latest reading + diagnosis)     │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "MQTT not connected" | Is Mosquitto running? `net start mosquitto` |
| "No data yet" | Is simulator running and pointing to correct broker IP? |
| App shows errors | Check API_BASE_URL in MainActivity.java |
| Diagnosis flickering | Sensor values at threshold boundaries (expected behavior) |

---

*Guide last updated: January 5, 2026*
