import os
import re

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

_NODE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _expand(block: dict) -> list:
    """One flat driver block, or neato_lidar.items / a list of them."""
    if not isinstance(block, dict) or block.get("enabled", True) is False:
        return []
    items = block.get("items")
    if isinstance(items, list):
        return [
            item
            for item in items
            if isinstance(item, dict) and item.get("enabled", True) is not False
        ]
    return [block]


def _load_configs(path: str) -> list:
    """Driver blocks to spawn.

    Prefers neato_lidar (flat or items). A flat lidar: block is the legacy
    fallback. lidar.items is a sensor list for the web/TF, not this driver.
    Missing block in an existing file → no node (do not invent /dev/ttyUSB0).
    Missing file → one node with parameter defaults (standalone launch).
    """
    if not path or not os.path.isfile(path):
        return [{}]
    with open(path, "r", encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    if not isinstance(root, dict):
        return []
    if isinstance(root.get("neato_lidar"), dict):
        return _expand(root["neato_lidar"])
    params = root.get("/**", {}).get("ros__parameters", {})
    if not isinstance(params, dict):
        return []
    if isinstance(params.get("neato_lidar"), dict):
        return _expand(params["neato_lidar"])
    lidar = params.get("lidar")
    if isinstance(lidar, dict) and not isinstance(lidar.get("items"), list):
        return _expand(lidar)
    return []


def _node_params(cfg: dict) -> dict:
    return {
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


def _node_name(cfg: dict, index: int, used: set) -> str:
    raw = str(cfg.get("name") or "").strip()
    base = raw if _NODE_NAME.match(raw) else ("neato_lidar" if index == 0 else f"neato_lidar_{index + 1}")
    name = base
    suffix = 2
    while name in used:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def _create(context):
    default = os.path.join(
        get_package_share_directory("neato_lidar"), "config", "neato_lidar.yaml"
    )
    raw = LaunchConfiguration("config_file").perform(context).strip()
    path = os.path.normpath(os.path.expanduser(raw)) if raw else default
    if not os.path.isfile(path):
        path = default

    used_names = set()
    nodes = []
    configs = _load_configs(path)
    if not configs:
        return [
            LogInfo(
                msg=(
                    f"[neato_lidar] v {path} neni blok neato_lidar "
                    "(ani plochý lidar bez items) — uzel nespoustim"
                )
            )
        ]
    for index, cfg in enumerate(configs):
        nodes.append(
            Node(
                package="neato_lidar",
                executable="neato_lidar",
                name=_node_name(cfg, index, used_names),
                parameters=[_node_params(cfg)],
                output="screen",
            )
        )
    return nodes


def generate_launch_description():
    default = os.path.join(
        get_package_share_directory("neato_lidar"), "config", "neato_lidar.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value=default,
                description="YAML with neato_lidar: (flat or items) or a flat lidar: block",
            ),
            OpaqueFunction(function=_create),
        ]
    )
