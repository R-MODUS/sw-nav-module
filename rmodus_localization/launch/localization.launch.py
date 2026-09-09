"""Localization: EKF + optional rf2o / slam_toolbox / obstacle_cloud."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import PackageNotFoundError, get_package_share_directory

import os
import yaml


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


def _flags_from_yaml(path: str) -> dict:
    defaults = {
        "localization": True,
        "slam": True,
        "rf2o": False,
        "obstacle_cloud": True,
    }
    if not path or not os.path.isfile(path):
        return defaults
    with open(path, "r", encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    if not isinstance(root, dict):
        return defaults
    b = root.get("bringup", {})
    if not isinstance(b, dict):
        return defaults
    out = dict(defaults)
    for key in out:
        if key in b:
            out[key] = bool(b[key])
    # legacy nested autonomy block
    auto = b.get("autonomy", {})
    if isinstance(auto, dict):
        for key in out:
            if key in auto:
                out[key] = bool(auto[key])
    return out


def _flag(v: bool) -> str:
    return "true" if v else "false"


def _arg_or_yaml(context, name: str, yaml_key: str, from_yaml: dict) -> str:
    raw = LaunchConfiguration(name).perform(context).strip().lower()
    if raw in ("true", "false", "1", "0", "yes", "no", "on", "off"):
        return "true" if raw in ("true", "1", "yes", "on") else "false"
    return _flag(from_yaml[yaml_key])


def _create(context):
    pkg = FindPackageShare("rmodus_localization")
    use_sim_time = LaunchConfiguration("use_sim_time")
    robot_config_file = LaunchConfiguration("robot_config_file")
    global_params_file = LaunchConfiguration("global_params_file")
    rf2o_params = LaunchConfiguration("rf2o_params_file")
    slam_params = LaunchConfiguration("slam_params_file")

    yaml_path = _resolve(LaunchConfiguration("global_params_file").perform(context)) or _resolve(
        LaunchConfiguration("robot_config_file").perform(context)
    )
    from_yaml = _flags_from_yaml(yaml_path)

    localization = _arg_or_yaml(context, "localization", "localization", from_yaml)
    slam = _arg_or_yaml(context, "slam", "slam", from_yaml)
    rf2o = _arg_or_yaml(context, "rf2o", "rf2o", from_yaml)
    obstacle_cloud = _arg_or_yaml(context, "obstacle_cloud", "obstacle_cloud", from_yaml)

    actions = []
    if localization != "true":
        actions.append(LogInfo(msg="[rmodus_localization] localization=false — nic nespouštím"))
        return actions

    if not _pkg_ok("robot_localization"):
        actions.append(
            LogInfo(
                msg=(
                    "[rmodus_localization] missing robot_localization — "
                    "cannot start EKF. Install ros-${ROS_DISTRO}-robot-localization."
                )
            )
        )
        return actions

    actions.append(
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([pkg, "launch", "ekf_dynamic.launch.py"])
            ),
            launch_arguments={
                "use_sim_time": use_sim_time,
                "robot_config_file": robot_config_file,
                "global_params_file": global_params_file,
            }.items(),
        )
    )

    if rf2o == "true":
        if _pkg_ok("rf2o_laser_odometry"):
            actions.append(
                Node(
                    package="rf2o_laser_odometry",
                    executable="rf2o_laser_odometry_node",
                    name="rf2o_laser_odometry",
                    parameters=[rf2o_params, {"use_sim_time": use_sim_time}],
                    output="screen",
                    emulate_tty=True,
                )
            )
        else:
            actions.append(
                LogInfo(
                    msg=(
                        "[rmodus_localization] rf2o=true but package rf2o_laser_odometry "
                        "not found — skipped (optional)."
                    )
                )
            )

    if slam == "true":
        if _pkg_ok("slam_toolbox"):
            actions.append(
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(
                        PathJoinSubstitution(
                            [
                                FindPackageShare("slam_toolbox"),
                                "launch",
                                "online_async_launch.py",
                            ]
                        )
                    ),
                    launch_arguments={
                        "slam_params_file": slam_params,
                        "use_sim_time": use_sim_time,
                    }.items(),
                )
            )
        else:
            actions.append(
                LogInfo(
                    msg=(
                        "[rmodus_localization] slam=true but package slam_toolbox "
                        "not found — skipped (optional)."
                    )
                )
            )

    if obstacle_cloud == "true":
        actions.append(
            Node(
                package="rmodus_localization",
                executable="obstacle_cloud",
                name="obstacle_cloud",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
                emulate_tty=True,
            )
        )

    return actions


def generate_launch_description():
    pkg = FindPackageShare("rmodus_localization")
    default_robot = PathJoinSubstitution(
        [FindPackageShare("rmodus_description"), "config", "default_robot_config.yaml"]
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument("localization", default_value=""),
            DeclareLaunchArgument("slam", default_value=""),
            DeclareLaunchArgument("rf2o", default_value=""),
            DeclareLaunchArgument("obstacle_cloud", default_value=""),
            DeclareLaunchArgument("global_params_file", default_value=""),
            DeclareLaunchArgument("robot_config_file", default_value=default_robot),
            DeclareLaunchArgument(
                "rf2o_params_file",
                default_value=PathJoinSubstitution([pkg, "config", "rf2o_params.yaml"]),
            ),
            DeclareLaunchArgument(
                "slam_params_file",
                default_value=PathJoinSubstitution([pkg, "config", "slam_params.yaml"]),
            ),
            OpaqueFunction(function=_create),
        ]
    )
