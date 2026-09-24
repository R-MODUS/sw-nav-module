"""Host drive node from profile /**/ros__parameters/drive (+ wheel_odom, bringup.localization)."""

import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _resolve(path: str) -> str:
    if not path:
        return ""
    return os.path.normpath(os.path.expanduser(str(path).strip()))


def _as_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _load(path: str):
    if not path or not os.path.isfile(path):
        return {}, {}
    with open(path, "r", encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    if not isinstance(root, dict):
        return {}, {}
    bringup = root.get("bringup") if isinstance(root.get("bringup"), dict) else {}
    params = (root.get("/**") or {}).get("ros__parameters") or {}
    return bringup, params if isinstance(params, dict) else {}


def _create(context):
    default = os.path.join(get_package_share_directory("rmodus_chassis"), "config", "chassis.yaml")
    path = _resolve(LaunchConfiguration("robot_config_file").perform(context)) or default
    if not os.path.isfile(path):
        path = default

    bringup, params = _load(path)
    cfg = params.get("drive") if isinstance(params.get("drive"), dict) else {}
    if not cfg or not _as_bool(cfg.get("enabled"), False):
        return [LogInfo(msg="[rmodus_chassis] drive disabled or missing — no drive node")]

    units = [u for u in (cfg.get("units") or []) if isinstance(u, dict) and u.get("name")]
    wheels = [
        w for w in (cfg.get("wheels") or [])
        if isinstance(w, dict) and w.get("name") and _as_bool(w.get("enabled"), True)
    ]
    if not units or not wheels:
        return [LogInfo(msg="[rmodus_chassis] drive needs units[] and wheels[] — skipped")]

    wheel_odom = params.get("wheel_odom") if isinstance(params.get("wheel_odom"), dict) else {}
    publish_odom = _as_bool(wheel_odom.get("enabled"), False)
    odom_topic = str(wheel_odom.get("topic") or "/odom")

    raw_tf = LaunchConfiguration("publish_tf").perform(context).strip().lower()
    if raw_tf in ("true", "false", "1", "0", "yes", "no", "on", "off"):
        publish_tf = _as_bool(raw_tf)
    else:
        # auto: EKF owns odom -> base_footprint when localization runs.
        publish_tf = not _as_bool(bringup.get("localization"), True)

    node_params = {
        "cmd_vel_topic": str(cfg.get("cmd_vel_topic", "/cmd_vel")),
        "mode": str(cfg.get("mode", "diff2")),
        "wheel_radius": float(cfg.get("wheel_radius", 0.05)),
        "track_width": float(cfg.get("track_width", 0.3)),
        "wheelbase": float(cfg.get("wheelbase", 0.0)),
        "max_wheel_speed": float(cfg.get("max_wheel_speed", 10.0)),
        "cmd_rate_hz": float(cfg.get("cmd_rate_hz", 20.0)),
        "cmd_timeout_sec": float(cfg.get("cmd_timeout_sec", 0.5)),
        "state_timeout_sec": float(cfg.get("state_timeout_sec", 0.5)),
        "feedback_rate_hz": float(cfg.get("feedback_rate_hz", 20.0)),
        "unit_names": [str(u["name"]) for u in units],
        "unit_cmd_topics": [str(u.get("cmd_topic") or f"/drive/{u['name']}/cmd") for u in units],
        "unit_state_topics": [str(u.get("state_topic") or "") for u in units],
        "unit_channels": [int(u.get("channels", 0)) for u in units],
        "wheel_names": [str(w["name"]) for w in wheels],
        "wheel_units": [str(w.get("unit", units[0]["name"])) for w in wheels],
        "wheel_channels": [int(w.get("channel", n)) for n, w in enumerate(wheels)],
        "wheel_inverts": [_as_bool(w.get("invert"), False) for w in wheels],
        "wheel_ticks_per_rev": [int(w.get("ticks_per_rev", 0)) for w in wheels],
        "publish_odom": publish_odom,
        "odom_topic": odom_topic,
        "odom_frame": str(cfg.get("odom_frame", "odom")),
        "base_frame": str(cfg.get("base_frame", "base_footprint")),
        "publish_tf": publish_tf,
        "publish_joint_states": _as_bool(cfg.get("joint_states"), True),
    }

    return [
        Node(
            package="rmodus_chassis",
            executable="drive",
            name="rmodus_drive",
            parameters=[node_params],
            output="screen",
            emulate_tty=True,
        )
    ]


def generate_launch_description():
    default = os.path.join(get_package_share_directory("rmodus_chassis"), "config", "chassis.yaml")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "robot_config_file",
                default_value=default,
                description="Profile YAML with /**/ros__parameters/drive",
            ),
            DeclareLaunchArgument(
                "publish_tf",
                default_value="auto",
                description="odom -> base_footprint TF: true | false | auto (= !bringup.localization)",
            ),
            OpaqueFunction(function=_create),
        ]
    )
