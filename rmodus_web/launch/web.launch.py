from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="rmodus_web",
                executable="websocket",
                name="websocket_node",
                output="screen",
                emulate_tty=True,
            ),
        ]
    )
