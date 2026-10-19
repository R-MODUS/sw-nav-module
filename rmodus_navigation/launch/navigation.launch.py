"""Navigation: Nav2 (optional — skipped if Nav2 packages are not installed).

Slam true: mapu drží slam_toolbox, tady se nespouští AMCL ani map_server.
Slam false a map.yaml_filename: map_server + AMCL.
Slam false a prázdná mapa: AMCL se nespustí, NavigateToPose je přeskočené.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import PackageNotFoundError, get_package_share_directory

import os

from rmodus_navigation.nav_params import (
    load_robot_parameters,
    map_yaml_from_parameters,
    navigation_sources,
)

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
_MAP_PKGS = ("nav2_amcl", "nav2_map_server")


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


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "y")


def _bringup_flag(path: str, key: str, default: bool) -> bool:
    if not path or not os.path.isfile(path):
        return default
    import yaml

    with open(path, "r", encoding="utf-8") as handle:
        root = yaml.safe_load(handle) or {}
    if not isinstance(root, dict):
        return default
    block = root.get("bringup", {})
    if not isinstance(block, dict):
        return default
    if key in block:
        return _as_bool(block[key])
    auto = block.get("autonomy", {})
    if isinstance(auto, dict) and key in auto:
        return _as_bool(auto[key])
    return default


def _want_flag(path: str, arg_raw: str, key: str, default: bool) -> bool:
    raw = (arg_raw or "").strip().lower()
    if raw in ("true", "1", "yes", "on"):
        return True
    if raw in ("false", "0", "no", "off"):
        return False
    return _bringup_flag(path, key, default)


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _create(context):
    use_sim_time = LaunchConfiguration("use_sim_time")
    params_file = LaunchConfiguration("params_file")
    yaml_path = _resolve(LaunchConfiguration("robot_yaml").perform(context))
    nav_arg = LaunchConfiguration("navigation").perform(context)
    slam_arg = LaunchConfiguration("slam").perform(context)
    map_arg = LaunchConfiguration("map").perform(context).strip()

    if not _want_flag(yaml_path, nav_arg, "navigation", True):
        return [LogInfo(msg="[rmodus_navigation] navigation=false — nic nespouštím")]

    missing = [name for name in _NAV2_PKGS if not _pkg_ok(name)]
    if missing:
        return [
            LogInfo(
                msg=(
                    "[rmodus_navigation] navigation requested but Nav2 packages missing: "
                    f"{', '.join(missing)}. Skipped (optional — install via sw_install / apt)."
                )
            )
        ]

    robot_params = load_robot_parameters(yaml_path)
    slam = _want_flag(yaml_path, slam_arg, "slam", True)
    map_yaml = map_arg or map_yaml_from_parameters(robot_params)
    sources = navigation_sources(slam, map_yaml, os.path.isfile(map_yaml) if map_yaml else False)
    start_amcl = sources["start_amcl"]
    start_navigate = sources["start_navigate"]

    actions = []
    if sources["reason"] == "slam":
        actions.append(
            LogInfo(
                msg=(
                    "[rmodus_navigation] slam=true — mapu a map→odom drží slam_toolbox, "
                    "AMCL a map_server se nespouští."
                )
            )
        )
    elif sources["reason"] == "saved":
        missing_map = [name for name in _MAP_PKGS if not _pkg_ok(name)]
        if missing_map:
            start_amcl = False
            start_navigate = False
            actions.append(
                LogInfo(
                    msg=(
                        "[rmodus_navigation] uložená mapa je, ale chybí "
                        f"{', '.join(missing_map)} — AMCL a map_server přeskočeny (optional). "
                        "NavigateToPose je přeskočené, lokální costmapa může běžet dál."
                    )
                )
            )
        else:
            start_amcl = True
            start_navigate = True
            actions.append(
                LogInfo(
                    msg=(
                        "[rmodus_navigation] slam=false — map_server a AMCL, "
                        f"mapa {map_yaml}. slam_toolbox se nespouští."
                    )
                )
            )
    else:
        start_amcl = False
        start_navigate = False
        if map_yaml:
            why = f"soubor mapy neexistuje: {map_yaml}"
        else:
            why = "bringup.slam je false a map.yaml_filename je prázdný"
        actions.append(
            LogInfo(
                msg=(
                    f"[rmodus_navigation] navigace nemá zdroj mapy ({why}) — "
                    "AMCL a map_server se nespouští, NavigateToPose je přeskočené. "
                    "Lokální costmapa může běžet dál."
                )
            )
        )

    actions.append(
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution(
                    [FindPackageShare("rmodus_navigation"), "launch", "nav2.launch.py"]
                )
            ),
            launch_arguments={
                "params_file": params_file,
                "use_sim_time": use_sim_time,
                "cmd_vel_topic": LaunchConfiguration("cmd_vel_topic"),
                "robot_yaml": yaml_path,
                "map": map_yaml,
                "start_amcl": _flag(start_amcl),
                "start_navigate": _flag(start_navigate),
            }.items(),
        )
    )
    return actions


def generate_launch_description():
    pkg = FindPackageShare("rmodus_navigation")
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument("navigation", default_value=""),
            DeclareLaunchArgument("slam", default_value=""),
            DeclareLaunchArgument("robot_yaml", default_value=""),
            DeclareLaunchArgument(
                "map",
                default_value="",
                description="Cesta k yaml mapy. Prázdné = map.yaml_filename z robot_yaml.",
            ),
            DeclareLaunchArgument("cmd_vel_topic", default_value="/nav/cmd_vel"),
            DeclareLaunchArgument(
                "params_file",
                default_value=PathJoinSubstitution([pkg, "config", "nav2_params.yaml"]),
            ),
            OpaqueFunction(function=_create),
        ]
    )
