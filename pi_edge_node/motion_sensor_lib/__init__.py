"""
motion_sensor_lib  —  Smart Waste Bin edge-node sensing library (Milestone 3 / Lab 03).

This package splits the edge-node logic into reusable, replaceable components:

    PirSampler      reads the raw electrical state of the HC-SR501 PIR pin.
    PirInterpreter  turns the noisy raw stream into clean "motion_detected" events
                    (debounce + cooldown).

Both components are pure-Python and hardware-agnostic: PirSampler falls back to a
deterministic simulation when `gpiozero` is unavailable (e.g. on a laptop), so the
whole pipeline can be developed and demoed without a Raspberry Pi.
"""

from .sampler import PirSampler
from .interpreter import PirInterpreter

__all__ = ["PirSampler", "PirInterpreter"]
__version__ = "1.0.0"
