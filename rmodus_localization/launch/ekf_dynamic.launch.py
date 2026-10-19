"""EKF z profilu. Jediný zdroj parametrů filtru — config/ekf_params.yaml neexistuje."""

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

from rmodus_localization.ekf_config import build_ekf_params, iter_ekf_inputs
from rmodus_localization.profile_params import load_merged_ros_parameters


def _resolve(path) -> str:
    if path is None:
        return ""
    text = str(path).strip()
    if not text:
        return ""
    return os.path.normpath(os.path.expanduser(text))


def _use_sim(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def _build_ekf(context):
    robot_config_file = _resolve(LaunchConfiguration("robot_config_file").perform(context))
    global_params_file = _resolve(LaunchConfiguration("global_params_file").perform(context))
    use_sim_time = _use_sim(LaunchConfiguration("use_sim_time").perform(context))

    if not os.path.isfile(robot_config_file):
        raise RuntimeError(f"robot_config file not found: {robot_config_file}")

    params = load_merged_ros_parameters(robot_config_file, global_params_file)
    ekf_params = build_ekf_params(params, use_sim_time)
    fused = [f"{name}={topic}" for name, _kind, topic in iter_ekf_inputs(params)]
    return [
        LogInfo(
            msg="[rmodus_localization] EKF fúze: " + (", ".join(fused) if fused else "(žádný vstup)")
        ),
        Node(
            package="robot_localization",
            executable="ekf_node",
            name="ekf_filter_node",
            parameters=[ekf_params],
            output="screen",
            emulate_tty=True,
        ),
    ]


def generate_launch_description():
    default_robot = PathJoinSubstitution(
        [FindPackageShare("rmodus_bringup"), "config", "rmodus.yaml"]
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument(
                "robot_config_file",
                default_value=default_robot,
                description="Profil robota. Z bringupu zkompilovaný YAML.",
            ),
            DeclareLaunchArgument(
                "global_params_file",
                default_value="",
                description="Volitelný druhý YAML. Prázdné, dokud ho bringup nepředá.",
            ),
            OpaqueFunction(function=_build_ekf),
        ]
    )
