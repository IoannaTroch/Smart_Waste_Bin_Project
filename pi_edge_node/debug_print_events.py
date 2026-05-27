#!/usr/bin/env python3
"""
debug_print_events.py  —  prove the sensing library works (Milestone 2/3).

Wires PirSampler -> PirInterpreter and prints every *clean* motion event
(after debounce + cooldown). This is the human-readable sanity check that the
modular library behaves before we start shipping events over MQTT.

    python debug_print_events.py --pin 17
    python debug_print_events.py --simulate          # laptop-friendly
    python debug_print_events.py --pin 17 --cooldown 5 --min-high 0.2
"""

import argparse
import sys
import time

from motion_sensor_lib import PirSampler, PirInterpreter


def main() -> None:
    p = argparse.ArgumentParser(description="PIR Sensor Debug Printer")
    p.add_argument("--pin", type=int, default=17, help="GPIO pin (BCM)")
    p.add_argument("--cooldown", type=float, default=5.0,
                   help="Seconds to wait after an event before allowing another")
    p.add_argument("--min-high", type=float, default=0.2,
                   help="Seconds the signal must stay HIGH to count as motion")
    p.add_argument("--simulate", action="store_true", help="Run without real GPIO")
    args = p.parse_args()

    print(f"Initializing PIR on pin {args.pin}  "
          f"(cooldown={args.cooldown}s, min-high={args.min_high}s)")

    sampler = PirSampler(args.pin, simulate=args.simulate)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    print("\n--- Monitoring for motion (Ctrl-C to exit) ---")
    try:
        while True:
            now = time.time()
            raw = sampler.read()
            for ev in interp.update(raw, now):
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}]  MOTION DETECTED!  (t={ev['t']:.2f})")
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nDebug monitoring stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
