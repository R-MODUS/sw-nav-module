"""Navigation: Nav2 (optional — skipped if Nav2 packages are not installed)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import PackageNotFoundError, get_package_share_directory

import os
import yaml

_NAV2_PKGS = (
    "nav2_common",
    "nav2_controller",
    "nav2_smoother",
    "nav2_planner",
    "nav2_behaviors",
    "nav2_bt_navigator",
    "nav2_waypoint_follower",
    "nav2_velocity_smoother",
    "nav2_lifecycle_manager",
)


def _resolve(path: str) -> str:
    if not path:
        return ""
    return os.path.normpath(os.path.expanduser(str(path).strip()))


def _pkg_ok(name: str) -> bool:
    try:
        get_package_share_directory(name)
        return True
    except PackageNotFoundError:
        return False


def _want_navigation(path: str, arg_raw: str) -> bool:
    raw = (arg_raw or "").strip().lower()
    if raw in ("true", "1", "yes", "on"):
        return True
    if raw in ("false", "0", "no", "off"):
        return False
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            root = yaml.safe_load(f) or {}
        if isinstance(root, dict):
            b = root.get("bringup", {})
            if isinstance(b, dict):
                if "navigation" in b:
                    return bool(b["navigation"])
                auto = b.get("autonomy", {})
                if isinstance(auto, dict) and "navigation" in auto:
                    return bool(auto["navigation"])
    return True


def _create(context):
    use_sim_time = LaunchConfiguration("use_sim_time")
    params_file = LaunchConfiguration("params_file")
    yaml_path = _resolve(LaunchConfiguration("robot_yaml").perform(context))
    arg_raw = LaunchConfiguration("navigation").perform(context)

    if not _want_navigation(yaml_path, arg_raw):
        return [LogInfo(msg="[rmodus_navigation] navigation=false — nic nespouštím")]

    missing = [p for p in _NAV2_PKGS if not _pkg_ok(p)]
    if missing:
        return [
            LogInfo(
                msg=(
                    "[rmodus_navigation] navigation requested but Nav2 packages missing: "
                    f"{', '.join(missing)}. Skipped (optional — install via sw_install / apt)."
                )
            )
        ]

    return [
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution(
                    [FindPackageShare("rmodus_navigation"), "launch", "nav2.launch.py"]
                )
            ),
            launch_arguments={
                "params_file": params_file,
                "use_sim_time": use_sim_time,
            }.items(),
        )
    ]


def generate_launch_description():
    pkg = FindPackageShare("rmodus_navigation")
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument("navigation", default_value=""),
            DeclareLaunchArgument("robot_yaml", default_value=""),
            DeclareLaunchArgument(
                "params_file",
                default_value=PathJoinSubstitution([pkg, "config", "nav2_params.yaml"]),
            ),
            OpaqueFunction(function=_create),
        ]
    )
