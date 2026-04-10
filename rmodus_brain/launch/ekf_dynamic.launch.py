import os
import yaml

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


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


def _odom_config():
    return [
        True, True, False,
        False, False, True,
        True, True, False,
        False, False, True,
        False, False, False,
    ]


def _imu_config():
    return [
        False, False, False,
        True, True, True,
        False, False, False,
        True, True, True,
        False, False, False,
    ]


def _twist_config():
    return [
        False, False, False,
        False, False, False,
        True, True, False,
        False, False, False,
        False, False, False,
    ]


def _append_sensor(ekf_params, counters, sensor_cfg):
    if not sensor_cfg.get('enabled', False):
        return

    sensor_type = sensor_cfg.get('type')
    topic = sensor_cfg.get('topic')

    if sensor_type not in counters or not topic:
        return

    idx = counters[sensor_type]
    prefix = f'{sensor_type}{idx}'

    ekf_params[prefix] = topic

    if sensor_type == 'odom':
        ekf_params[f'{prefix}_config'] = _odom_config()
        ekf_params[f'{prefix}_differential'] = False
        ekf_params[f'{prefix}_queue_size'] = 10
    elif sensor_type == 'imu':
        ekf_params[f'{prefix}_config'] = _imu_config()
        ekf_params[f'{prefix}_differential'] = False
        ekf_params[f'{prefix}_queue_size'] = 10
        ekf_params[f'{prefix}_remove_gravitational_acceleration'] = True
    elif sensor_type == 'twist':
        ekf_params[f'{prefix}_config'] = _twist_config()
        ekf_params[f'{prefix}_relative'] = False

    counters[sensor_type] += 1


def _build_ekf(context):
    robot_config_file = LaunchConfiguration('robot_config_file').perform(context)
    global_params_file = LaunchConfiguration('global_params_file').perform(context)
    use_sim_time_raw = LaunchConfiguration('use_sim_time').perform(context)
    use_sim_time = use_sim_time_raw.lower() in ('1', 'true', 'yes', 'on')

    if not os.path.exists(robot_config_file):
        raise RuntimeError(f'robot_config file not found: {robot_config_file}')

    with open(robot_config_file, 'r', encoding='utf-8') as f:
        root = yaml.safe_load(f) or {}

    if global_params_file and os.path.exists(global_params_file):
        with open(global_params_file, 'r', encoding='utf-8') as f:
            global_root = yaml.safe_load(f) or {}
        root = _deep_merge(root, global_root)

    params = root.get('/**', {}).get('ros__parameters', {})

    ekf_params = {
        'use_sim_time': use_sim_time,
        'frequency': 30.0,
        'two_d_mode': True,
        'publish_tf': True,
        'map_frame': 'map',
        'odom_frame': 'odom',
        'base_link_frame': 'base_footprint',
        'world_frame': 'odom',
    }

    counters = {
        'odom': 0,
        'imu': 0,
        'twist': 0,
    }

    wheel_odom_cfg = params.get('wheel_odom', {
        'enabled': True,
        'type': 'odom',
        'topic': '/odom',
    })
    lidar_odom_cfg = params.get('lidar_odom', {
        'enabled': False,
        'type': 'odom',
        'topic': '/odom_lidar',
    })
    imu_cfg = params.get('imu', {})
    flow_cfg = params.get('flow_sensor', {})

    if 'type' not in imu_cfg:
        imu_cfg = {
            **imu_cfg,
            'type': 'imu',
        }
    if 'enabled' not in imu_cfg:
        imu_cfg = {
            **imu_cfg,
            'enabled': True,
        }

    if 'type' not in flow_cfg:
        flow_cfg = {
            **flow_cfg,
            'type': 'twist',
        }
    if 'enabled' not in flow_cfg:
        flow_cfg = {
            **flow_cfg,
            'enabled': True,
        }
    if 'topic' not in flow_cfg:
        flow_cfg = {
            **flow_cfg,
            'topic': '/visual_flow/data',
        }

    for sensor_cfg in (wheel_odom_cfg, lidar_odom_cfg, imu_cfg, flow_cfg):
        _append_sensor(ekf_params, counters, sensor_cfg)

    return [
        Node(
            package='robot_localization',
            executable='ekf_node',
            name='ekf_filter_node',
            parameters=[ekf_params],
            output='screen',
            emulate_tty=True,
        )
    ]


def generate_launch_description():
    default_robot_config = os.path.join(
        get_package_share_directory('rmodus_description'),
        'config',
        'robot_config.yaml',
    )

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument(
            'robot_config_file',
            default_value=default_robot_config,
            description='Path to robot config file',
        ),
        DeclareLaunchArgument(
            'global_params_file',
            default_value='',
            description='Path to optional global params file',
        ),
        OpaqueFunction(function=_build_ekf),
    ])
