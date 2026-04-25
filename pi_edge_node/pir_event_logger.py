import time
import argparse
import json
import uuid
from datetime import datetime, timezone
import sys

# Import your custom sensor library
from motion_sensor_lib.sampler import PirSampler
from motion_sensor_lib.interpreter import PirInterpreter

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def main():
    p = argparse.ArgumentParser(description="PIR Sensor Local JSONL Logger")
    # Added these back in so the command works!
    p.add_argument("--device-id", type=str, required=True, help="Unique ID for this bin")
    p.add_argument("--output", type=str, default="motion_events.jsonl", help="Output file name")
    
    p.add_argument("--pin", type=int, required=True, help="GPIO pin number")
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown", type=float, default=5.0)
    p.add_argument("--min-high", type=float, default=0.2)
    args = p.parse_args()

    sampler = PirSampler(args.pin)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    run_id = str(uuid.uuid4())
    seq = 1

    print(f"Starting Logger for {args.device_id} on Pin {args.pin}")
    print(f"File: {args.output} | Press Ctrl+C to stop.")

    try:
        with open(args.output, "a") as f:
            while True:
                now = time.time()
                raw = sampler.read()
                events = interp.update(raw, now)
                
                for ev in events:
                    event_time_iso = utc_now_iso()
                    payload = {
                        "device_id": args.device_id,
                        "event_type": "motion",
                        "motion_state": "detected",
                        "event_time": event_time_iso,
                        "seq": seq,
                        "run_id": run_id
                    }
                    
                    f.write(json.dumps(payload) + "\n")
                    f.flush() 
                    
                    print(f"[{time.strftime('%H:%M:%S')}] Logged event {seq}")
                    seq += 1
                    
                time.sleep(args.sample_interval)

    except KeyboardInterrupt:
        print("\nLogging stopped.")
        sys.exit(0)

if __name__ == "__main__":
    main()