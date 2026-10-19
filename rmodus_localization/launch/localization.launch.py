"""Localization: EKF + optional rf2o / slam_toolbox / obstacle_cloud.

Výchozí profil je rmodus_bringup/config/rmodus.yaml. Home se tu nehledá.
Bringup předává zkompilovaný profil jako robot_config_file i global_params_file.
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import PackageNotFoundError, get_package_share_directory

import os

from rmodus_localization.ekf_config import iter_ekf_inputs
from rmodus_localization.profile_params import (
    force_key,
    load_merged_ros_parameters,
    read_yaml,
    write_yaml,
)
from rmodus_localization.sensor_frames import obstacle_sensor_params


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


def _flags_from_yaml(path: str) -> dict:
    defaults = {
        "localization": True,
        "slam": True,
        "rf2o": False,
        "obstacle_cloud": True,
    }
    if not path or not os.path.isfile(path):
        return defaults
    root = read_yaml(path)
    b = root.get("bringup", {})
    if not isinstance(b, dict):
        return defaults
    out = dict(defaults)
    for key in out:
        if key in b:
            out[key] = _as_bool(b[key])
    # legacy nested autonomy block
    auto = b.get("autonomy", {})
    if isinstance(auto, dict):
        for key in out:
            if key in auto:
                out[key] = _as_bool(auto[key])
    return out


def _flag(v: bool) -> str:
    return "true" if v else "false"


def _arg_or_yaml(context, name: str, yaml_key: str, from_yaml: dict) -> str:
    raw = LaunchConfiguration(name).perform(context).strip().lower()
    if raw in ("true", "false", "1", "0", "yes", "no", "on", "off"):
        return "true" if raw in ("true", "1", "yes", "on") else "false"
    return _flag(from_yaml[yaml_key])


def _use_sim(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def _lidar_topic(params: dict) -> str:
    lidar = params.get("lidar") if isinstance(params, dict) else None
    if isinstance(lidar, dict):
        topic = lidar.get("topic")
        if isinstance(topic, str) and topic.strip():
            return topic.strip()
    return "/scan"


def _lidar_odom_topic(params: dict) -> str:
    for name, _kind, topic in iter_ekf_inputs(params):
        if name == "lidar_odom":
            return topic
    block = params.get("lidar_odom") if isinstance(params, dict) else None
    if isinstance(block, dict):
        topic = block.get("topic")
        if isinstance(topic, str) and topic.strip():
            return topic.strip()
    return "/odom_lidar"


def _rf2o_has_ekf_input(params: dict) -> bool:
    return any(name == "lidar_odom" for name, _kind, _topic in iter_ekf_inputs(params))


def _slam_params_file(source: str, use_sim_time: bool) -> str:
    """Launch argument přepíše use_sim_time z yaml (tam může být true)."""
    document = force_key(read_yaml(source), "use_sim_time", bool(use_sim_time))
    toolbox = document.get("slam_toolbox")
    if not isinstance(toolbox, dict):
        toolbox = {}
        document["slam_toolbox"] = toolbox
    params = toolbox.get("ros__parameters")
    if not isinstance(params, dict):
        params = {}
        toolbox["ros__parameters"] = params
    params["use_sim_time"] = bool(use_sim_time)
    return write_yaml(document, "slam_params.ros.yaml")


def _string_list_param(values: list) -> list:
    """Prázdný seznam v ROS parametru nemá typ. Prázdný řetězec uzel zahodí."""
    cleaned = [str(item) for item in values if str(item).strip()]
    return cleaned if cleaned else [""]


def _create(context):
    pkg = FindPackageShare("rmodus_localization")
    use_sim_time = LaunchConfiguration("use_sim_time")
    use_sim = _use_sim(use_sim_time.perform(context))
    robot_config_file = LaunchConfiguration("robot_config_file")
    global_params_file = LaunchConfiguration("global_params_file")
    rf2o_params = LaunchConfiguration("rf2o_params_file")
    slam_params = LaunchConfiguration("slam_params_file")

    robot_path = _resolve(robot_config_file.perform(context))
    global_path = _resolve(global_params_file.perform(context))
    yaml_path = global_path or robot_path
    from_yaml = _flags_from_yaml(yaml_path)
    params = load_merged_ros_parameters(robot_path, global_path)

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
        if not _rf2o_has_ekf_input(params):
            actions.append(
                LogInfo(
                    msg=(
                        "[rmodus_localization] rf2o=true, ale lidar_odom v profilu chybí "
                        "nebo je vypnutý — uzel se nespouští, nemá vstup do EKF."
                    )
                )
            )
        elif _pkg_ok("rf2o_laser_odometry"):
            scan_topic = _lidar_topic(params)
            odom_topic = _lidar_odom_topic(params)
            actions.append(
                LogInfo(
                    msg=(
                        "[rmodus_localization] rf2o: "
                        f"{scan_topic} → {odom_topic}, rám base_footprint, publish_tf false"
                    )
                )
            )
            actions.append(
                Node(
                    package="rf2o_laser_odometry",
                    executable="rf2o_laser_odometry_node",
                    name="rf2o_laser_odometry",
                    parameters=[
                        rf2o_params,
                        {
                            "laser_scan_topic": scan_topic,
                            "odom_topic": odom_topic,
                            "base_frame_id": "base_footprint",
                            "odom_frame_id": "odom",
                            "publish_tf": False,
                            "use_sim_time": use_sim,
                        },
                    ],
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
            slam_file = _slam_params_file(_resolve(slam_params.perform(context)), use_sim)
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
                        "slam_params_file": slam_file,
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
        sensors = obstacle_sensor_params(params)
        if not sensors["has_sensors"]:
            actions.append(
                LogInfo(
                    msg=(
                        "[rmodus_localization] obstacle_cloud: bumpers ani cliff_sensors "
                        "v profilu nejsou — uzel běží bez topiců senzorů."
                    )
                )
            )
        actions.append(
            Node(
                package="rmodus_localization",
                executable="obstacle_cloud",
                name="obstacle_cloud",
                parameters=[
                    {
                        "use_sim_time": use_sim,
                        "base_frame": "base_link",
                        "bumper_topics": _string_list_param(sensors["bumper_topics"]),
                        "bumper_topic_frames": _string_list_param(sensors["bumper_topic_frames"]),
                        "range_topics": _string_list_param(sensors["range_topics"]),
                        "range_topic_frames": _string_list_param(sensors["range_topic_frames"]),
                    }
                ],
                output="screen",
                emulate_tty=True,
            )
        )

    return actions


def generate_launch_description():
    pkg = FindPackageShare("rmodus_localization")
    default_robot = PathJoinSubstitution(
        [FindPackageShare("rmodus_bringup"), "config", "rmodus.yaml"]
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
