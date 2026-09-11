# Shared helpers for optional package gates (bringup / feature launches).

from __future__ import annotations

from ament_index_python.packages import PackageNotFoundError, get_package_share_directory
from launch.actions import LogInfo


def package_available(name: str) -> bool:
    try:
        get_package_share_directory(name)
        return True
    except PackageNotFoundError:
        return False


def missing_packages(names) -> list:
    return [n for n in names if not package_available(n)]


def skip_log(feature: str, missing) -> LogInfo:
    pkgs = ", ".join(missing) if isinstance(missing, (list, tuple)) else str(missing)
    return LogInfo(
        msg=(
            f"[rmodus] skip '{feature}': missing package(s): {pkgs}. "
            "Install via sw_install / apt, or set bringup flag to false."
        )
    )
