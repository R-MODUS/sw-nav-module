"""Čtení profilu a přepis use_sim_time. Bez ROS."""

from __future__ import annotations

import copy
import os
import tempfile

import yaml


def read_yaml(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def ros_parameters(root: dict) -> dict:
    if not isinstance(root, dict):
        return {}
    wrapped = root.get("/**")
    if isinstance(wrapped, dict):
        params = wrapped.get("ros__parameters")
        if isinstance(params, dict):
            return params
    return {}


def deep_merge(base_obj, override_obj):
    if isinstance(base_obj, dict) and isinstance(override_obj, dict):
        merged = dict(base_obj)
        for key, value in override_obj.items():
            if key in merged:
                merged[key] = deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    return override_obj


def load_ros_parameters(path: str) -> dict:
    return ros_parameters(read_yaml(path))


def load_merged_ros_parameters(robot_path: str, global_path: str = "") -> dict:
    root = read_yaml(robot_path)
    if global_path and os.path.isfile(global_path):
        root = deep_merge(root, read_yaml(global_path))
    return ros_parameters(root)


def force_key(document: dict, key: str, value):
    """Vrátí kopii, ve které má každý výskyt klíče danou hodnotu."""
    out = copy.deepcopy(document if isinstance(document, dict) else {})

    def _walk(node) -> None:
        if isinstance(node, dict):
            if key in node:
                node[key] = value
            for child in node.values():
                _walk(child)
        elif isinstance(node, list):
            for child in node:
                _walk(child)

    _walk(out)
    return out


def write_yaml(document: dict, name: str) -> str:
    directory = os.path.join(tempfile.gettempdir(), "rmodus")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    payload = yaml.safe_dump(
        document,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return path
