from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import PathJoinSubstitution, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory

import os
import yaml


def _build_sensor_overrides(user_params_path):
    if not user_params_path or not os.path.exists(user_params_path):
        return {}, {}, {}, {}, {}, {}

    with open(user_params_path, 'r', encoding='utf-8') as f:
        root = yaml.safe_load(f) or {}

    ros_params = root.get('/**', {}).get('ros__parameters', {})
    lidar_cfg = ros_params.get('lidar', {})
    flow_cfg = ros_params.get('flow_sensor', {})
    cliff_cfg = ros_params.get('cliff_sensors', [])
    motors_cfg = ros_params.get('motors_node', {})
    display_cfg = ros_params.get('display', {})
    fan_cfg = ros_params.get('fan', {})

    lidar_override = {}
    for key in (
        'frame_id', 'port', 'frequency', 'motor_pin', 'target_rpm',
        'range_max', 'range_min', 'angle_min', 'angle_max',
    ):
        if key in lidar_cfg:
            lidar_override[key] = lidar_cfg[key]

    flow_override = {}
    for key in ('spi_port', 'spi_cs', 'deadzone', 'timer_period', 'z_height', 'fov_deg', 'res_pix'):
        if key in flow_cfg:
            flow_override[key] = flow_cfg[key]
    if 'frame_id' in flow_cfg:
        flow_override['frame_id'] = flow_cfg['frame_id']

    cliff_override = {}
    if isinstance(cliff_cfg, list) and cliff_cfg:
        first = cliff_cfg[0] if isinstance(cliff_cfg[0], dict) else {}
        for key in ('v_points', 'd_points'):
            if key in first:
                cliff_override[key] = first[key]
        if 'range_min' in first:
            cliff_override['range_msg_min'] = first['range_min']
        if 'range_max' in first:
            cliff_override['range_msg_max'] = first['range_max']
        topics = []
        frames = []
        for item in cliff_cfg:
            if not isinstance(item, dict) or not item.get('enabled', True):
                continue
            t = str(item.get('topic', '')).strip()
            if t:
                topics.append(t)
            name = str(item.get('name', ''))
            frame_id = item.get('frame_id')
            if frame_id:
                frames.append(str(frame_id))
            elif name:
                frames.append(f'cliff_sensor_{name}_beam')
        if len(topics) == 4 and len(frames) == 4:
            cliff_override['cliff_topics'] = topics
            cliff_override['cliff_frame_ids'] = frames

    motors_override = {}
    for key in ('port', 'max_speed'):
        if key in motors_cfg:
            motors_override[key] = motors_cfg[key]

    display_override = {}
    for key in ('width', 'height', 'orientation', 'brightness'):
        if key in display_cfg:
            display_override[key] = display_cfg[key]

    fan_override = {}
    for key in ('fan_pin', 'frequency', 'min_to_run', 'user_power'):
        if key in fan_cfg:
            fan_override[key] = fan_cfg[key]

    return lidar_override, flow_override, cliff_override, motors_override, display_override, fan_override


def _create_hw_nodes(context):
    pkg_name = 'rmodus_hw'
    pkg_share = get_package_share_directory(pkg_name)

    params_base_path = os.path.join(pkg_share, 'config', 'base_params.yaml')
    params_xsens_path = os.path.join(pkg_share, 'config', 'xsens_mti_node.yaml')
    raw_user = LaunchConfiguration('user_params_file').perform(context)
    if raw_user and str(raw_user).strip():
        params_user_path = os.path.normpath(os.path.expanduser(str(raw_user).strip()))
    else:
        params_user_path = raw_user

    params = [params_base_path, params_user_path]
    lidar_override, flow_override, cliff_override, motors_override, display_override, fan_override = _build_sensor_overrides(params_user_path)

    motors_params = list(params)
    if motors_override:
        motors_params.append(motors_override)

    display_params = list(params)
    if display_override:
        display_params.append(display_override)

    fan_params = list(params)
    if fan_override:
        fan_params.append(fan_override)

    lidar_params = list(params)
    if lidar_override:
        lidar_params.append(lidar_override)

    flow_params = list(params)
    if flow_override:
        flow_params.append(flow_override)

    cliff_params = list(params)
    if cliff_override:
        cliff_params.append(cliff_override)

    return [
        Node(package=pkg_name, executable='get_wifi', name='wifi_service', parameters=params),
        Node(package=pkg_name, executable='system_monitor', name='sys_mon', parameters=params),
        Node(package=pkg_name, executable='fan_control', name='fan', parameters=fan_params),
        Node(package=pkg_name, executable='display', name='display', parameters=display_params),
        Node(package=pkg_name, executable='motors', name='motors_node', parameters=motors_params),
        Node(package=pkg_name, executable='lidar', name='lidar_node', parameters=lidar_params),
        Node(package=pkg_name, executable='cliff_sensors', name='cliff_sensors_node', parameters=cliff_params),
        Node(package=pkg_name, executable='bumper_sensors', name='bumper_sensors_node', parameters=params),
        Node(package=pkg_name, executable='flow_sensor', name='optical_flow_node', parameters=flow_params),
        Node(
            package='xsens_mti_ros2_driver',
            executable='xsens_mti_node',
            name='xsens_driver',
            parameters=[params_xsens_path],
            remappings=[('/temperature', '/xsens/temperature')],
        ),
    ]

def generate_launch_description():
    pkg_name = 'rmodus_hw'
    config_dir = PathJoinSubstitution([FindPackageShare(pkg_name), 'config'])

    params_base = PathJoinSubstitution([config_dir, 'base_params.yaml'])

    params_user_arg = DeclareLaunchArgument(
        'user_params_file',
        default_value=params_base,
        description='Path to user parameter file'
    )

    return LaunchDescription([
        params_user_arg,
        OpaqueFunction(function=_create_hw_nodes),
    ])