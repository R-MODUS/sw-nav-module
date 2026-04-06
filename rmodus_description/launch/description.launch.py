from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os


def generate_launch_description():
    pkg_share = FindPackageShare('rmodus_description')
    robot_xacro = PathJoinSubstitution([pkg_share, 'urdf', 'robot.urdf.xacro'])

    default_config = os.path.join(
        get_package_share_directory('rmodus_description'), 'config', 'robot_config.yaml'
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use simulation clock'
        ),
        DeclareLaunchArgument(
            'config_path',
            default_value=default_config,
            description='Path to robot_config.yaml'
        ),

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{
                'use_sim_time': LaunchConfiguration('use_sim_time'),
                'robot_description': ParameterValue(
                    Command([
                        'xacro ', robot_xacro,
                        ' config_path:=', LaunchConfiguration('config_path'),
                    ]),
                    value_type=str
                ),
            }],
            output='screen',
        ),
    ])
