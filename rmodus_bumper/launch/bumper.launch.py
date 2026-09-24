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
    if isinstance(root.get("bumpers"), dict):
        return root["bumpers"]
    params = root.get("/**", {}).get("ros__parameters", {})
    if isinstance(params, dict) and isinstance(params.get("bumpers"), dict):
        return params["bumpers"]
    # Legacy: bumpers was a bare list under ros__parameters
    if isinstance(params, dict) and isinstance(params.get("bumpers"), list):
        return {"enabled": True, "items": params["bumpers"]}
    return {}


def _enabled_items(cfg: dict) -> list:
    items = cfg.get("items") or []
    out = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled", True):
            continue
        out.append(item)
    return out


def _tf_node(name: str, parent: str, child: str, xyz, rpy) -> Node:
    return Node(
        package="tf2_ros",
        executable="static_transform_publisher",
        name=name,
        arguments=[
            "--x", str(float(xyz[0])),
            "--y", str(float(xyz[1])),
            "--z", str(float(xyz[2])),
            "--roll", str(float(rpy[0])),
            "--pitch", str(float(rpy[1])),
            "--yaw", str(float(rpy[2])),
            "--frame-id", parent,
            "--child-frame-id", child,
        ],
    )


def _static_tf(item: dict) -> list:
    """Same chain as rmodus_description/urdf/bumper_bodies.urdf.xacro: parent → _mount → contact."""
    name = str(item.get("name", "x"))
    size = item.get("size") or [0.02, 0.3, 0.05]
    mount = f"bumper_{name}_mount"
    contact = str(item.get("frame_id") or f"bumper_{name}_contact")
    return [
        _tf_node(
            f"bumper_tf_{name}_mount",
            str(item.get("mount_parent_frame", "base_link")),
            mount,
            item.get("mount_offset", [0.0, 0.0, 0.0]),
            item.get("mount_rpy", [0.0, 0.0, 0.0]),
        ),
        _tf_node(
            f"bumper_tf_{name}_contact",
            mount,
            contact,
            item.get("contact_offset", [float(size[0]) / 2.0, 0.0, 0.0]),
            item.get("contact_rpy", [0.0, 0.0, 0.0]),
        ),
    ]


def _create(context):
    default = os.path.join(
        get_package_share_directory("rmodus_bumper"), "config", "bumper.yaml"
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

    topics = [str(i.get("topic", f"/bumper/{i.get('name')}")) for i in items]
    frames = [
        str(i.get("frame_id") or f"bumper_{i.get('name')}_contact") for i in items
    ]
    # pin = index 0..7 v poli z ESP, ne číslo GPIO.
    indices = [int(i.get("pin", n)) for n, i in enumerate(items)]
    widths = [float((i.get("size") or [0.02, 0.3, 0.05])[1]) for i in items]
    depths = [float((i.get("size") or [0.02, 0.3, 0.05])[0]) for i in items]
    heights = [float((i.get("size") or [0.02, 0.3, 0.05])[2]) for i in items]

    params = {
        "state_topic": str(cfg.get("state_topic", "/robot/bumpers/state")),
        "bumper_indices": indices,
        "bumper_topics": topics,
        "bumper_frame_ids": frames,
        "bumper_widths": widths,
        "bumper_depths": depths,
        "bumper_heights": heights,
    }

    nodes = [
        Node(
            package="rmodus_bumper",
            executable="bumper_sensors",
            name="bumper_sensors_node",
            parameters=[params],
            output="screen",
        )
    ]
    # Without rmodus_description nobody else publishes the bumper frames.
    if LaunchConfiguration("publish_tf").perform(context).strip().lower() in ("1", "true", "yes", "on"):
        for item in items:
            nodes.extend(_static_tf(item))

    estop = cfg.get("estop_request") if isinstance(cfg.get("estop_request"), dict) else {}
    if bool(estop.get("enabled", True)):
        nodes.append(
            Node(
                package="rmodus_bumper",
                executable="bumper_estop_request",
                name="bumper_estop_request",
                parameters=[
                    {
                        "enabled": True,
                        "request_topic": str(
                            estop.get("request_topic", "/rmodus/e_stop/request")
                        ),
                        "bumper_topics": topics,
                        "retrigger_while_contact": bool(
                            estop.get("retrigger_while_contact", False)
                        ),
                    }
                ],
                output="screen",
            )
        )
    return nodes


def generate_launch_description():
    default = os.path.join(
        get_package_share_directory("rmodus_bumper"), "config", "bumper.yaml"
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument("config_file", default_value=default),
            DeclareLaunchArgument(
                "publish_tf",
                default_value="true",
                description="Static TF _mount → contact; false when rmodus_description publishes them",
            ),
            OpaqueFunction(function=_create),
        ]
    )
