"""Start one micro-ROS agent per serial device listed in the robot profile."""

import os
import re

import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from rmodus_bringup.package_gates import package_available, skip_log


def _node_name(label: str, used: set) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", label).strip("_") or "device"
    if not base[0].isalpha():
        base = f"dev_{base}"
    candidate = f"micro_ros_agent_{base}"
    n = 2
    while candidate in used:
        candidate = f"micro_ros_agent_{base}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _as_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _entry(raw: dict, index: int) -> dict | None:
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or f"device_{index}").strip() or f"device_{index}"
    return {
        "name": name,
        "enabled": _as_bool(raw.get("enabled", True)),
        "transport": str(raw.get("transport") or "serial").strip(),
        "device": str(raw.get("device") or "").strip(),
        "baudrate": int(raw.get("baudrate") or 115200),
    }


def _load_items(path: str) -> tuple[bool, list]:
    if not path or not os.path.isfile(path):
        return True, []
    with open(path, "r", encoding="utf-8") as handle:
        root = yaml.safe_load(handle) or {}
    block = root.get("microros", {}) if isinstance(root, dict) else {}
    if not isinstance(block, dict):
        return True, []
    enabled = _as_bool(block.get("enabled", True))
    raw_items = block.get("items")
    items = []
    if isinstance(raw_items, list):
        for index, raw in enumerate(raw_items):
            entry = _entry(raw, index)
            if entry is not None:
                items.append(entry)
        return enabled, items
    # Starý plochý zápis: jedno device na celém bloku.
    if block.get("device"):
        flat = _entry(block, 0)
        if flat is not None:
            flat["name"] = str(block.get("name") or "serial").strip() or "serial"
            items.append(flat)
    return enabled, items


def _create(context):
    path = os.path.expanduser(str(LaunchConfiguration("config_file").perform(context)).strip())
    enabled, items = _load_items(path)
    actions = [LogInfo(msg=f"[rmodus] microros config_file={path or '(prazdne)'}")]
    if not enabled:
        actions.append(LogInfo(msg="[rmodus] skip 'microros': microros.enabled is false"))
        return actions
    if not items:
        actions.append(LogInfo(msg="[rmodus] skip 'microros': no devices in microros.items"))
        return actions
    if not package_available("micro_ros_agent"):
        actions.append(skip_log("microros", "micro_ros_agent"))
        return actions
    used_names = set()
    used_devices = set()
    for item in items:
        label = item["name"]
        if not item["enabled"]:
            actions.append(LogInfo(msg=f"[rmodus] skip microros '{label}': enabled is false"))
            continue
        if item["transport"] != "serial":
            actions.append(
                LogInfo(
                    msg=(
                        f"[rmodus] skip microros '{label}': transport {item['transport']!r} "
                        "is not used; firmware talks serial"
                    )
                )
            )
            continue
        device = item["device"]
        if not device:
            actions.append(LogInfo(msg=f"[rmodus] skip microros '{label}': device is empty"))
            continue
        if not os.path.exists(device):
            actions.append(
                LogInfo(
                    msg=(
                        f"[rmodus] skip microros '{label}': {device} does not exist "
                        "(unplugged). Agent respawn on a missing port stalls /drive/*/cmd"
                    )
                )
            )
            continue
        if device in used_devices:
            actions.append(
                LogInfo(msg=f"[rmodus] skip microros '{label}': {device} is already used")
            )
            continue
        used_devices.add(device)
        baudrate = str(item["baudrate"])
        node_name = _node_name(label, used_names)
        actions.append(LogInfo(msg=f"[rmodus] micro-ROS {label} serial {device} @ {baudrate}"))
        actions.append(
            Node(
                package="micro_ros_agent",
                executable="micro_ros_agent",
                name=node_name,
                arguments=["serial", "--dev", device, "-b", baudrate],
                output="screen",
                respawn=False,
            )
        )
    if not any(isinstance(action, Node) for action in actions):
        actions.append(LogInfo(msg="[rmodus] skip 'microros': no enabled serial devices"))
    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("config_file", default_value=""),
            OpaqueFunction(function=_create),
        ]
    )
