"""twist_mux: pick one velocity source by priority and publish it for the host."""

import os
import re

import yaml
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from rmodus_bringup.package_gates import package_available, skip_log


_DEFAULT_INPUTS = [
    {"name": "estop", "topic": "/estop/cmd_vel", "priority": 255, "timeout": 0.5},
    {"name": "teleop", "topic": "/teleop/cmd_vel", "priority": 100, "timeout": 0.5},
    {"name": "web", "topic": "/web/cmd_vel", "priority": 90, "timeout": 0.5},
    {"name": "nav", "topic": "/nav/cmd_vel", "priority": 10, "timeout": 0.5},
]
_DEFAULT_LOCKS = [
    {"name": "e_stop", "topic": "/rmodus/e_stop", "priority": 255, "timeout": 0.5},
]


def _as_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _load_profile(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        root = yaml.safe_load(handle) or {}
    return root if isinstance(root, dict) else {}


def _block(root: dict) -> dict:
    params = root.get("/**", {})
    params = params.get("ros__parameters", {}) if isinstance(params, dict) else {}
    block = params.get("cmd_mux") if isinstance(params, dict) else None
    return block if isinstance(block, dict) else {}


def _estop_flag(root: dict) -> bool:
    bringup = root.get("bringup", {})
    if not isinstance(bringup, dict):
        return True
    return _as_bool(bringup.get("estop"), True)


def _param_name(label: str, used: set) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", str(label)).strip("_") or "input"
    if not base[0].isalpha():
        base = f"in_{base}"
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _entries(raw, defaults: list) -> list:
    items = raw if isinstance(raw, list) else defaults
    out = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not _as_bool(item.get("enabled"), True):
            continue
        topic = str(item.get("topic") or "").strip()
        if not topic:
            continue
        out.append(
            {
                "name": str(item.get("name") or f"input_{index}"),
                "topic": topic,
                "priority": int(item.get("priority", 1)),
                "timeout": float(item.get("timeout", 0.5)),
            }
        )
    return out


def _flatten(group: str, entries: list, params: dict) -> None:
    used: set = set()
    for entry in entries:
        key = _param_name(entry["name"], used)
        params[f"{group}.{key}.topic"] = entry["topic"]
        params[f"{group}.{key}.priority"] = entry["priority"]
        params[f"{group}.{key}.timeout"] = entry["timeout"]


def _create(context):
    path = os.path.expanduser(str(LaunchConfiguration("config_file").perform(context)).strip())
    root = _load_profile(path)
    cfg = _block(root)
    if not _as_bool(cfg.get("enabled"), True):
        return [LogInfo(msg="[rmodus] skip 'cmd_mux': cmd_mux.enabled is false")]
    if not package_available("twist_mux"):
        return [skip_log("cmd_mux", "twist_mux")]

    inputs = _entries(cfg.get("inputs"), _DEFAULT_INPUTS)
    if not inputs:
        return [LogInfo(msg="[rmodus] skip 'cmd_mux': no enabled inputs")]
    locks = _entries(cfg.get("locks"), _DEFAULT_LOCKS)

    actions = []
    # Zámek bez běžícího e-stopu by po timeoutu zamkl robota natrvalo.
    if locks and not _estop_flag(root):
        actions.append(
            LogInfo(
                msg=(
                    "[rmodus] cmd_mux: bringup.estop=false → locks skipped, "
                    "robot se NEZASTAVÍ e-stopem ani nárazníky"
                )
            )
        )
        locks = []
    elif locks and not package_available("rmodus_estop"):
        actions.append(
            LogInfo(
                msg=(
                    "[rmodus] cmd_mux: rmodus_estop chybí → zámek zůstane zamčený "
                    "a robot se nerozjede (bringup.estop: false pro test bez e-stopu)"
                )
            )
        )

    output_topic = str(cfg.get("output_topic") or "/cmd_vel").strip()
    params = {"use_stamped": _as_bool(cfg.get("use_stamped"), False)}
    _flatten("topics", inputs, params)
    _flatten("locks", locks, params)

    summary = ", ".join(f"{e['name']}={e['topic']}@{e['priority']}" for e in inputs)
    actions.append(LogInfo(msg=f"[rmodus] cmd_mux → {output_topic}: {summary}"))
    actions.append(
        Node(
            package="twist_mux",
            executable="twist_mux",
            name="twist_mux",
            parameters=[params],
            remappings=[("cmd_vel_out", output_topic)],
            output="screen",
        )
    )
    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument("config_file", default_value=""),
            OpaqueFunction(function=_create),
        ]
    )
