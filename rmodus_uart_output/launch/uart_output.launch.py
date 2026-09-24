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
    if isinstance(root.get("uart_output"), dict):
        return root["uart_output"]
    params = root.get("/**", {}).get("ros__parameters", {})
    if isinstance(params, dict) and isinstance(params.get("uart_output"), dict):
        return params["uart_output"]
    return {}


def _create(context):
    default = os.path.join(
        get_package_share_directory("rmodus_uart_output"), "config", "uart_output.yaml"
    )
    raw = LaunchConfiguration("config_file").perform(context).strip()
    path = os.path.normpath(os.path.expanduser(raw)) if raw else default
    if not os.path.isfile(path):
        path = default

    cfg = _load_block(path)
    if not bool(cfg.get("enabled", True)):
        return []

    params = {
        "port": str(cfg.get("port", "/dev/ttyUSB0")),
        "baudrate": int(cfg.get("baudrate", 115200)),
        "cmd_vel_topic": str(cfg.get("cmd_vel_topic", "/cmd_vel")),
        "cmd_timeout_sec": float(cfg.get("cmd_timeout_sec", 0.5)),
    }
    return [
        Node(
            package="rmodus_uart_output",
            executable="uart_output",
            name="uart_output",
            parameters=[params],
            output="screen",
        )
    ]


def generate_launch_description():
    default = os.path.join(
        get_package_share_directory("rmodus_uart_output"), "config", "uart_output.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "config_file",
                default_value=default,
                description="YAML with uart_output: block (or /**/ros__parameters/uart_output)",
            ),
            OpaqueFunction(function=_create),
        ]
    )
