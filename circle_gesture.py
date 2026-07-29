from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class CircleGestureTracker:
    """Track one continuous clockwise or counter-clockwise cursor orbit."""

    required_turns: float = 2.0
    max_sample_gap_ms: int = 450
    max_step_degrees: float = 100.0
    reverse_tolerance_degrees: float = 80.0

    def __post_init__(self) -> None:
        if self.required_turns <= 0:
            raise ValueError("required_turns 必须大于 0")
        if self.max_sample_gap_ms <= 0:
            raise ValueError("max_sample_gap_ms 必须大于 0")
        if not 0 < self.max_step_degrees < 180:
            raise ValueError("max_step_degrees 必须在 0～180 之间")
        if self.reverse_tolerance_degrees < 0:
            raise ValueError("reverse_tolerance_degrees 不能小于 0")
        self.reset()

    @property
    def rotation_degrees(self) -> float:
        return self._rotation_degrees

    @property
    def progress(self) -> float:
        required = self.required_turns * 360.0
        return min(self._rotation_degrees / required, 1.0)

    def reset(self) -> None:
        self._previous_angle: float | None = None
        self._last_sample_at: float | None = None
        self._direction = 0
        self._rotation_degrees = 0.0
        self._reverse_degrees = 0.0

    def sample(
        self,
        dx: float,
        dy: float,
        *,
        now: float,
        min_radius_px: float,
    ) -> bool:
        """Return True once after a valid orbit reaches ``required_turns``."""
        if math.hypot(dx, dy) < min_radius_px:
            self.reset()
            return False

        angle = math.degrees(math.atan2(dy, dx))
        if self._previous_angle is None or self._last_sample_at is None:
            self._start_at(angle, now)
            return False

        gap_ms = (now - self._last_sample_at) * 1000.0
        if gap_ms < 0 or gap_ms > self.max_sample_gap_ms:
            self.reset()
            self._start_at(angle, now)
            return False

        delta = (angle - self._previous_angle + 180.0) % 360.0 - 180.0
        self._previous_angle = angle
        self._last_sample_at = now

        if abs(delta) < 0.75:
            return False
        if abs(delta) > self.max_step_degrees:
            self.reset()
            self._start_at(angle, now)
            return False

        step_direction = 1 if delta > 0 else -1
        if self._direction == 0:
            self._direction = step_direction

        if step_direction == self._direction:
            self._rotation_degrees += abs(delta)
            self._reverse_degrees = max(0.0, self._reverse_degrees - abs(delta))
        else:
            reverse = abs(delta)
            self._reverse_degrees += reverse
            self._rotation_degrees = max(0.0, self._rotation_degrees - reverse)
            if (
                self._reverse_degrees > self.reverse_tolerance_degrees
                or self._rotation_degrees == 0.0
            ):
                self.reset()
                self._start_at(angle, now)
                self._direction = step_direction
                return False

        if self._rotation_degrees < self.required_turns * 360.0:
            return False

        self.reset()
        return True

    def _start_at(self, angle: float, now: float) -> None:
        self._previous_angle = angle
        self._last_sample_at = now
