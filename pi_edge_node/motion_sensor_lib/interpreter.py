from typing import Optional, List, Dict

class PirInterpreter:
    def __init__(self, cooldown_s: float = 0.0, min_high_s: float = 0.0):
        # How long to wait before allowing a new event
        self.cooldown_s = cooldown_s
        # How long the signal must stay HIGH to be considered "real" motion (filters out noise)
        self.min_high_s = min_high_s

        # State tracking variables
        self.prev_raw = False
        self.high_start_t: Optional[float] = None
        self.emitted_for_this_high = False
        self.last_emit_t: Optional[float] = None

    def update(self, raw: bool, t: float) -> List[Dict]:
        events: List[Dict] = []

        # Detect if the signal just changed
        rising = (not self.prev_raw) and raw
        falling = self.prev_raw and (not raw)

        # If it just went HIGH, start the timer
        if rising:
            self.high_start_t = t
            self.emitted_for_this_high = False

        # If it just went LOW, reset
        if falling:
            self.high_start_t = None
            self.emitted_for_this_high = False

        # CORE LOGIC: Should we emit an event?
        # If currently HIGH, and we haven't emitted yet for this specific movement...
        if raw and (not self.emitted_for_this_high) and (self.high_start_t is not None):
            high_for = t - self.high_start_t
            
            # 1. Did it stay HIGH long enough to pass the noise filter?
            if high_for >= self.min_high_s:
                
                # 2. Are we outside the cooldown window?
                in_cd = self.last_emit_t is not None and (t - self.last_emit_t) < self.cooldown_s
                
                if not in_cd:
                    # WE HAVE A VALID EVENT!
                    events.append({"kind": "motion_detected", "t": t})
                    self.last_emit_t = t
                    self.emitted_for_this_high = True # Prevent spamming until it goes LOW again

        # Save current state for the next fraction of a second
        self.prev_raw = raw
        return events