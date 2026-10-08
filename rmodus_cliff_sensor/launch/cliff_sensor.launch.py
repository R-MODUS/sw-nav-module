import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _as_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


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


def _beam_frame(item: dict) -> str:
    """frame_id, or <name>_beam. Same expression as cliff_sensors.urdf.xacro."""
    return str(item.get("frame_id") or f"{item.get('name', 'x')}_beam")


def _static_tf(item: dict) -> Node:
    offset = item.get("mount_offset", [0.0, 0.0, 0.0])
    rpy = item.get("mount_rpy", [0.0, 0.0, 0.0])
    parent = str(item.get("mount_parent_frame", "base_link"))
    child = _beam_frame(item)
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
    frames = [_beam_frame(i) for i in items]
    indices = [int(i.get("pin", n)) for n, i in enumerate(items)]
    state_topic = str(cfg.get("state_topic", "/robot/cliffs/range"))
    use_sim = _as_bool(LaunchConfiguration("use_sim_time").perform(context), False)
    hw_arg = LaunchConfiguration("hardware").perform(context).strip()
    read_hw = _as_bool(cfg.get("hardware", True), True) if not hw_arg else _as_bool(hw_arg, True)

    first = items[0]
    nodes = [
        Node(
            package="rmodus_cliff_sensor",
            executable="cliff_sensors",
            name="cliff_sensors_node",
            parameters=[
                {
                    "use_sim_time": use_sim,
                    "state_topic": state_topic,
                    "cliff_indices": indices,
                    "cliff_topics": topics,
                    "cliff_frame_ids": frames,
                    "range_msg_min": float(cfg.get("range_msg_min", 0.02)),
                    "range_msg_max": float(cfg.get("range_msg_max", 0.5)),
                    "field_of_view": float(cfg.get("field_of_view", 0.05)),
                }
            ],
            output="screen",
        )
    ]
    if read_hw:
        nodes.append(
            Node(
                package="rmodus_cliff_sensor",
                executable="cliff_hw",
                name="cliff_hw_node",
                parameters=[
                    {
                        "use_sim_time": use_sim,
                        "state_topic": state_topic,
                        "address": str(cfg.get("address", first.get("address", "0x48"))),
                        "timer_period": float(cfg.get("timer_period", 0.1)),
                        "v_points": list(
                            cfg.get("v_points", first.get("v_points", [0.3, 0.4, 0.8, 1.2, 2.0, 2.5]))
                        ),
                        "d_points": list(
                            cfg.get("d_points", first.get("d_points", [0.20, 0.15, 0.08, 0.05, 0.03, 0.02]))
                        ),
                    }
                ],
                output="screen",
            )
        )
    if LaunchConfiguration("publish_tf").perform(context).strip().lower() in ("1", "true", "yes", "on"):
        for item in items:
            nodes.append(_static_tf(item))

    estop = cfg.get("estop_request") if isinstance(cfg.get("estop_request"), dict) else {}
    if bool(estop.get("enabled", True)):
        nodes.append(
            Node(
                package="rmodus_cliff_sensor",
                executable="cliff_estop_request",
                name="cliff_estop_request",
                parameters=[
                    {
                        "use_sim_time": use_sim,
                        "enabled": True,
                        "request_topic": str(
                            estop.get("request_topic", "/rmodus/e_stop/request")
                        ),
                        "cliff_topics": topics,
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
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument(
                "hardware",
                default_value="",
                description="true = ADS1115 publikuje state_topic. Prázdné = cliff_sensors.hardware v profilu",
            ),
            DeclareLaunchArgument(
                "publish_tf",
                default_value="true",
                description="Static TF mount. false když rámce drží URDF (description nebo Gazebo)",
            ),
            OpaqueFunction(function=_create),
        ]
    )
