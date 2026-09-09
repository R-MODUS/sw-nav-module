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
    if isinstance(root.get("cliff_sensors"), dict):
        return root["cliff_sensors"]
    params = root.get("/**", {}).get("ros__parameters", {})
    if isinstance(params, dict) and isinstance(params.get("cliff_sensors"), dict):
        return params["cliff_sensors"]
    if isinstance(params, dict) and isinstance(params.get("cliff_sensors"), list):
        return {"enabled": True, "items": params["cliff_sensors"]}
    return {}


def _enabled_items(cfg: dict) -> list:
    return [
        i for i in (cfg.get("items") or [])
        if isinstance(i, dict) and i.get("enabled", True)
    ]


def _static_tf(item: dict) -> Node:
    offset = item.get("mount_offset", [0.0, 0.0, 0.0])
    rpy = item.get("mount_rpy", [0.0, 0.0, 0.0])
    parent = str(item.get("mount_parent_frame", "base_link"))
    child = str(item.get("frame_id") or f"cliff_sensor_{item.get('name', 'x')}_beam")
    return Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name=f"cliff_tf_{item.get('name', 'x')}",
        arguments=[
            "--x", str(float(offset[0])),
            "--y", str(float(offset[1])),
            "--z", str(float(offset[2])),
            "--roll", str(float(rpy[0])),
            "--pitch", str(float(rpy[1])),
            "--yaw", str(float(rpy[2])),
            "--frame-id", parent,
            "--child-frame-id", child,
        ],
    )


def _create(context):
    default = os.path.join(
        get_package_share_directory("rmodus_cliff_sensor"), "config", "cliff.yaml"
    )
    raw = LaunchConfiguration("config_file").perform(context).strip()
    path = os.path.normpath(os.path.expanduser(raw)) if raw else default
    if not os.path.isfile(path):
        path = default

    cfg = _load_block(path)
    if not bool(cfg.get("enabled", True)):
        return []

    items = _enabled_items(cfg)
    if not items:
        return []

    topics = [str(i.get("topic", f"/cliff/{i.get('name')}")) for i in items]
    frames = [
        str(i.get("frame_id") or f"cliff_sensor_{i.get('name')}_beam") for i in items
    ]
    while len(topics) < 4:
        topics.append(f"/cliff/unused_{len(topics)}")
        frames.append(f"cliff_sensor_unused_{len(frames)}_beam")
    topics, frames = topics[:4], frames[:4]

    first = items[0]
    params = {
        "address": str(cfg.get("address", first.get("address", "0x48"))),
        "cliff_topics": topics,
        "cliff_frame_ids": frames,
        "range_msg_min": float(cfg.get("range_msg_min", 0.02)),
        "range_msg_max": float(cfg.get("range_msg_max", 0.5)),
        "field_of_view": float(cfg.get("field_of_view", 0.05)),
        "timer_period": float(cfg.get("timer_period", 0.1)),
        "v_points": list(cfg.get("v_points", first.get("v_points", [0.3, 0.4, 0.8, 1.2, 2.0, 2.5]))),
        "d_points": list(cfg.get("d_points", first.get("d_points", [0.20, 0.15, 0.08, 0.05, 0.03, 0.02]))),
    }

    nodes = [
        Node(
            package="rmodus_cliff_sensor",
            executable="cliff_sensors",
            name="cliff_sensors_node",
            parameters=[params],
            output="screen",
        )
    ]
    for item in items:
        nodes.append(_static_tf(item))

    estop = cfg.get("estop_request") if isinstance(cfg.get("estop_request"), dict) else {}
    if bool(estop.get("enabled", True)):
        active_topics = [t for t in topics if not t.startswith("/cliff/unused_")]
        nodes.append(
            Node(
                package="rmodus_cliff_sensor",
                executable="cliff_estop_request",
                name="cliff_estop_request",
                parameters=[
                    {
                        "enabled": True,
                        "request_topic": str(
                            estop.get("request_topic", "/rmodus/e_stop/request")
                        ),
                        "cliff_topics": active_topics,
                        "cliff_range_threshold_m": float(
                            estop.get("cliff_range_threshold_m", 0.12)
                        ),
                        "retrigger_while_cliff": bool(
                            estop.get("retrigger_while_cliff", False)
                        ),
                    }
                ],
                output="screen",
            )
        )
    return nodes


def generate_launch_description():
    default = os.path.join(
        get_package_share_directory("rmodus_cliff_sensor"), "config", "cliff.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("config_file", default_value=default),
            OpaqueFunction(function=_create),
        ]
    )
