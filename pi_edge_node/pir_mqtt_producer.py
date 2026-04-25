import time
import argparse
import json
import uuid
from datetime import datetime, timezone
import sys
import paho.mqtt.client as mqtt

# Import your newly structured custom sensor library
from motion_sensor_lib.sampler import PirSampler
from motion_sensor_lib.interpreter import PirInterpreter

def utc_now_iso() -> str:
    """Returns current UTC time in strictly formatted ISO 8601"""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print("[MQTT] Successfully connected to broker.")
    else:
        print(f"[MQTT] Connection failed with code {reason_code}")

def main():
    p = argparse.ArgumentParser(description="PIR Sensor MQTT Publisher (Producer)")
    p.add_argument("--device-id", type=str, required=True, help="Unique ID for this bin")
    p.add_argument("--pin", type=int, required=True, help="GPIO pin number")
    
    # MQTT Specific Arguments
    p.add_argument("--broker", type=str, default="test.mosquitto.org", help="MQTT Broker IP/URL")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", type=str, default="wastebin/motion", help="MQTT Topic to publish to")
    
    # Sensor Tuning Arguments
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown", type=float, default=5.0)
    p.add_argument("--min-high", type=float, default=0.2)
    args = p.parse_args()

    # 1. Initialize Hardware & Logic
    sampler = PirSampler(args.pin)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    # 2. Initialize MQTT Client
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client() # Fallback for older paho-mqtt versions
        
    client.on_connect = on_connect
    
    print(f"Connecting to MQTT Broker: {args.broker}:{args.port}...")
    client.connect(args.broker, args.port, 60)
    client.loop_start() # Start the network loop in the background

    # 3. Setup tracking variables
    run_id = str(uuid.uuid4())
    seq = 1

    print(f"Started Monitoring. Publishing to topic: '{args.topic}' on Pin {args.pin}")
    print("Press Ctrl+C to stop.")

    try:
        while True:
            now = time.time()
            
            # Read hardware and filter noise
            raw = sampler.read()
            events = interp.update(raw, now)
            
            for ev in events:
                event_time_iso = utc_now_iso() 
                
                # Build the EXACT JSON payload required by your professor
                payload = {
                    "device_id": args.device_id,
                    "event_type": "motion",
                    "motion_state": "detected",
                    "event_time": event_time_iso,
                    "seq": seq,
                    "run_id": run_id
                }
                
                # Convert dictionary to JSON string
                json_payload = json.dumps(payload)
                
                # PUBLISH to the broker
                client.publish(args.topic, json_payload)
                
                print(f"[{time.strftime('%H:%M:%S')}] 📡 Published event {seq} to '{args.topic}'")
                seq += 1
            
            time.sleep(args.sample_interval)
            
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
    finally:
        client.loop_stop()
        client.disconnect()
        print("Disconnected from MQTT Broker.")

if __name__ == "__main__":
    main()