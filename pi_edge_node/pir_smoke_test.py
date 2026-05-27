#!/usr/bin/env python3
"""
pir_smoke_test.py  —  lowest-level hardware check (Milestone 2 / Lab 02).

Talks straight to the GPIO pin (no library, no filtering) and prints every time
the raw voltage changes. Use this first to prove the PIR is wired correctly
(5V, GND, DATA) before running anything fancier.

    python pir_smoke_test.py --pin 17
    python pir_smoke_test.py --simulate      # no Raspberry Pi needed
"""

import argparse
import sys
import time


def _make_sensor(pin: int, simulate: bool):
    """Return a callable read() -> bool, real or simulated."""
    if not simulate:
        try:
            from gpiozero import DigitalInputDevice
            dev = DigitalInputDevice(pin)
            return lambda: bool(dev.value)
        except Exception as exc:
            print(f"[smoke] gpiozero unavailable ({exc}); using SIMULATION.")
    # simulated: toggle roughly every 2 seconds
    t0 = time.time()
    return lambda: ((time.time() - t0) % 4.0) < 1.0


def main() -> None:
    p = argparse.ArgumentParser(description="PIR Hardware Smoke Test")
    p.add_argument("--pin", type=int, default=17, help="GPIO pin (BCM numbering)")
    p.add_argument("--simulate", action="store_true", help="Run without real GPIO")
    args = p.parse_args()

    print(f"--- PIR Hardware Smoke Test on pin {args.pin} ---")
    read = _make_sensor(args.pin, args.simulate)

    print("Warming up the PIR lens (2 s)...")
    time.sleep(2)
    print("Ready! Wave your hand in front of the sensor.  (Ctrl-C to stop)\n")

    previous = None
    try:
        while True:
            current = read()
            if current != previous:
                ts = time.strftime("%H:%M:%S")
                print(f"[{ts}] {'Motion!' if current else 'No motion'}")
                previous = current
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nSmoke test stopped by user.")
        sys.exit(0)
    except Exception as exc:
        print(f"\nHardware error: {exc}")
        print("Check your 5V, GND, and DATA wires!")
        sys.exit(1)


if __name__ == "__main__":
    main()
