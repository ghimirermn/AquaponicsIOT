#!/usr/bin/env python3
"""
Raspberry Pi Sensor Simulator for Aquaponics IoT System
--------------------------------------------------------
This script simulates sensor readings and publishes them to an MQTT broker.
It also listens for control commands from the Android app.
Deploy this on your Raspberry Pi.

Usage:
    python3 rpi_sensor_simulator.py --broker YOUR_WINDOWS_IP
"""

import json
import time
import random
import math
import argparse
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("Please install paho-mqtt: pip3 install paho-mqtt")
    exit(1)


# -----------------------------
# Configuration
# -----------------------------
MQTT_PORT = 1883
PUBLISH_INTERVAL = 5  # seconds between readings

# MQTT Topics
TOPICS = {
    "water_temp": "aquaponics/sensors/water_temp",
    "air_temp": "aquaponics/sensors/air_temp",
    "ph": "aquaponics/sensors/ph",
    "ammonia": "aquaponics/sensors/ammonia",
    "dissolved_oxygen": "aquaponics/sensors/dissolved_oxygen",
    "ec": "aquaponics/sensors/ec",
    "water_level": "aquaponics/sensors/water_level",
    "humidity": "aquaponics/sensors/humidity",
    "light": "aquaponics/sensors/light",
    "all_sensors": "aquaponics/sensors/all"  # Combined reading
}

# Control Topics
CONTROL_TOPICS = [
    "aquaponics/control/pump",
    "aquaponics/control/light",
    "aquaponics/control/simulate"
]


class AquaponicsSensorSimulator:
    """Simulates realistic aquaponics sensor readings with control support."""
    
    def __init__(self):
        self.start_time = time.time()
        self.reading_count = 0
        
        # Simulate slow drifts
        self.ph_drift = 0
        self.ec_drift = 0
        
        # Controllable states
        self.pump_on = True          # Pump is ON by default
        self.light_on = True         # Light follows day/night by default
        self.pump_failure = False    # Simulated failure state
        self.manual_light = False    # Manual light control mode
        
    def get_hour_of_day(self):
        """Get current hour (0-23) for day/night cycles."""
        return datetime.now().hour
    
    def daily_cycle(self, mean, amplitude, noise_std):
        """Generate value with daily sinusoidal pattern."""
        hour = self.get_hour_of_day()
        value = mean + amplitude * math.sin(2 * math.pi * hour / 24)
        value += random.gauss(0, noise_std)
        return round(value, 2)
    
    def set_pump(self, state):
        """Control pump state."""
        if state == "toggle":
            self.pump_on = not self.pump_on
        elif state == "on":
            self.pump_on = True
        elif state == "off":
            self.pump_on = False
        print(f"🔧 Pump is now: {'ON' if self.pump_on else 'OFF'}")
    
    def set_light(self, state):
        """Control light state."""
        self.manual_light = True  # Switch to manual mode
        if state == "toggle":
            self.light_on = not self.light_on
        elif state == "on":
            self.light_on = True
        elif state == "off":
            self.light_on = False
        elif state == "auto":
            self.manual_light = False  # Back to auto mode
        print(f"💡 Light is now: {'ON' if self.light_on else 'OFF'} ({'manual' if self.manual_light else 'auto'})")
    
    def set_failure_simulation(self, enable):
        """Enable or disable pump failure simulation."""
        self.pump_failure = enable
        print(f"⚠️ Pump failure simulation: {'ENABLED' if enable else 'DISABLED'}")
    
    def get_readings(self):
        """Generate a complete set of sensor readings."""
        self.reading_count += 1
        
        # Slow drifts over time
        self.ph_drift -= 0.0001  # pH slowly decreases
        self.ec_drift += random.gauss(0, 0.5)  # EC drifts randomly
        
        # Base readings with daily cycles
        water_temp = self.daily_cycle(23.5, 1.5, 0.2)
        air_temp = self.daily_cycle(22.0, 2.0, 0.3)
        ph = round(6.9 + self.ph_drift + random.gauss(0, 0.05), 2)
        ammonia = round(max(0, random.gauss(0.15, 0.05)), 3)
        dissolved_oxygen = self.daily_cycle(6.5, 0.6, 0.15)
        ec = round(900 + self.ec_drift, 1)
        water_level = round(95 + random.gauss(0, 2), 1)
        humidity = self.daily_cycle(60, 10, 2)
        
        # Light - auto mode follows day/night, manual mode uses light_on state
        hour = self.get_hour_of_day()
        if self.manual_light:
            light = 20000 if self.light_on else 0
        else:
            light = max(0, 20000 * math.sin(2 * math.pi * (hour - 6) / 24))
        light = round(light + random.gauss(0, 500), 0)
        
        # Determine pump status
        if self.pump_failure:
            pump_status = "FAILURE"
            water_level -= 20  # Reduced from 15 to ensure it goes below 80% threshold
            dissolved_oxygen -= 2
        elif not self.pump_on:
            pump_status = "OFF"
            water_level -= 5  # Slow decrease when pump is off
            dissolved_oxygen -= 1
        else:
            pump_status = "ON"
        
        return {
            "timestamp": datetime.now().isoformat(),
            "water_temp_C": water_temp,
            "air_temp_C": air_temp,
            "pH": ph,
            "ammonia_mgL": ammonia,
            "dissolved_oxygen_mgL": round(max(0, dissolved_oxygen), 2),
            "ec_uScm": ec,
            "water_level_percent": round(max(0, water_level), 1),
            "humidity_percent": round(humidity, 1),
            "light_lux": max(0, light),
            "pump_status": pump_status,
            "light_status": "ON" if (self.light_on if self.manual_light else light > 0) else "OFF",
            "reading_id": self.reading_count
        }


