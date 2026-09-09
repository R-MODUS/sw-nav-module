"""Publish host TF: base_footprint → base_link from profile YAML."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os


def _resolve(path: str) -> str:
    if not path:
        return ""
    return os.path.normpath(os.path.expanduser(str(path).strip()))


def _create(context):
    use_sim_time = LaunchConfiguration("use_sim_time")
    config = _resolve(LaunchConfiguration("robot_config_file").perform(context))
    if not config or not os.path.isfile(config):
        config = os.path.join(
            get_package_share_directory("rmodus_chassis"), "config", "chassis.yaml"
        )

    xacro = os.path.join(
        get_package_share_directory("rmodus_chassis"), "urdf", "chassis.urdf.xacro"
    )

    return [
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            name="chassis_state_publisher",
            parameters=[
                {
                    "use_sim_time": use_sim_time,
                    "robot_description": ParameterValue(
                        Command(["xacro ", xacro, " config_path:=", config]),
                        value_type=str,
                    ),
                }
            ],
            output="screen",
        )
    ]


def generate_launch_description():
    default_cfg = os.path.join(
        get_package_share_directory("rmodus_chassis"), "config", "chassis.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument(
                "robot_config_file",
                default_value=default_cfg,
                description="Profile YAML with /**/ros__parameters/base_link",
            ),
            OpaqueFunction(function=_create),
        ]
    )
