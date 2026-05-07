from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration, Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue
from ament_index_python.packages import get_package_share_directory

import os
import tempfile
import yaml


def _deep_merge(base_obj, override_obj):
    if isinstance(base_obj, dict) and isinstance(override_obj, dict):
        merged = dict(base_obj)
        for key, value in override_obj.items():
            if key in merged:
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    return override_obj


def _create_robot_state_publisher(context):
    use_sim_time = LaunchConfiguration('use_sim_time')
    robot_config_file = LaunchConfiguration('robot_config_file').perform(context)
    base_config_path = LaunchConfiguration('base_config_path').perform(context)
    override_config_path = LaunchConfiguration('override_config_path').perform(context)

    final_config_path = robot_config_file or base_config_path

    if override_config_path and os.path.exists(override_config_path):
        with open(final_config_path, 'r', encoding='utf-8') as f:
            base_cfg = yaml.safe_load(f) or {}
        with open(override_config_path, 'r', encoding='utf-8') as f:
            override_cfg = yaml.safe_load(f) or {}

        merged_cfg = _deep_merge(base_cfg, override_cfg)
        tmp_cfg = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml')
        yaml.safe_dump(merged_cfg, tmp_cfg)
        tmp_cfg.close()
        final_config_path = tmp_cfg.name

    robot_xacro = os.path.join(
        get_package_share_directory('rmodus_description'),
        'urdf',
        'robot.urdf.xacro',
    )

    return [
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{
                'use_sim_time': use_sim_time,
                'robot_description': ParameterValue(
                    Command([
                        'xacro ', robot_xacro,
                        ' config_path:=', final_config_path,
                    ]),
                    value_type=str,
                ),
            }],
            output='screen',
        )
    ]


def generate_launch_description():
    default_robot_config_file = os.path.join(
        get_package_share_directory('rmodus_description'), 'config', 'default_robot_config.yaml'
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='false',
            description='Use simulation clock'
        ),
        DeclareLaunchArgument(
            'robot_config_file',
            default_value='',
            description='Path to robot YAML config file (preferred argument)'
        ),
        DeclareLaunchArgument(
            'base_config_path',
            default_value=default_robot_config_file,
            description='Path to robot YAML config file (legacy fallback)'
        ),
        DeclareLaunchArgument(
            'override_config_path',
            default_value='',
            description='Path to optional global override config file'
        ),
        OpaqueFunction(function=_create_robot_state_publisher),
    ])
