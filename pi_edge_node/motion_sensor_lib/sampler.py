"""
sampler.py  —  reads the raw state of an HC-SR501 PIR sensor.

Responsibility (single):  give the rest of the pipeline a clean boolean reading
of the sensor pin, and nothing else.

On a Raspberry Pi this uses gpiozero's DigitalInputDevice. On any other machine
(or if gpiozero / a GPIO backend is missing) it transparently falls back to a
lightweight simulator so the edge-node code can still be imported, tested and
demoed on a laptop.
"""

from __future__ import annotations

import os
import random
import time


class PirSampler:
    """Reads the digital output pin of a PIR motion sensor.

    Args:
        pin:       BCM GPIO pin number the PIR data line is wired to.
        simulate:  Force simulation mode (ignore real GPIO even on a Pi).

    The public contract is intentionally tiny:

        sampler = PirSampler(pin=17)
        sampler.read()   # -> True (HIGH / motion) or False (LOW / clear)
    """

    def __init__(self, pin: int = 17, simulate: bool = False):
        self.pin = pin
        self.simulate = simulate or os.getenv("PIR_SIMULATE", "0") == "1"
        self._dev = None
        self._sim_t0 = time.time()

        if not self.simulate:
            try:
                from gpiozero import DigitalInputDevice  # imported lazily
                self._dev = DigitalInputDevice(pin)
            except Exception as exc:  # pragma: no cover - hardware specific
                print(f"[PirSampler] gpiozero unavailable ({exc.__class__.__name__}); "
                      f"falling back to SIMULATION mode.")
                self.simulate = True

    def read(self) -> bool:
        """Return the current sensor state.

        Returns:
            True  if the signal is HIGH (motion present),
            False if the signal is LOW (no motion).
        """
        if self.simulate:
            return self._read_simulated()
        return bool(self._dev.value)

    # ── Simulation ────────────────────────────────────────────────────────────
    def _read_simulated(self) -> bool:
        """Deterministic-ish simulator.

        Produces realistic bursts of motion: roughly a couple of short HIGH
        windows every ~10 seconds, so the downstream interpreter and the whole
        MQTT pipeline can be exercised end-to-end with no hardware attached.
        """
        phase = (time.time() - self._sim_t0) % 10.0
        # Two motion windows per 10 s cycle: 1.0-1.6 s and 5.0-5.4 s
        in_window = (1.0 <= phase <= 1.6) or (5.0 <= phase <= 5.4)
        if in_window:
            return random.random() < 0.9   # mostly HIGH while "moving"
        return random.random() < 0.02      # rare noise spike otherwise
