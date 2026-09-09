"""Spuštění na robotovi (edge): HW box + volitelné moduly (+ volitelně TF)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare("rmodus_bringup")
    hw_launch = PathJoinSubstitution([FindPackageShare("rmodus_hw"), "launch", "hw.launch.py"])
    uart_launch = PathJoinSubstitution(
        [FindPackageShare("rmodus_uart_output"), "launch", "uart_output.launch.py"]
    )
    estop_launch = PathJoinSubstitution(
        [FindPackageShare("rmodus_estop"), "launch", "estop.launch.py"]
    )
    bumper_launch = PathJoinSubstitution(
        [FindPackageShare("rmodus_bumper"), "launch", "bumper.launch.py"]
    )
    cliff_launch = PathJoinSubstitution(
        [FindPackageShare("rmodus_cliff_sensor"), "launch", "cliff_sensor.launch.py"]
    )
    flow_launch = PathJoinSubstitution(
        [FindPackageShare("rmodus_flow_sensor"), "launch", "flow_sensor.launch.py"]
    )
    display_launch = PathJoinSubstitution(
        [FindPackageShare("rmodus_display"), "launch", "display.launch.py"]
    )
    description_launch = PathJoinSubstitution(
        [FindPackageShare("rmodus_description"), "launch", "description.launch.py"]
    )
    web_launch = PathJoinSubstitution([FindPackageShare("rmodus_web"), "launch", "web.launch.py"])

    robot_yaml = LaunchConfiguration("robot_yaml")
    launch_web = LaunchConfiguration("launch_web")
    launch_description = LaunchConfiguration("launch_description")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "robot_yaml",
                default_value=PathJoinSubstitution([pkg_share, "config", "robot.yaml"]),
            ),
            DeclareLaunchArgument("launch_web", default_value="false"),
            DeclareLaunchArgument("launch_description", default_value="false"),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(hw_launch),
                launch_arguments={"user_params_file": robot_yaml}.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(uart_launch),
                launch_arguments={"config_file": robot_yaml}.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(estop_launch),
                launch_arguments={"config_file": robot_yaml}.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(bumper_launch),
                launch_arguments={"config_file": robot_yaml}.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(cliff_launch),
                launch_arguments={"config_file": robot_yaml}.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(flow_launch),
                launch_arguments={"config_file": robot_yaml}.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(display_launch),
                launch_arguments={"config_file": robot_yaml}.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(description_launch),
                launch_arguments={
                    "use_sim_time": "false",
                    "robot_config_file": robot_yaml,
                    "override_config_path": robot_yaml,
                }.items(),
                condition=IfCondition(launch_description),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(web_launch),
                launch_arguments={"robot_yaml": robot_yaml}.items(),
                condition=IfCondition(launch_web),
            ),
        ]
    )
