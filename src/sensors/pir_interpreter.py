from typing import Optional, List, Dict

class PirInterpreter:
    def __init__(self, cooldown_s: float = 0.0, min_high_s: float = 0.0):
        self.cooldown_s = cooldown_s
        self.min_high_s = min_high_s

        self.prev_raw = False
        self.high_start_t: Optional[float] = None
        self.emitted_for_this_high = False
        self.last_emit_t: Optional[float] = None

    def update(self, raw: bool, t: float) -> List[Dict]:
        events: List[Dict] = []

        rising = (not self.prev_raw) and raw
        falling = self.prev_raw and (not raw)

        if rising:
            self.high_start_t = t
            self.emitted_for_this_high = False

        if falling:
            self.high_start_t = None
            self.emitted_for_this_high = False

        if raw and (not self.emitted_for_this_high) and (self.high_start_t is not None):
            high_for = t - self.high_start_t
            if high_for >= self.min_high_s:
                in_cd = self.last_emit_t is not None and (t - self.last_emit_t) < self.cooldown_s
                if not in_cd:
                    events.append({"kind": "motion_detected", "t": t})
                    self.last_emit_t = t
                    self.emitted_for_this_high = True

        self.prev_raw = raw
        return events