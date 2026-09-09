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
    if isinstance(root.get("rmodus_estop"), dict):
        return root["rmodus_estop"]
    params = root.get("/**", {}).get("ros__parameters", {})
    if isinstance(params, dict) and isinstance(params.get("rmodus_estop"), dict):
        return params["rmodus_estop"]
    return {}


def _create(context):
    default = os.path.join(
        get_package_share_directory("rmodus_estop"), "config", "estop.yaml"
    )
    raw = LaunchConfiguration("config_file").perform(context).strip()
    path = os.path.normpath(os.path.expanduser(raw)) if raw else default
    if not os.path.isfile(path):
        path = default

    cfg = _load_block(path)
    if not bool(cfg.get("enabled", True)):
        return []

    gpio = cfg.get("gpio_button") if isinstance(cfg.get("gpio_button"), dict) else {}
    platform = cfg.get("platform") if isinstance(cfg.get("platform"), dict) else {}

    params = {
        "enabled": True,
        "publish_rate_hz": float(cfg.get("publish_rate_hz", 50.0)),
        "cmd_vel_input_topic": str(cfg.get("cmd_vel_input_topic", "/cmd_vel")),
        "cmd_vel_output_topic": str(cfg.get("cmd_vel_output_topic", "/cmd_vel_safe")),
        "state_topic": str(cfg.get("state_topic", "/rmodus/e_stop")),
        "request_topic": str(cfg.get("request_topic", "/rmodus/e_stop/request")),
        "reset_topic": str(cfg.get("reset_topic", "/rmodus/e_stop/reset")),
        "require_clear_to_reset": bool(cfg.get("require_clear_to_reset", False)),
        "gpio_button.enabled": bool(gpio.get("enabled", False)),
        "gpio_button.pin": int(gpio.get("pin", 16)),
        "gpio_button.active_high": bool(gpio.get("active_high", False)),
        "gpio_button.pull_up": bool(gpio.get("pull_up", True)),
        "platform.enabled": bool(platform.get("enabled", False)),
        "platform.state_topic": str(platform.get("state_topic", "/hardware/e_stop")),
        "platform.trigger_service": str(
            platform.get("trigger_service", "/hardware/e_stop_trigger")
        ),
        "platform.reset_service": str(
            platform.get("reset_service", "/hardware/e_stop_reset")
        ),
        "platform.mode": str(platform.get("mode", "mirror_out")),
    }
    return [
        Node(
            package="rmodus_estop",
            executable="estop",
            name="rmodus_estop",
            parameters=[params],
            output="screen",
        )
    ]


def generate_launch_description():
    default = os.path.join(
        get_package_share_directory("rmodus_estop"), "config", "estop.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("config_file", default_value=default),
            OpaqueFunction(function=_create),
        ]
    )