# Global simulator instance for control commands
simulator = None


def on_connect(client, userdata, flags, rc):
    """Callback when connected to MQTT broker."""
    if rc == 0:
        print("✅ Connected to MQTT Broker!")
        # Subscribe to control topics
        for topic in CONTROL_TOPICS:
            client.subscribe(topic)
            print(f"📡 Subscribed to: {topic}")
    else:
        print(f"❌ Connection failed with code {rc}")


def on_message(client, userdata, msg):
    """Handle incoming control messages."""
    global simulator
    try:
        payload = json.loads(msg.payload.decode())
        print(f"\n📥 Received control command: {msg.topic}")
        
        if msg.topic == "aquaponics/control/pump":
            state = payload.get("state", "toggle")
            simulator.set_pump(state)
            
        elif msg.topic == "aquaponics/control/light":
            state = payload.get("state", "toggle")
            simulator.set_light(state)
            
        elif msg.topic == "aquaponics/control/simulate":
            enable = payload.get("enable", True)
            simulator.set_failure_simulation(enable)
            
    except Exception as e:
        print(f"❌ Error processing control message: {e}")


def main():
    global simulator
    
    parser = argparse.ArgumentParser(description="Aquaponics Sensor Simulator")
    parser.add_argument("--broker", required=True, help="MQTT Broker IP address")
    parser.add_argument("--port", type=int, default=1883, help="MQTT Broker port")
    parser.add_argument("--interval", type=int, default=5, help="Seconds between readings")
    args = parser.parse_args()
    
    print(f"""
╔═══════════════════════════════════════════════════════╗
║     🌿 Aquaponics IoT Sensor Simulator 🐟             ║
╠═══════════════════════════════════════════════════════╣
║  Broker: {args.broker:<43} ║
║  Port: {args.port:<45} ║
║  Interval: {args.interval} seconds{' ' * 36}║
║  Control: Enabled (listening for commands)           ║
╚═══════════════════════════════════════════════════════╝
    """)
    
    # Create MQTT client
    client = mqtt.Client(client_id="rpi_sensor_simulator")
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        print(f"🔌 Connecting to broker at {args.broker}:{args.port}...")
        client.connect(args.broker, args.port, 60)
        client.loop_start()
        
        simulator = AquaponicsSensorSimulator()
        
        print("\n📡 Starting sensor simulation (Ctrl+C to stop)...")
        print("🎮 Listening for control commands...\n")
        
        while True:
            readings = simulator.get_readings()
            
            # Publish individual sensor readings
            for sensor, topic in TOPICS.items():
                if sensor == "all_sensors":
                    continue
                if sensor == "water_temp":
                    value = readings["water_temp_C"]
                elif sensor == "air_temp":
                    value = readings["air_temp_C"]
                elif sensor == "ph":
                    value = readings["pH"]
                elif sensor == "ammonia":
                    value = readings["ammonia_mgL"]
                elif sensor == "dissolved_oxygen":
                    value = readings["dissolved_oxygen_mgL"]
                elif sensor == "ec":
                    value = readings["ec_uScm"]
                elif sensor == "water_level":
                    value = readings["water_level_percent"]
                elif sensor == "humidity":
                    value = readings["humidity_percent"]
                elif sensor == "light":
                    value = readings["light_lux"]
                else:
                    continue
                    
                client.publish(topic, json.dumps({"value": value, "timestamp": readings["timestamp"]}))
            
            # Publish combined reading
            payload = json.dumps(readings)
            client.publish(TOPICS["all_sensors"], payload)
            
            # Pretty print
            print(f"[{readings['timestamp']}] Reading #{readings['reading_id']}")
            print(f"  🌡️  Water: {readings['water_temp_C']}°C | Air: {readings['air_temp_C']}°C")
            print(f"  💧 pH: {readings['pH']} | DO: {readings['dissolved_oxygen_mgL']} mg/L")
            print(f"  ⚗️  NH3: {readings['ammonia_mgL']} mg/L | EC: {readings['ec_uScm']} µS/cm")
            print(f"  📊 Water Level: {readings['water_level_percent']}% | Humidity: {readings['humidity_percent']}%")
            print(f"  💡 Light: {readings['light_lux']} lux ({readings['light_status']}) | Pump: {readings['pump_status']}")
            print("-" * 60)
            
            time.sleep(args.interval)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping sensor simulation...")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        client.loop_stop()
        client.disconnect()
        print("👋 Disconnected from broker. Goodbye!")


if __name__ == "__main__":
    main()
