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
    if isinstance(root.get("flow_sensor"), dict):
        return root["flow_sensor"]
    params = root.get("/**", {}).get("ros__parameters", {})
    if isinstance(params, dict) and isinstance(params.get("flow_sensor"), dict):
        return params["flow_sensor"]
    return {}


def _create(context):
    default = os.path.join(
        get_package_share_directory("rmodus_flow_sensor"), "config", "flow.yaml"
    )
    raw = LaunchConfiguration("config_file").perform(context).strip()
    path = os.path.normpath(os.path.expanduser(raw)) if raw else default
    if not os.path.isfile(path):
        path = default

    cfg = _load_block(path)
    if not bool(cfg.get("enabled", True)):
        return []

    frame_id = str(cfg.get("frame_id", "flow_front_link"))
    parent = str(cfg.get("mount_parent_frame", "base_link"))
    offset = cfg.get("mount_offset", [0.0, 0.0, 0.0])
    rpy = cfg.get("mount_rpy", [0.0, 0.0, 0.0])

    params = {
        "spi_port": int(cfg.get("spi_port", 0)),
        "spi_cs": int(cfg.get("spi_cs", 0)),
        "deadzone": int(cfg.get("deadzone", 3)),
        "timer_period": float(cfg.get("timer_period", 0.05)),
        "topic": str(cfg.get("topic", "/visual_flow/data")),
        "frame_id": frame_id,
        "z_height": float(cfg.get("z_height", 0.025)),
        "fov_deg": float(cfg.get("fov_deg", 42.0)),
        "res_pix": int(cfg.get("res_pix", 35)),
    }

    return [
        Node(
            package="rmodus_flow_sensor",
            executable="flow_sensor",
            name="optical_flow_node",
            parameters=[params],
            output="screen",
        ),
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name="flow_tf",
            arguments=[
                "--x", str(float(offset[0])),
                "--y", str(float(offset[1])),
                "--z", str(float(offset[2])),
                "--roll", str(float(rpy[0])),
                "--pitch", str(float(rpy[1])),
                "--yaw", str(float(rpy[2])),
                "--frame-id", parent,
                "--child-frame-id", frame_id,
            ],
        ),
    ]


def generate_launch_description():
    default = os.path.join(
        get_package_share_directory("rmodus_flow_sensor"), "config", "flow.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("config_file", default_value=default),
            OpaqueFunction(function=_create),
        ]
    )
