#!/usr/bin/env python3
"""
Aquaponics IoT API Server with MQTT Integration
------------------------------------------------
FastAPI server that serves real-time sensor data from MQTT.
Run this on your Windows PC.

Usage:
    uvicorn api_server:app --reload --host 0.0.0.0 --port 8000
"""

import json
import csv
import os
import threading
from datetime import datetime
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Please install paho-mqtt: pip install paho-mqtt")
    exit(1)

# CSV file for persistent logging
CSV_FILE = "sensor_readings.csv"
CSV_COLUMNS = [
    "timestamp", "water_temp_C", "air_temp_C", "pH", "ammonia_mgL",
    "dissolved_oxygen_mgL", "ec_uScm", "water_level_percent",
    "humidity_percent", "light_lux", "pump_status", "diagnosis"
]


def init_csv():
    """Initialize CSV file with headers if it doesn't exist."""
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()
        print(f"📄 Created {CSV_FILE}")


def log_to_csv(reading):
    """Append a sensor reading to the CSV file."""
    try:
        with open(CSV_FILE, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            row = {col: reading.get(col, '') for col in CSV_COLUMNS}
            writer.writerow(row)
    except Exception as e:
        print(f"⚠️ CSV write error: {e}")


# -----------------------------
# Configuration
# -----------------------------
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MAX_READINGS = 500

# Thread-safe storage
sensor_readings = deque(maxlen=MAX_READINGS)
latest_reading = {}
lock = threading.Lock()

# Thresholds for alerts
THRESHOLDS = {
    "do_low": 5.0,
    "ammonia_high": 0.5,
    "water_level_low": 80.0,
    "temp_high": 26.0,
    "ph_low": 6.0
}


def diagnose(reading):
    """Rule-based diagnosis."""
    low_do = reading.get("dissolved_oxygen_mgL", 10) < THRESHOLDS["do_low"]
    high_ammonia = reading.get("ammonia_mgL", 0) > THRESHOLDS["ammonia_high"]
    low_water_level = reading.get("water_level_percent", 100) < THRESHOLDS["water_level_low"]
    high_temp = reading.get("water_temp_C", 20) > THRESHOLDS["temp_high"]
    low_ph = reading.get("pH", 7) < THRESHOLDS["ph_low"]
    
    if low_water_level and low_do:
        return "Pump failure suspected"
    elif high_ammonia and low_do:
        return "Overfeeding / biofilter stress"
    elif high_temp and low_do:
        return "Thermal oxygen stress"
    elif low_water_level:
        return "Leak or evaporation"
    elif low_ph:
        return "pH too low - add buffer"
    else:
        return "Normal operation"


# -----------------------------
# MQTT Client Setup
# -----------------------------
mqtt_client = None


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ MQTT Connected!")
        client.subscribe("aquaponics/sensors/#")
    else:
        print(f"❌ MQTT Connection failed: {rc}")


def on_message(client, userdata, msg):
    global latest_reading
    try:
        if msg.topic == "aquaponics/sensors/all":
            payload = json.loads(msg.payload.decode())
            payload["diagnosis"] = diagnose(payload)
            with lock:
                latest_reading = payload
                sensor_readings.append(payload)
            # Log to CSV for persistence
            log_to_csv(payload)
            print(f"📥 Received reading #{payload.get('reading_id', '?')}: {payload['diagnosis']}")
    except Exception as e:
        print(f"Error: {e}")


def start_mqtt_client():
    global mqtt_client
    mqtt_client = mqtt.Client(client_id="fastapi_subscriber")
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
        print(f"🔌 MQTT client started, connecting to {MQTT_BROKER}:{MQTT_PORT}")
    except Exception as e:
        print(f"⚠️ Could not connect to MQTT broker: {e}")
        print("   Make sure Mosquitto is running!")


def stop_mqtt_client():
    global mqtt_client
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
        print("🔌 MQTT client stopped")


# -----------------------------
# FastAPI App
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_csv()  # Initialize CSV file
    start_mqtt_client()
    yield
    # Shutdown
    stop_mqtt_client()


app = FastAPI(
    title="Aquaponics IoT API",
    description="Real-time aquaponics monitoring system with MQTT integration",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# API Endpoints
# -----------------------------
@app.get("/")
def read_root():
    return {
        "message": "Welcome to Aquaponics IoT API v2.0",
        "endpoints": {
            "/latest": "Get latest sensor reading",
            "/data": "Get historical readings",
            "/status": "System status",
            "/alerts": "Current alerts",
            "/dashboard": "Web dashboard",
            "/download-csv": "Download all recorded data as CSV"
        }
    }


@app.get("/latest")
def get_latest():
    """Get the most recent sensor reading."""
    with lock:
        if latest_reading:
            return latest_reading
        return {"message": "No data yet. Is the Raspberry Pi publishing?"}


@app.get("/download-csv")
def download_csv():
    """Download the CSV file with all recorded sensor readings."""
    if os.path.exists(CSV_FILE):
        return FileResponse(
            CSV_FILE,
            media_type="text/csv",
            filename="aquaponics_sensor_data.csv"
        )
    return {"message": "No CSV file yet. Wait for some sensor readings."}


@app.get("/data")
def get_data(limit: int = 100):
    """Get historical sensor readings."""
    with lock:
        readings_list = list(sensor_readings)
        data = readings_list[-limit:] if len(readings_list) > limit else readings_list
    return {
        "count": len(data),
        "readings": data
    }


# -----------------------------
# Control Endpoints
# -----------------------------
@app.post("/control/pump")
def control_pump(state: str = "toggle"):
    """
    Control the pump. 
    state: 'on', 'off', or 'toggle'
    """
    if mqtt_client and mqtt_client.is_connected():
        payload = json.dumps({"action": "pump", "state": state})
        mqtt_client.publish("aquaponics/control/pump", payload)
        print(f"🔧 Sent pump control: {state}")
        return {"success": True, "message": f"Pump command sent: {state}"}
    return {"success": False, "message": "MQTT not connected"}


@app.post("/control/light")
def control_light(state: str = "toggle"):
    """
    Control the grow light.
    state: 'on', 'off', or 'toggle'
    """
    if mqtt_client and mqtt_client.is_connected():
        payload = json.dumps({"action": "light", "state": state})
        mqtt_client.publish("aquaponics/control/light", payload)
        print(f"💡 Sent light control: {state}")
        return {"success": True, "message": f"Light command sent: {state}"}
    return {"success": False, "message": "MQTT not connected"}


@app.post("/control/simulate-failure")
def simulate_failure(enable: bool = True):
    """
    Trigger or stop a simulated pump failure for testing.
    """
    if mqtt_client and mqtt_client.is_connected():
        payload = json.dumps({"action": "simulate_failure", "enable": enable})
        mqtt_client.publish("aquaponics/control/simulate", payload)
        status = "enabled" if enable else "disabled"
        print(f"⚠️ Pump failure simulation: {status}")
        return {"success": True, "message": f"Pump failure simulation {status}"}
    return {"success": False, "message": "MQTT not connected"}


@app.get("/status")
def get_status():
    """Get system status."""
    with lock:
        reading_count = len(sensor_readings)
        has_data = reading_count > 0
        last_time = latest_reading.get("timestamp") if latest_reading else None
    
    return {
        "mqtt_broker": MQTT_BROKER,
        "mqtt_port": MQTT_PORT,
        "mqtt_connected": mqtt_client.is_connected() if mqtt_client else False,
        "total_readings": reading_count,
        "has_data": has_data,
        "last_reading_time": last_time,
        "thresholds": THRESHOLDS
    }


@app.get("/alerts")
def get_alerts():
    """Get current alerts based on thresholds."""
    with lock:
        if not latest_reading:
            return {"alerts": [], "message": "No data available"}
        
        alerts = []
        r = latest_reading
        
        if r.get("dissolved_oxygen_mgL", 10) < THRESHOLDS["do_low"]:
            alerts.append({"type": "warning", "sensor": "dissolved_oxygen", "message": f"Low DO: {r['dissolved_oxygen_mgL']} mg/L"})
        if r.get("ammonia_mgL", 0) > THRESHOLDS["ammonia_high"]:
            alerts.append({"type": "danger", "sensor": "ammonia", "message": f"High ammonia: {r['ammonia_mgL']} mg/L"})
        if r.get("water_level_percent", 100) < THRESHOLDS["water_level_low"]:
            alerts.append({"type": "danger", "sensor": "water_level", "message": f"Low water: {r['water_level_percent']}%"})
        if r.get("water_temp_C", 20) > THRESHOLDS["temp_high"]:
            alerts.append({"type": "warning", "sensor": "temperature", "message": f"High temp: {r['water_temp_C']}°C"})
        if r.get("pH", 7) < THRESHOLDS["ph_low"]:
            alerts.append({"type": "warning", "sensor": "pH", "message": f"Low pH: {r['pH']}"})
        if r.get("pump_status") == "FAILURE":
            alerts.append({"type": "danger", "sensor": "pump", "message": "Pump failure detected!"})
        
        return {
            "alerts": alerts,
            "alert_count": len(alerts),
            "diagnosis": r.get("diagnosis", "Unknown")
        }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Simple HTML dashboard for quick monitoring."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Aquaponics Dashboard</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body { font-family: Arial, sans-serif; padding: 20px; background: #1a1a2e; color: #eee; }
            h1 { color: #4ecca3; }
            .card { background: #16213e; padding: 15px; margin: 10px 0; border-radius: 8px; }
            .value { font-size: 24px; font-weight: bold; color: #4ecca3; }
            .label { color: #888; }
            .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 15px; }
            .alert { background: #e94560; padding: 10px; border-radius: 5px; margin: 5px 0; }
            .ok { background: #4ecca3; color: #000; }
        </style>
    </head>
    <body>
        <h1>🌿 Aquaponics IoT Dashboard 🐟</h1>
        <div id="content">Loading...</div>
        <script>
            async function update() {
                try {
                    const latest = await fetch('/latest').then(r => r.json());
                    const alerts = await fetch('/alerts').then(r => r.json());
                    
                    if (latest.message) {
                        document.getElementById('content').innerHTML = '<p>' + latest.message + '</p>';
                        return;
                    }
                    
                    let html = '<div class="card ' + (alerts.alert_count === 0 ? 'ok' : '') + '">';
                    html += '<strong>Status:</strong> ' + (latest.diagnosis || 'Unknown') + '</div>';
                    
                    html += '<div class="grid">';
                    html += '<div class="card"><div class="label">Water Temp</div><div class="value">' + latest.water_temp_C + '°C</div></div>';
                    html += '<div class="card"><div class="label">Air Temp</div><div class="value">' + latest.air_temp_C + '°C</div></div>';
                    html += '<div class="card"><div class="label">pH</div><div class="value">' + latest.pH + '</div></div>';
                    html += '<div class="card"><div class="label">Dissolved O2</div><div class="value">' + latest.dissolved_oxygen_mgL + ' mg/L</div></div>';
                    html += '<div class="card"><div class="label">Ammonia</div><div class="value">' + latest.ammonia_mgL + ' mg/L</div></div>';
                    html += '<div class="card"><div class="label">Water Level</div><div class="value">' + latest.water_level_percent + '%</div></div>';
                    html += '<div class="card"><div class="label">EC</div><div class="value">' + latest.ec_uScm + ' µS/cm</div></div>';
                    html += '<div class="card"><div class="label">Humidity</div><div class="value">' + latest.humidity_percent + '%</div></div>';
                    html += '<div class="card"><div class="label">Light</div><div class="value">' + latest.light_lux + ' lux</div></div>';
                    html += '<div class="card"><div class="label">Pump</div><div class="value">' + latest.pump_status + '</div></div>';
                    html += '</div>';
                    
                    if (alerts.alerts && alerts.alerts.length > 0) {
                        html += '<h2>⚠️ Alerts</h2>';
                        alerts.alerts.forEach(a => {
                            html += '<div class="alert">' + a.message + '</div>';
                        });
                    }
                    
                    html += '<p style="color:#666;margin-top:20px;">Last update: ' + latest.timestamp + '</p>';
                    
                    document.getElementById('content').innerHTML = html;
                } catch(e) {
                    document.getElementById('content').innerHTML = '<p>Error loading data: ' + e + '</p>';
                }
            }
            update();
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Aquaponics IoT API Server...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
