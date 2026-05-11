"""Spuštění na robotovi (edge): pouze HW ovladače + robot_state_publisher / TF z URDF.

Autonomii, RViz a volitelně web spusť na PC se stejným ROS_DOMAIN_ID a fungujícím
síťovým ROS 2 discovery (viz dokumentace k RMW, typicky Cyclone DDS)."""

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

    user_params_file = LaunchConfiguration('user_params_file')
    robot_config_file = LaunchConfiguration('robot_config_file')
    launch_web = LaunchConfiguration('launch_web')

    return LaunchDescription([
        DeclareLaunchArgument(
            'user_params_file',
            default_value=PathJoinSubstitution([pkg_share, 'config', 'user_params.yaml']),
            description='Globální YAML s přepsáními (stejný soubor jako na PC)',
        ),
        DeclareLaunchArgument(
            'robot_config_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('rmodus_description'), 'config', 'default_robot_config.yaml',
            ]),
            description='Konfigurace robota / URDF (stejná jako na PC)',
        ),
        DeclareLaunchArgument(
            'launch_web',
            default_value='false',
            description='true = spustit websocket UI na robotovi (jinak jen na PC)',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(hw_launch),
            launch_arguments={'user_params_file': user_params_file}.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(description_launch),
            launch_arguments={
                'use_sim_time': 'false',
                'robot_config_file': robot_config_file,
                'override_config_path': user_params_file,
            }.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(web_launch),
            condition=IfCondition(launch_web),
        ),
    ])
