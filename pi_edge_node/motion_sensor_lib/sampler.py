"""
sampler.py  —  reads the raw state of an HC-SR501 PIR sensor.

Responsibility (single):  give the rest of the pipeline a clean boolean reading
of the sensor pin, and nothing else.

Uses gpiozero's DigitalInputDevice. This is a hardware-only component and must
run on a Raspberry Pi (or any machine with a real GPIO backend).
"""

from __future__ import annotations

from gpiozero import DigitalInputDevice


class PirSampler:
    """Reads the digital output pin of a PIR motion sensor.

    Args:
        pin:  BCM GPIO pin number the PIR data line is wired to.

    The public contract is intentionally tiny:

        sampler = PirSampler(pin=17)
        sampler.read()   # -> True (HIGH / motion) or False (LOW / clear)
    """

    def __init__(self, pin: int = 17):
        self.pin = pin
        self._dev = DigitalInputDevice(pin)

    def read(self) -> bool:
        """Return the current sensor state.

        Returns:
            True  if the signal is HIGH (motion present),
            False if the signal is LOW (no motion).
        """
        return bool(self._dev.value)
