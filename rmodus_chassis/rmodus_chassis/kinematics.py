"""Wheel kinematics for diff2 / diff4 / mecanum (host side, rad/s at the wheel)."""

import numpy as np

MODES = ("diff2", "diff4", "mecanum")

WHEEL_NAMES = {
    "diff2": ("wheel_l", "wheel_r"),
    "diff4": ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"),
    "mecanum": ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr"),
}


class Kinematics:
    """Row i of the Jacobian maps body twist (vx, vy, wz) to wheel i speed in rad/s."""

    def __init__(self, mode, wheel_names, wheel_radius, track_width, wheelbase):
        if mode not in MODES:
            raise ValueError(f"unknown drive mode '{mode}', expected one of {MODES}")
        if wheel_radius <= 0.0:
            raise ValueError("wheel_radius must be > 0")
        if track_width <= 0.0:
            raise ValueError("track_width must be > 0")
        if mode == "mecanum" and wheelbase <= 0.0:
            raise ValueError("mecanum needs wheelbase > 0")

        allowed = WHEEL_NAMES[mode]
        for name in wheel_names:
            if name not in allowed:
                raise ValueError(
                    f"wheel '{name}' is not valid for mode '{mode}', expected {allowed}"
                )

        self.mode = mode
        self.holonomic = mode == "mecanum"
        half_track = track_width / 2.0
        lever = (wheelbase + track_width) / 2.0
        r = wheel_radius

        rows = {
            "diff2": {
                "wheel_l": (1.0, 0.0, -half_track),
                "wheel_r": (1.0, 0.0, half_track),
            },
            "diff4": {
                "wheel_fl": (1.0, 0.0, -half_track),
                "wheel_rl": (1.0, 0.0, -half_track),
                "wheel_fr": (1.0, 0.0, half_track),
                "wheel_rr": (1.0, 0.0, half_track),
            },
            "mecanum": {
                "wheel_fl": (1.0, -1.0, -lever),
                "wheel_fr": (1.0, 1.0, lever),
                "wheel_rl": (1.0, 1.0, -lever),
                "wheel_rr": (1.0, -1.0, lever),
            },
        }[mode]
        self.jacobian = np.array([rows[n] for n in wheel_names], dtype=float) / r

    def inverse(self, vx, vy, wz, max_wheel_speed=0.0):
        """Body twist -> wheel speeds [rad/s]; scales all wheels down if one exceeds the limit."""
        if not self.holonomic:
            vy = 0.0
        speeds = self.jacobian @ np.array([vx, vy, wz], dtype=float)
        if max_wheel_speed > 0.0 and speeds.size:
            peak = float(np.max(np.abs(speeds)))
            if peak > max_wheel_speed:
                speeds *= max_wheel_speed / peak
        return speeds

    def forward(self, indices, wheel_values):
        """Least-squares body motion from a subset of wheels (rad or rad/s).

        Returns (vx, vy, wz) or None when the subset cannot observe the motion
        (e.g. only left wheels of a diff drive).
        """
        if not indices:
            return None
        cols = [0, 1, 2] if self.holonomic else [0, 2]
        a = self.jacobian[np.ix_(indices, cols)]
        b = np.asarray(wheel_values, dtype=float)
        sol, _res, rank, _sv = np.linalg.lstsq(a, b, rcond=None)
        if rank < len(cols):
            return None
        if self.holonomic:
            return float(sol[0]), float(sol[1]), float(sol[2])
        return float(sol[0]), 0.0, float(sol[1])
