"""Spuštění na robotovi (edge): HW (+ volitelně TF z URDF na místě).

TF/URDF často nechávají běžet na výkonnějším PC (`pc_dev.launch.py`, launch_description:=true),
aby na Pi nebyl xacro / robot_state_publisher. Autonomii a RViz spouštěj na PC se stejným
ROS_DOMAIN_ID a fungujícím ROS 2 discovery přes LAN."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare('rmodus_bringup')
    hw_launch = PathJoinSubstitution([FindPackageShare('rmodus_hw'), 'launch', 'hw.launch.py'])
    description_launch = PathJoinSubstitution([FindPackageShare('rmodus_description'), 'launch', 'description.launch.py'])
    web_launch = PathJoinSubstitution([FindPackageShare('rmodus_web'), 'launch', 'web.launch.py'])

    robot_yaml = LaunchConfiguration('robot_yaml')
    launch_web = LaunchConfiguration('launch_web')
    launch_description = LaunchConfiguration('launch_description')

    return LaunchDescription([
        DeclareLaunchArgument(
            'robot_yaml',
            default_value=PathJoinSubstitution([pkg_share, 'config', 'robot.yaml']),
            description='Jeden konfig pro HW + URDF merge; stejný soubor na PC (`pc_dev.launch.py`).',
        ),
        DeclareLaunchArgument(
            'launch_web',
            default_value='false',
            description='true = spustit websocket UI na robotovi (jinak jen na PC)',
        ),
        DeclareLaunchArgument(
            'launch_description',
            default_value='false',
            description='true = robot_state_publisher na Pi; nechte false, když TF běží na PC',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(hw_launch),
            launch_arguments={'user_params_file': robot_yaml}.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(description_launch),
            launch_arguments={
                'use_sim_time': 'false',
                'robot_config_file': robot_yaml,
                'override_config_path': robot_yaml,
            }.items(),
            condition=IfCondition(launch_description),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(web_launch),
            condition=IfCondition(launch_web),
        ),
    ])
