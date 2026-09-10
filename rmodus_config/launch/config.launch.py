from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="rmodus_config",
                executable="config_manager",
                name="rmodus_config_manager",
                output="screen",
                emulate_tty=True,
            ),
        ]
    )
