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
    if isinstance(root.get("display"), dict):
        return root["display"]
    params = root.get("/**", {}).get("ros__parameters", {})
    if isinstance(params, dict) and isinstance(params.get("display"), dict):
        return params["display"]
    return {}


def _create(context):
    default = os.path.join(
        get_package_share_directory("rmodus_display"), "config", "display.yaml"
    )
    raw = LaunchConfiguration("config_file").perform(context).strip()
    path = os.path.normpath(os.path.expanduser(raw)) if raw else default
    if not os.path.isfile(path):
        path = default

    cfg = _load_block(path)
    if not bool(cfg.get("enabled", True)):
        return []

    params = {
        "address": str(cfg.get("address", "0x3C")),
        "width": int(cfg.get("width", 128)),
        "height": int(cfg.get("height", 32)),
        "orientation": int(cfg.get("orientation", 0)),
        "brightness": int(cfg.get("brightness", 5)),
    }

    nodes = [
        Node(
            package="rmodus_display",
            executable="display",
            name="display",
            parameters=[params],
            output="screen",
        )
    ]

    parent = str(cfg.get("mount_parent_frame") or "").strip()
    frame_id = str(cfg.get("frame_id") or "").strip()
    if parent and frame_id:
        offset = cfg.get("mount_offset", [0.0, 0.0, 0.0])
        rpy = cfg.get("mount_rpy", [0.0, 0.0, 0.0])
        nodes.append(
            Node(
                package="tf2_ros",
                executable="static_transform_publisher",
                name="display_tf",
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
            )
        )
    return nodes


def generate_launch_description():
    default = os.path.join(
        get_package_share_directory("rmodus_display"), "config", "display.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("config_file", default_value=default),
            OpaqueFunction(function=_create),
        ]
    )
