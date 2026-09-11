import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _load_block(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    if not isinstance(root, dict):
        return {}
    if isinstance(root.get("neato_lidar"), dict):
        return root["neato_lidar"]
    # Allow reuse of robot profile lidar: block (driver-specific keys only)
    params = root.get("/**", {}).get("ros__parameters", {})
    if isinstance(params, dict) and isinstance(params.get("neato_lidar"), dict):
        return params["neato_lidar"]
    if isinstance(params, dict) and isinstance(params.get("lidar"), dict):
        return params["lidar"]
    return {}


def _create(context):
    default = os.path.join(
        get_package_share_directory("neato_lidar"), "config", "neato_lidar.yaml"
    )
    raw = LaunchConfiguration("config_file").perform(context).strip()
    path = os.path.normpath(os.path.expanduser(raw)) if raw else default
    if not os.path.isfile(path):
        path = default

    cfg = _load_block(path)
    if not bool(cfg.get("enabled", True)):
        return []

    params = {
        "frame_id": str(cfg.get("frame_id", "lidar_beam")),
        "topic": str(cfg.get("topic", "/scan")),
        "port": str(cfg.get("port", "/dev/ttyUSB0")),
        "frequency": int(cfg.get("frequency", 10_000)),
        "motor_pin": int(cfg.get("motor_pin", 19)),
        "target_rpm": int(cfg.get("target_rpm", 300)),
        "range_max": float(cfg.get("range_max", 5.0)),
        "range_min": float(cfg.get("range_min", 0.05)),
        "angle_min": float(cfg.get("angle_min", 0.0)),
        "angle_max": float(cfg.get("angle_max", 6.283185307179586)),
    }
    return [
        Node(
            package="neato_lidar",
            executable="neato_lidar",
            name="neato_lidar",
            parameters=[params],
            output="screen",
        )
    ]


def generate_launch_description():
    default = os.path.join(
        get_package_share_directory("neato_lidar"), "config", "neato_lidar.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value=default,
                description="YAML with neato_lidar: (or /**/ros__parameters/lidar)",
            ),
            OpaqueFunction(function=_create),
        ]
    )
