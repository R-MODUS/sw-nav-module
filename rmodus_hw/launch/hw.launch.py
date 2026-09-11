from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

import os
import yaml


def _load_fan(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    if not isinstance(root, dict):
        return {}

    def _unwrap(block):
        if not isinstance(block, dict):
            return {}
        if isinstance(block.get("ros__parameters"), dict):
            return block["ros__parameters"]
        return block

    if "fan" in root:
        return _unwrap(root["fan"])
    params = root.get("/**", {}).get("ros__parameters", {})
    if isinstance(params, dict) and "fan" in params:
        return _unwrap(params["fan"])
    return {}


def _create_hw_nodes(context):
    pkg_share = get_package_share_directory("rmodus_hw")
    params_base_path = os.path.join(pkg_share, "config", "base_params.yaml")
    raw_user = LaunchConfiguration("user_params_file").perform(context)
    if raw_user and str(raw_user).strip():
        params_user_path = os.path.normpath(os.path.expanduser(str(raw_user).strip()))
    else:
        params_user_path = params_base_path

    params = [params_base_path]
    if params_user_path and os.path.isfile(params_user_path):
        if os.path.normpath(params_user_path) != os.path.normpath(params_base_path):
            params.append(params_user_path)

    fan_cfg = _load_fan(params_user_path) or _load_fan(params_base_path)
    fan_params = list(params)
    fan_override = {}
    for key in ("fan_pin", "pin", "frequency", "min_to_run", "user_power"):
        if key in fan_cfg:
            fan_override["fan_pin" if key == "pin" else key] = fan_cfg[key]
    if fan_override:
        fan_params.append(fan_override)

    nodes = [
        Node(package="rmodus_hw", executable="get_wifi", name="wifi_service", parameters=params),
        Node(package="rmodus_hw", executable="system_monitor", name="sys_mon", parameters=params),
    ]
    if bool(fan_cfg.get("enabled", True)):
        nodes.append(
            Node(package="rmodus_hw", executable="fan_control", name="fan", parameters=fan_params)
        )
    return nodes


def generate_launch_description():
    pkg_share = get_package_share_directory("rmodus_hw")
    params_base = os.path.join(pkg_share, "config", "base_params.yaml")

    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "user_params_file",
                default_value=params_base,
                description="Path to user/robot YAML (fan block optional)",
            ),
            OpaqueFunction(function=_create_hw_nodes),
        ]
    )
