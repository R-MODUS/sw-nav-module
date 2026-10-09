"""Přepis Nav2 parametrů z profilu robota. Bez ROS.

Výstup velocity_smootheru se nemění: launch ho pořád mapuje na /nav/cmd_vel.
"""

from __future__ import annotations

import copy
import os
import tempfile

import yaml


_DEFAULT_LINEAR_MPS = 0.5
_DEFAULT_ANGULAR_RPS = 0.7
_SCAN_FALLBACK = "/scan"


def load_robot_parameters(path: str) -> dict:
    if not path or not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return ros_parameters(loaded if isinstance(loaded, dict) else {})


def map_yaml_from_parameters(params: dict) -> str:
    block = params.get("map") if isinstance(params, dict) else None
    if not isinstance(block, dict):
        return ""
    return str(block.get("yaml_filename") or "").strip()


def write_params(document: dict, name: str = "nav2_params.ros.yaml") -> str:
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


def ros_parameters(root: dict) -> dict:
    if not isinstance(root, dict):
        return {}
    wrapped = root.get("/**")
    if isinstance(wrapped, dict):
        params = wrapped.get("ros__parameters")
        if isinstance(params, dict):
            return params
    return {}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def linear_speed_limit(drive: dict) -> float:
    """wheel_radius * max_wheel_speed. Chybí-li, dnešních 0.5 m/s."""
    if not isinstance(drive, dict):
        return _DEFAULT_LINEAR_MPS
    radius = _number(drive.get("wheel_radius"))
    speed = _number(drive.get("max_wheel_speed"))
    if radius is None or speed is None or radius <= 0.0 or speed <= 0.0:
        return _DEFAULT_LINEAR_MPS
    return radius * speed


def lidar_topic(robot_params: dict) -> str:
    lidar = robot_params.get("lidar") if isinstance(robot_params, dict) else None
    if isinstance(lidar, dict):
        topic = lidar.get("topic")
        if isinstance(topic, str) and topic.strip():
            return topic.strip()
    return _SCAN_FALLBACK


def footprint_from_size(size) -> str:
    """Obdélník v base_footprint. Půlka size[0] a size[1]. offset_z ani size[2] se neberou.

    Prázdný řetězec = size nejde použít, volající otisk nepřepisuje.
    """
    if not isinstance(size, (list, tuple)) or len(size) < 2:
        return ""
    length = _number(size[0])
    width = _number(size[1])
    if length is None or width is None or length <= 0.0 or width <= 0.0:
        return ""
    hx = length / 2.0
    hy = width / 2.0
    points = [(hx, hy), (hx, -hy), (-hx, -hy), (-hx, hy)]
    body = ", ".join(f"[{x:.4f}, {y:.4f}]" for x, y in points)
    return f"[{body}]"


def _is_mecanum(drive: dict) -> bool:
    if not isinstance(drive, dict):
        return False
    return str(drive.get("mode") or "").strip().lower() == "mecanum"


def _force_key(node, key: str, value) -> None:
    if isinstance(node, dict):
        if key in node:
            node[key] = value
        for child in node.values():
            _force_key(child, key, value)
    elif isinstance(node, list):
        for child in node:
            _force_key(child, key, value)


def _nested(root: dict, *keys):
    node = root
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, dict) else None


def _set_scan(layer: dict, topic: str) -> None:
    scan = layer.get("scan") if isinstance(layer, dict) else None
    if isinstance(scan, dict):
        scan["topic"] = topic


def _apply_footprint(costmap: dict, footprint: str) -> None:
    if not footprint or not isinstance(costmap, dict):
        return
    costmap.pop("robot_radius", None)
    costmap["footprint"] = footprint


