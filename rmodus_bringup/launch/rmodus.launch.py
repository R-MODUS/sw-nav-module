"""Jediný entrypoint R-MODUS — spouští rmodus_* balíčky podle profilu bringup:."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory

import os
import yaml

from rmodus_bringup.package_gates import missing_packages, package_available, skip_log


_DEFAULT_BRINGUP = {
    "chassis": True,
    "description": True,
    "hw": True,
    "uart_output": True,
    "estop": True,
    "bumper": True,
    "cliff": True,
    "flow": True,
    "display": True,
    "web": True,
    "rviz": False,
    "sim": False,
    "localization": True,
    "navigation": True,
    "slam": True,
    "rf2o": False,
    "obstacle_cloud": True,
}

# bringup flag → ROS package that must exist to include
_OPTIONAL_RM_PKGS = {
    "chassis": "rmodus_chassis",
    "description": "rmodus_description",
    "hw": "rmodus_hw",
    "uart_output": "rmodus_uart_output",
    "estop": "rmodus_estop",
    "bumper": "rmodus_bumper",
    "cliff": "rmodus_cliff_sensor",
    "flow": "rmodus_flow_sensor",
    "display": "rmodus_display",
    "web": "rmodus_web",
    "localization": "rmodus_localization",
    "navigation": "rmodus_navigation",
    "sim": "rmodus_gazebo",
}


def _resolve(path: str) -> str:
    if not path:
        return ""
    return os.path.normpath(os.path.expanduser(str(path).strip()))


def _load_bringup(path: str) -> dict:
    cfg = dict(_DEFAULT_BRINGUP)
    if not path or not os.path.isfile(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    if not isinstance(root, dict):
        return cfg
    block = root.get("bringup", {})
    if not isinstance(block, dict):
        return cfg
    for key in cfg:
        if key in block:
            cfg[key] = bool(block[key])
    # legacy: bringup.autonomy.*
    auto = block.get("autonomy", {})
    if isinstance(auto, dict):
        for key in ("localization", "navigation", "slam", "rf2o", "obstacle_cloud"):
            if key in auto:
                cfg[key] = bool(auto[key])
    return cfg


def _flag(v: bool) -> str:
    return "true" if v else "false"


def _build(context):
    robot_yaml = _resolve(LaunchConfiguration("robot_yaml").perform(context))
    if not robot_yaml:
        robot_yaml = os.path.join(
            get_package_share_directory("rmodus_bringup"), "config", "robot.yaml"
        )

    b = _load_bringup(robot_yaml)
    actions = [
        LogInfo(msg=f"[rmodus_bringup] profile={robot_yaml}"),
        LogInfo(msg=f"[rmodus_bringup] flags={b}"),
    ]

    def _include(pkg: str, launch_file: str, **launch_arguments):
        return IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([FindPackageShare(pkg), "launch", launch_file])
            ),
            launch_arguments=launch_arguments.items(),
        )

    def _try_feature(flag: str, pkg: str, launch_file: str, **launch_arguments):
        if not b.get(flag, False):
            return
        if not package_available(pkg):
            actions.append(skip_log(flag, pkg))
            return
        actions.append(_include(pkg, launch_file, **launch_arguments))

    # TF: one RSP — description composes chassis when both enabled and present.
    want_desc = b["description"]
    want_chassis = b["chassis"]
    if want_desc:
        if package_available("rmodus_description"):
            include_chassis = want_chassis and package_available("rmodus_chassis")
            if want_chassis and not include_chassis:
                actions.append(skip_log("chassis", "rmodus_chassis"))
            actions.append(
                _include(
                    "rmodus_description",
                    "description.launch.py",
                    use_sim_time="false",
                    robot_config_file=robot_yaml,
                    override_config_path=robot_yaml,
                    include_chassis=_flag(include_chassis),
                )
            )
        else:
            actions.append(skip_log("description", "rmodus_description"))
            if want_chassis:
                _try_feature(
                    "chassis",
                    "rmodus_chassis",
                    "chassis.launch.py",
                    use_sim_time="false",
                    robot_config_file=robot_yaml,
                )
    elif want_chassis:
        _try_feature(
            "chassis",
            "rmodus_chassis",
            "chassis.launch.py",
            use_sim_time="false",
            robot_config_file=robot_yaml,
        )

    _try_feature("hw", "rmodus_hw", "hw.launch.py", user_params_file=robot_yaml)
    _try_feature(
        "uart_output", "rmodus_uart_output", "uart_output.launch.py", config_file=robot_yaml
    )
    _try_feature("estop", "rmodus_estop", "estop.launch.py", config_file=robot_yaml)
    _try_feature("bumper", "rmodus_bumper", "bumper.launch.py", config_file=robot_yaml)
    _try_feature(
        "cliff", "rmodus_cliff_sensor", "cliff_sensor.launch.py", config_file=robot_yaml
    )
    _try_feature(
        "flow", "rmodus_flow_sensor", "flow_sensor.launch.py", config_file=robot_yaml
    )
    _try_feature("display", "rmodus_display", "display.launch.py", config_file=robot_yaml)
    _try_feature("web", "rmodus_web", "web.launch.py", robot_yaml=robot_yaml)

    if b["localization"] or b["slam"] or b["rf2o"] or b["obstacle_cloud"]:
        if package_available("rmodus_localization"):
            actions.append(
                _include(
                    "rmodus_localization",
                    "localization.launch.py",
                    use_sim_time="false",
                    robot_config_file=robot_yaml,
                    global_params_file=robot_yaml,
                    localization=_flag(b["localization"]),
                    slam=_flag(b["slam"]),
                    rf2o=_flag(b["rf2o"]),
                    obstacle_cloud=_flag(b["obstacle_cloud"]),
                )
            )
        else:
            actions.append(skip_log("localization", "rmodus_localization"))

    if b["navigation"]:
        if package_available("rmodus_navigation"):
            actions.append(
                _include(
                    "rmodus_navigation",
                    "navigation.launch.py",
                    use_sim_time="false",
                    robot_yaml=robot_yaml,
                    navigation="true",
                )
            )
        else:
            actions.append(skip_log("navigation", "rmodus_navigation"))

    if b["sim"]:
        if package_available("rmodus_gazebo"):
            gz_missing = missing_packages(["ros_gz_sim", "ros_gz_bridge"])
            if gz_missing:
                actions.append(skip_log("sim/gazebo-runtime", gz_missing))
            else:
                actions.append(
                    LogInfo(
                        msg=(
                            "[rmodus_bringup] bringup.sim=true: rmodus_gazebo is present, "
                            "but sim launch wiring is still reserved (not started yet)."
                        )
                    )
                )
        else:
            actions.append(skip_log("sim", "rmodus_gazebo"))

    if b["rviz"]:
        if package_available("rviz2"):
            actions.append(_include("rmodus_bringup", "rviz.launch.py", use_sim_time="false"))
        else:
            actions.append(skip_log("rviz", "rviz2"))

    return actions


def generate_launch_description():
    pkg_share = FindPackageShare("rmodus_bringup")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "robot_yaml",
                default_value=PathJoinSubstitution([pkg_share, "config", "robot.yaml"]),
                description="Profil s bringup: + /**/ros__parameters",
            ),
            OpaqueFunction(function=_build),
        ]
    )
