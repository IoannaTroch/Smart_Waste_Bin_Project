"""
motion_sensor_lib  —  Smart Waste Bin edge-node sensing library (Milestone 3 / Lab 03).

This package splits the edge-node logic into reusable, replaceable components:

    PirSampler      reads the raw electrical state of the HC-SR501 PIR pin.
    PirInterpreter  turns the noisy raw stream into clean "motion_detected" events
                    (debounce + cooldown).

PirSampler reads real GPIO via gpiozero, so the edge node runs on a Raspberry Pi.
PirInterpreter is pure Python and hardware-agnostic.
"""

from .sampler import PirSampler
from .interpreter import PirInterpreter

__all__ = ["PirSampler", "PirInterpreter"]
__version__ = "1.0.0"
