"""
interpreter.py  —  turns a noisy raw PIR stream into clean motion events.

Responsibility (single):  decide *when* a real "motion_detected" event has
happened, filtering out electrical noise and rate-limiting repeated triggers.

Two tunables:
    min_high_s   the signal must stay HIGH at least this long to count as motion
                 (rejects short noise spikes).
    cooldown_s   after emitting an event, ignore further triggers for this long
                 (debounce / rate-limit).

Usage:
    interp = PirInterpreter(cooldown_s=5.0, min_high_s=0.2)
    for raw in stream:
        for event in interp.update(raw, time.time()):
            print(event)   # {"kind": "motion_detected", "t": <epoch seconds>}
"""

from __future__ import annotations

from typing import Optional, List, Dict


class PirInterpreter:
    """Stateful edge-detector that emits one event per genuine motion burst."""

    def __init__(self, cooldown_s: float = 0.0, min_high_s: float = 0.0):
        self.cooldown_s = cooldown_s
        self.min_high_s = min_high_s

        # internal state
        self.prev_raw = False
        self.high_start_t: Optional[float] = None
        self.emitted_for_this_high = False
        self.last_emit_t: Optional[float] = None

    def update(self, raw: bool, t: float) -> List[Dict]:
        """Feed one raw reading; return a list of 0 or 1 events.

        Args:
            raw: current sensor state (True = HIGH).
            t:   timestamp in seconds (time.time() or time.monotonic()).
        """
        events: List[Dict] = []

        rising = (not self.prev_raw) and raw
        falling = self.prev_raw and (not raw)

        # Signal just went HIGH -> start timing how long it stays high.
        if rising:
            self.high_start_t = t
            self.emitted_for_this_high = False

        # Signal just went LOW -> reset.
        if falling:
            self.high_start_t = None
            self.emitted_for_this_high = False

        # Core rule: HIGH, not yet emitted for this burst, and we have a start.
        if raw and (not self.emitted_for_this_high) and (self.high_start_t is not None):
            high_for = t - self.high_start_t

            # 1) stayed high long enough to pass the noise filter?
            if high_for >= self.min_high_s:

                # 2) outside the cooldown window?
                in_cooldown = (
                    self.last_emit_t is not None
                    and (t - self.last_emit_t) < self.cooldown_s
                )
                if not in_cooldown:
                    events.append({"kind": "motion_detected", "t": t})
                    self.last_emit_t = t
                    self.emitted_for_this_high = True  # don't spam until it clears

        self.prev_raw = raw
        return events
