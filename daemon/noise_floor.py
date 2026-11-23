"""The adaptive microphone gate: follow the room instead of a fixed number.

The gate decides which frames are somebody talking. That ends a turn, cuts
the second check's bursts and, on Vosk, guards the grammar. A fixed number
is right for one room: a fan coming on puts the noise above it, so a turn
never ends until max_utterance_ms, and a quiet evening leaves it far above
the floor, so a soft word is cut off.

So the gate here is the room's noise floor plus a margin:

- the floor is the median frame loudness over the last WINDOW_S seconds
  of the wake phase, which is mostly the room: a wake word is a second or
  two in a minute. Not a low percentile, because a TV or music has gaps,
  and a floor in the gaps puts the gate under the TV itself, which then
  holds every turn open (bench/gate_bench.py: 0.1 held 6 of 6 turns open
  beside a TV, 0.5 none; FINDINGS §27);
- it is only fed frames that cannot be anybody talking to us: the caller
  feeds it in the wake phase only, never during a capture, never while we
  speak and never inside the deaf window after;
- it moves slowly: up at `rise_db_per_s`, down at `fall_db_per_s` (shipped
  as RISE_DB_PER_S and FALL_DB_PER_S, and settable since master plan M23 as
  gateRiseTenths and gateFallTenths, within RISE_BOUNDS and FALL_BOUNDS).
  Falling is faster because a gate that is too high cuts words off, which
  is worse than holding a turn open a little longer. Plain attributes,
  changed in place: a new rate never forgets the room;
- the rates only limit how fast the floor may *follow* the median, and the
  median of a WINDOW_S window itself moves only when the new level is
  most of the window: after a step in the room's noise nothing happens for
  about half the window, whatever the rates (bench/gate_speed.py,
  FINDINGS §56);
- the gate is clamped to [GATE_MIN_DB, GATE_MAX_DB] so no room, however
  loud or silent, can make it absurd;
- until WARMUP_S of frames have been seen, the fixed gate stands.

Pure: numbers in, numbers out, no numpy. The frame loop feeds it.
"""
from __future__ import annotations

from collections import deque

#: How much room is remembered, in seconds of eligible frames.
WINDOW_S = 30.0
#: The percentile taken as the floor: the median. See the module docstring.
PERCENTILE = 0.50
#: Frames needed before the estimate replaces the fixed gate.
WARMUP_S = 3.0
#: How fast the floor may move, dB per second of fed frames.
RISE_DB_PER_S = 0.5
FALL_DB_PER_S = 3.0
#: The range either rate may be set to, dB per second (master plan M23). A
#: floor that could jump straight to whatever the median says would follow a
#: burst of talk the wake phase let through; one that could not move at all
#: would be the fixed gate with extra steps.
RISE_BOUNDS = (0.1, 3.0)
FALL_BOUNDS = (0.5, 10.0)
#: The page's "adapts slow / normal / fast", in the settings' own units
#: (tenths of a dB per second): (gateRiseTenths, gateFallTenths). Normal is
#: the shipped pair. pages/ListeningPage.qml writes the same numbers, and a
#: test holds the two in step.
SPEEDS = {"slow": (2, 15), "normal": (5, 30), "fast": (15, 80)}
#: Hard limits on the gate itself, whatever the room says.
GATE_MIN_DB = -55.0
GATE_MAX_DB = -25.0
#: How much lower the wake word's gate sits than the one that ends a turn.
#: A wake name is short and its quiet syllables matter: at the full margin
#: the second check's bursts lost them, and wakes beside a TV fell from 11
#: to 8 of 12 (FINDINGS §27). Ending a turn wants the full margin, so the
#: room cannot hold it open; hearing a name wants a little less.
WAKE_SLACK_DB = 6.0
#: The margin above the floor, when none is configured.
MARGIN_DB = 10
MARGIN_MIN, MARGIN_MAX = 3, 25


class NoiseFloor:
    def __init__(self, frame_ms: int, margin_db: float = MARGIN_DB) -> None:
        self.frame_s = frame_ms / 1000.0
        self.margin_db = float(margin_db)
        #: dB per second of fed frames; see set_rates().
        self.rise_db_per_s = RISE_DB_PER_S
        self.fall_db_per_s = FALL_DB_PER_S
        self._levels: deque[float] = deque(maxlen=max(1, int(WINDOW_S / self.frame_s)))
        self._warm = max(1, int(WARMUP_S / self.frame_s))
        #: The floor as it stands, after the slew; None while warming up.
        self.floor_db: float | None = None

    def set_rates(self, rise_db_per_s: float, fall_db_per_s: float) -> None:
        """How fast the floor may move, kept inside RISE_BOUNDS and
        FALL_BOUNDS. In place: the window and the floor so far are kept, so
        a slider move changes the next step and nothing already learned."""
        self.rise_db_per_s = _bounded(rise_db_per_s, RISE_BOUNDS, RISE_DB_PER_S)
        self.fall_db_per_s = _bounded(fall_db_per_s, FALL_BOUNDS, FALL_DB_PER_S)

    @property
    def ready(self) -> bool:
        return self.floor_db is not None

    def feed(self, level_db: float) -> None:
        """One frame that is the room, not a person talking to us."""
        self._levels.append(max(-99.0, float(level_db)))
        if len(self._levels) < self._warm:
            return
        target = self._percentile()
        if self.floor_db is None:
            # The first estimate is taken whole: there is nothing to slew
            # from, and the fixed gate held until now.
            self.floor_db = target
            return
        step = target - self.floor_db
        up, down = self.rise_db_per_s * self.frame_s, self.fall_db_per_s * self.frame_s
        self.floor_db += max(-down, min(up, step))

    def gate(self, fixed_db: float) -> float:
        """The gate to use: the fixed one until warm, then floor + margin."""
        if self.floor_db is None:
            return float(fixed_db)
        return max(GATE_MIN_DB, min(GATE_MAX_DB, self.floor_db + self.margin_db))

    def wake_gate(self, fixed_db: float) -> float:
        """The gate the wake word's own checks use; see WAKE_SLACK_DB."""
        if self.floor_db is None:
            return float(fixed_db)
        return max(GATE_MIN_DB, self.gate(fixed_db) - WAKE_SLACK_DB)

    def reset(self) -> None:
        self._levels.clear()
        self.floor_db = None

    def _percentile(self) -> float:
        xs = sorted(self._levels)
        return xs[min(len(xs) - 1, int(PERCENTILE * len(xs)))]


def _bounded(value, bounds: tuple[float, float], default: float) -> float:
    """`value` as a float inside `bounds`; anything that is not a finite
    number is `default`."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    if x != x or x in (float("inf"), float("-inf")):
        return default
    return max(bounds[0], min(bounds[1], x))
