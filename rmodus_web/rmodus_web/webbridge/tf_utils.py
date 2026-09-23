"""Helpers for TF frame bookkeeping and conversions sent to the browser."""

import math
from collections import deque
from typing import Optional, Tuple

RATE_WINDOW_SAMPLES = 50


def quaternion_to_yaw(x: float, y: float, z: float, w: float) -> float:
    siny_cosp = 2.0 * (w * z + x * y)
    cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
    return math.atan2(siny_cosp, cosy_cosp)


class TfFrameRecord:
    """Latest transform parent → child plus receive history for rate / age metrics."""

    __slots__ = ("parent_frame_id", "child_frame_id", "translation", "rotation", "is_static", "rx_times")

    def __init__(self, child_frame_id: str):
        self.child_frame_id = child_frame_id
        self.parent_frame_id: Optional[str] = None
        self.translation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
        self.rotation: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)
        self.is_static = False
        self.rx_times: deque = deque(maxlen=RATE_WINDOW_SAMPLES)

    def update(self, parent_frame_id, translation, rotation, is_static: bool, now: float) -> None:
        if is_static != self.is_static:
            self.rx_times.clear()
        self.parent_frame_id = parent_frame_id
        self.translation = translation
        self.rotation = rotation
        self.is_static = is_static
        self.rx_times.append(now)

    def age_sec(self, now: float) -> Optional[float]:
        if not self.rx_times:
            return None
        return max(0.0, now - self.rx_times[-1])

    def rate_hz(self, now: float, dead_after_sec: float) -> Optional[float]:
        """Mean receive rate over the window; 0.0 once nothing arrived for dead_after_sec."""
        if self.is_static or len(self.rx_times) < 2:
            return None
        if now - self.rx_times[-1] > dead_after_sec:
            return 0.0
        span = self.rx_times[-1] - self.rx_times[0]
        if span <= 0.0:
            return None
        return (len(self.rx_times) - 1) / span

    def as_2d(self) -> dict:
        x, y, _z = self.translation
        return {
            "parent_frame_id": self.parent_frame_id,
            "child_frame_id": self.child_frame_id,
            "x": x,
            "y": y,
            "yaw": quaternion_to_yaw(*self.rotation),
            "is_static": self.is_static,
        }

    def as_3d(self, now: float, dead_after_sec: float) -> dict:
        age = self.age_sec(now)
        rate = self.rate_hz(now, dead_after_sec)
        return {
            "parent": self.parent_frame_id,
            "child": self.child_frame_id,
            "t": list(self.translation),
            "q": list(self.rotation),
            "static": self.is_static,
            "age": round(age, 4) if age is not None else None,
            "hz": round(rate, 2) if rate is not None else None,
        }
