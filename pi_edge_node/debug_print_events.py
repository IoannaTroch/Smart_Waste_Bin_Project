import time
import argparse
import sys

# Import the custom sensor library we just built
from motion_sensor_lib.sampler import PirSampler
from motion_sensor_lib.interpreter import PirInterpreter

def main():
    # Set up command line arguments
    p = argparse.ArgumentParser(description="PIR Sensor Debug Printer")
    p.add_argument("--pin", type=int, required=True, help="GPIO pin number (e.g., 17)")
    p.add_argument("--cooldown", type=float, default=5.0, help="Cooldown in seconds after motion")
    p.add_argument("--min-high", type=float, default=0.2, help="Minimum time (seconds) to confirm motion")
    args = p.parse_args()

    print(f"Initializing PIR sensor on Pin {args.pin}...")
    print(f"Settings: Cooldown={args.cooldown}s, Min-High={args.min_high}s")

    # Initialize hardware and logic
    sampler = PirSampler(args.pin)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    print("\n--- Monitoring for Motion (Press Ctrl+C to exit) ---")

    try:
        while True:
            now = time.time()
            
            # 1. Read the physical pin
            raw_state = sampler.read()
            
            # 2. Pass it to the 'brain' to filter noise
            events = interp.update(raw_state, now)
            
            # 3. Print any valid events that pop out
            for ev in events:
                # Get human readable time
                current_time = time.strftime('%H:%M:%S')
                print(f"[{current_time}] 🚨 MOTION DETECTED! (Timestamp: {ev['t']:.2f})")
            
            # Sleep briefly to avoid maxing out the Pi's CPU
            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nDebug monitoring stopped by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()