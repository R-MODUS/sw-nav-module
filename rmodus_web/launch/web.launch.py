from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    default_web_yaml = PathJoinSubstitution(
        [FindPackageShare("rmodus_web"), "config", "web.yaml"]
    )
    robot_yaml = LaunchConfiguration("robot_yaml")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "robot_yaml",
                default_value=default_web_yaml,
                description="YAML s blokem web: (default: share/rmodus_web/config/web.yaml)",
            ),
            Node(
                package="rmodus_web",
                executable="web",
                name="web_node",
                output="screen",
                emulate_tty=True,
                arguments=["--config", robot_yaml],
            ),
        ]
    )
