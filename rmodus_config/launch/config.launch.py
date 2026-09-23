from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    configs_root = LaunchConfiguration("configs_root")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "configs_root",
                default_value="",
                description="Absolutni …/configs (z cesty aktivniho profilu). Prazdne = ~/rmodus/configs.",
            ),
            Node(
                package="rmodus_config",
                executable="config_manager",
                name="rmodus_config_manager",
                output="screen",
                emulate_tty=True,
                parameters=[{"configs_root": configs_root}],
            ),
        ]
    )