def _apply_drive(follow: dict, smoother: dict, drive: dict) -> None:
    if not isinstance(follow, dict):
        return
    limit = linear_speed_limit(drive)
    follow["max_vel_x"] = limit
    follow["max_speed_xy"] = limit
    follow["max_vel_theta"] = _DEFAULT_ANGULAR_RPS
    mecanum = _is_mecanum(drive)
    lateral = 0.0
    if mecanum:
        follow["max_vel_y"] = lateral
        follow["min_vel_y"] = -lateral
        follow["vy_samples"] = 5
        accel_x = _number(follow.get("acc_lim_x"))
        accel_y = accel_x if accel_x is not None and accel_x != 0.0 else 1.0
        follow["acc_lim_y"] = accel_y
        follow["decel_lim_y"] = -abs(accel_y)
    else:
        follow["max_vel_y"] = 0.0
        follow["min_vel_y"] = 0.0
        follow["vy_samples"] = 1
        follow["acc_lim_y"] = 0.0
        follow["decel_lim_y"] = 0.0

    if not isinstance(smoother, dict):
        return
    max_v = smoother.get("max_velocity")
    min_v = smoother.get("min_velocity")
    theta_max = 1.0
    theta_min = -1.0
    if isinstance(max_v, (list, tuple)) and len(max_v) >= 3 and _number(max_v[2]) is not None:
        theta_max = _number(max_v[2])
    if isinstance(min_v, (list, tuple)) and len(min_v) >= 3 and _number(min_v[2]) is not None:
        theta_min = _number(min_v[2])
    lateral = limit if mecanum else 0.0
    smoother["max_velocity"] = [limit, lateral, theta_max]
    smoother["min_velocity"] = [-limit, -lateral, theta_min]


def navigation_sources(slam: bool, map_yaml: str, map_file_exists: bool) -> dict:
    """Odkud bere navigace map→odom. Slam a AMCL se nikdy nezapnou najednou."""
    if slam:
        return {"start_amcl": False, "start_navigate": True, "reason": "slam"}
    if str(map_yaml or "").strip() and map_file_exists:
        return {"start_amcl": True, "start_navigate": True, "reason": "saved"}
    return {"start_amcl": False, "start_navigate": False, "reason": "none"}


def apply_robot_profile(
    nav_params: dict,
    robot_params: dict,
    use_sim_time: bool,
    map_yaml: str = "",
) -> dict:
    """Vrátí kopii Nav2 YAML s otiskem, scanem, limity a use_sim_time z profilu a argumentu."""
    out = copy.deepcopy(nav_params if isinstance(nav_params, dict) else {})
    robot = robot_params if isinstance(robot_params, dict) else {}
    drive = robot.get("drive") if isinstance(robot.get("drive"), dict) else {}
    base = robot.get("base_link") if isinstance(robot.get("base_link"), dict) else {}

    footprint = footprint_from_size(base.get("size"))
    topic = lidar_topic(robot)

    for costmap_name, inner, layer_name in (
        ("local_costmap", "local_costmap", "voxel_layer"),
        ("global_costmap", "global_costmap", "obstacle_layer"),
    ):
        costmap = _nested(out, costmap_name, inner, "ros__parameters")
        if costmap is None:
            continue
        _apply_footprint(costmap, footprint)
        layer = costmap.get(layer_name)
        _set_scan(layer if isinstance(layer, dict) else None, topic)

    follow = _nested(out, "controller_server", "ros__parameters", "FollowPath")
    smoother = _nested(out, "velocity_smoother", "ros__parameters")
    if isinstance(robot.get("drive"), dict):
        _apply_drive(follow, smoother, drive)

    amcl = _nested(out, "amcl", "ros__parameters")
    if amcl is not None:
        amcl["base_frame_id"] = "base_footprint"
        amcl["odom_frame_id"] = "odom"
        amcl["global_frame_id"] = "map"
        amcl["scan_topic"] = topic

    map_block = _nested(out, "map_server", "ros__parameters")
    if map_block is not None and str(map_yaml or "").strip():
        map_block["yaml_filename"] = str(map_yaml).strip()

    _force_key(out, "use_sim_time", bool(use_sim_time))
    return out
