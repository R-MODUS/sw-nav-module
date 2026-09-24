"""Central configuration values and filesystem paths for the websocket service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

HERE = Path(__file__).resolve().parent.parent
WEBSOCKET_DIR = HERE / "websocket"
STATIC_DIR = WEBSOCKET_DIR / "static"
INDEX_HTML = WEBSOCKET_DIR / "index.html"

DEFAULT_NAV_TABS = {
    "status": True,
    "controls": True,
    "map": True,
    "sensors": True,
    "tf": True,
    "docs": True,
    "config": True,
    "settings": True,
    "users": True,
}


@dataclass(frozen=True)
class WebConfig:
    """Runtime settings for the web bridge (YAML overlay on these defaults)."""

    testing: bool = True
    operator_pin: str = "1234"
    admin_pin: str = "4321"
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"
    tf_root_frame: str = "base_link"
    tf_broadcast_rate_hz: float = 5.0
    sensor_discovery_rate_hz: float = 1.0
    tf_stale_timeout_sec: float = 3.0
    tf_resubscribe_cooldown_sec: float = 8.0
    # Per-frame stáří dynamického TF: žlutá / červená v UI (statické rámy nikdy)
    tf_frame_stale_warn_sec: float = 0.5
    tf_frame_stale_error_sec: float = 2.0
    lidar_topic: str = "/scan"
    imu_topic: str = "/imu/data"
    bumper_topic_prefix: str = "/bumper/"
    cliff_topic_prefix: str = "/cliff/"
    flow_topic_prefix: str = "/visual_flow/"
    map_topic: str = "/map"
    map_updates_topic: str = "/map_updates"
    plan_topic: str = "/received_global_plan"
    goal_pose_topic: str = "/goal_pose"
    cmd_use_twist_stamped: bool = False
    cmd_frame_id: str = "base_link"
    cmd_vel_topic: str = "/web/cmd_vel"
    e_stop_state_topic: str = "/rmodus/e_stop"
    e_stop_request_topic: str = "/rmodus/e_stop/request"
    e_stop_reset_topic: str = "/rmodus/e_stop/reset"
    # topic (s úvodním /) → zobrazované jméno z lidar/imu .name v profilu
    sensor_names: dict = field(default_factory=dict)
    # {"footprint": [x, y] | None, "mounts": {topic: {kind, name, x, y, yaw, size, threshold}},
    #  "segments": {svg_id: {topic, x?, y?, yaw?, size?, threshold?}}}
    sensor_layout: dict = field(default_factory=dict)
    # {"base_link": {"size": [x, y, z]} | None,
    #  "rmodus_module": {"size": [x, y, z], "offset": [x, y, z], "rpy": [r, p, y]} | None}
    robot_model: dict = field(default_factory=dict)
    # Max. frekvence sensor_data zpráv do UI na jeden senzor (0 = bez omezení)
    sensor_max_rate_hz: float = 10.0
    web_ui_nav_tabs: dict = field(default_factory=lambda: dict(DEFAULT_NAV_TABS))
    web_ui_persist_local: bool = True
    # Empty → derive from --config (…/profiles/*.yaml) or ~/rmodus/configs / $RMODUS_CONFIGS
    configs_root: str = ""
    source: str = "defaults"


# Module-level defaults (used when YAML is missing; also a compatibility alias).
TESTING = True
OPERATOR_PIN = "1234"
ADMIN_PIN = "4321"
HOST = "0.0.0.0"
PORT = 8080
LOG_LEVEL = "info"
TF_ROOT_FRAME = "base_link"
TF_BROADCAST_RATE_HZ = 5.0
SENSOR_DISCOVERY_RATE_HZ = 1.0
TF_STALE_TIMEOUT_SEC = 3.0
TF_RESUBSCRIBE_COOLDOWN_SEC = 8.0
LIDAR_TOPIC = "/scan"
IMU_TOPIC = "/imu/data"
BUMPER_TOPIC_PREFIX = "/bumper/"
CLIFF_TOPIC_PREFIX = "/cliff/"
FLOW_TOPIC_PREFIX = "/visual_flow/"
MAP_TOPIC = "/map"
MAP_UPDATES_TOPIC = "/map_updates"
PLAN_TOPIC = "/received_global_plan"
GOAL_POSE_TOPIC = "/goal_pose"
CMD_USE_TWIST_STAMPED = False
CMD_FRAME_ID = "base_link"
CMD_VEL_TOPIC = "/web/cmd_vel"
E_STOP_STATE_TOPIC = "/rmodus/e_stop"
E_STOP_REQUEST_TOPIC = "/rmodus/e_stop/request"
E_STOP_RESET_TOPIC = "/rmodus/e_stop/reset"
WEB_UI_NAV_TABS = dict(DEFAULT_NAV_TABS)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "y")


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_topic(topic: Any) -> str:
    """Canonical topic name: leading slash, no trailing slash."""
    text = str(topic or "").strip()
    if not text:
        return ""
    return "/" + text.strip("/")


def _enabled(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return _as_bool(value)


def _ros_parameters(loaded: Mapping[str, Any]) -> Mapping[str, Any]:
    block = loaded.get("/**")
    if not isinstance(block, dict):
        return {}
    params = block.get("ros__parameters")
    return params if isinstance(params, dict) else {}


NAMED_SENSOR_BLOCKS = ("lidar", "imu", "bumpers", "cliff_sensors", "flow_sensor", "wheel_odom", "lidar_odom")
MOUNTED_SENSOR_BLOCKS = {"bumpers": "bumper", "cliff_sensors": "cliff"}
FOOTPRINT_PARENT_FRAMES = ("", "base_link", "base_footprint")


def _sensor_items(block: Any):
    """Yield enabled sensor dicts from a flat block or from its items list."""
    if not isinstance(block, dict) or not _enabled(block.get("enabled"), True):
        return
    items = block.get("items")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and _enabled(item.get("enabled"), True):
                yield item
        return
    yield block


def _named_sensor_entries(block: Any):
    """Yield (topic, name) from a flat sensor block or from its items list."""
    for item in _sensor_items(block):
        topic = str(item.get("topic") or "").strip()
        name = str(item.get("name") or "").strip()
        if topic and name:
            yield topic, name


def collect_sensor_names(loaded: Mapping[str, Any]) -> dict:
    """Map sensor topics to display names from <sensor block>.name / items[].name."""
    params = _ros_parameters(loaded)
    names: dict = {}
    for key in NAMED_SENSOR_BLOCKS:
        for topic, name in _named_sensor_entries(params.get(key)):
            normalized = normalize_topic(topic)
            if normalized and normalized not in names:
                names[normalized] = name
    return names


def _float_list(value: Any, length: int) -> Optional[list]:
    if not isinstance(value, (list, tuple)) or len(value) < length:
        return None
    try:
        return [float(v) for v in value[:length]]
    except (TypeError, ValueError):
        return None


def collect_sensor_layout(loaded: Mapping[str, Any]) -> dict:
    """Robot footprint + 2D mount poses (in base_link) of bumpers / cliff sensors for the UI."""
    params = _ros_parameters(loaded)
    footprint = _float_list(_mapping(params.get("base_link")).get("size"), 2)
    mounts: dict = {}
    for key, kind in MOUNTED_SENSOR_BLOCKS.items():
        block = params.get(key)
        threshold = None
        if kind == "cliff":
            threshold = _mapping(_mapping(block).get("estop_request")).get("cliff_range_threshold_m")
        for item in _sensor_items(block):
            topic = normalize_topic(item.get("topic"))
            if not topic:
                continue
            parent = str(item.get("mount_parent_frame") or "").strip().lstrip("/")
            offset = _float_list(item.get("mount_offset"), 2)
            rpy = _float_list(item.get("mount_rpy"), 3)
            entry = {
                "kind": kind,
                "name": str(item.get("name") or "").strip(),
                "size": _float_list(item.get("size"), 2),
            }
            if offset is not None and parent in FOOTPRINT_PARENT_FRAMES:
                entry.update({"x": offset[0], "y": offset[1], "yaw": rpy[2] if rpy else 0.0})
            if threshold is not None:
                entry["threshold"] = _as_float(threshold, 0.0)
            mounts[topic] = entry
    return {"footprint": footprint, "mounts": mounts}


def collect_robot_model(loaded: Mapping[str, Any]) -> dict:
    """Chassis + R-MODUS box dimensions for the TF 3D scene (same keys as the URDF xacros)."""
    params = _ros_parameters(loaded)
    base = _mapping(params.get("base_link"))
    module = _mapping(params.get("rmodus_module", params.get("nav_module")))
    model: dict = {"base_link": None, "rmodus_module": None}

    base_size = _float_list(base.get("size"), 3)
    if base_size:
        model["base_link"] = {"size": base_size}

    module_size = _float_list(module.get("size"), 3)
    if module_size:
        offset = _float_list(module.get("offset"), 3) or [
            _as_float(module.get("offset_x"), 0.0),
            _as_float(module.get("offset_y"), 0.0),
            _as_float(module.get("offset_z"), 0.0),
        ]
        model["rmodus_module"] = {
            "size": module_size,
            "offset": offset,
            "rpy": _float_list(module.get("rpy"), 3) or [0.0, 0.0, 0.0],
        }
    model["parts"] = (
        _wheel_parts(params, base)
        + _sensor_mount_parts(params)
        + _bumper_parts(params)
        + _custom_parts(params)
    )
    return model


HALF_PI = 1.5707963267948966
WHEEL_LAYOUT = {
    "mecanum": (("wheel_fl", 1, 1), ("wheel_fr", 1, -1), ("wheel_rl", -1, 1), ("wheel_rr", -1, -1)),
    "diff4": (("wheel_fl", 1, 1), ("wheel_fr", 1, -1), ("wheel_rl", -1, 1), ("wheel_rr", -1, -1)),
    "diff2": (("wheel_l", 0, 1), ("wheel_r", 0, -1)),
}


def _part(frame: str, shape: str, size: list, color: str, xyz=None, rpy=None, name: str = "") -> dict:
    """One primitive for the TF scene, same convention as URDF (cylinder axis = z, size = [radius, length])."""
    return {
        "name": name or frame,
        "frame": frame,
        "shape": shape,
        "size": size,
        "xyz": xyz or [0.0, 0.0, 0.0],
        "rpy": rpy or [0.0, 0.0, 0.0],
        "color": color,
    }


def _wheel_parts(params: Mapping[str, Any], base: Mapping[str, Any]) -> list:
    drive = _mapping(params.get("drive"))
    layout = WHEEL_LAYOUT.get(str(drive.get("mode") or ""))
    if not layout:
        return []
    radius = _as_float(drive.get("wheel_radius"), 0.05)
    width = _as_float(drive.get("wheel_width"), 0.04)
    # Tvar sedí na wheel_*_link (střed kola už nese TF), ne na base_link.
    return [
        _part(f"{name}_link", "cylinder", [radius, width], "#cbd5e1",
              rpy=[HALF_PI, 0.0, 0.0], name=name)
        for name, _fx, _fy in layout
    ]


def _sensor_mount_parts(params: Mapping[str, Any]) -> list:
    parts = []
    lidar = _mapping(params.get("lidar"))
    if _enabled(lidar.get("enabled"), False):
        size = _float_list(lidar.get("size"), 2) or [0.02, 0.02]
        parts.append(_part("lidar_mount", "cylinder", [size[0] / 2.0, size[1]], "#3b82f6",
                           xyz=[0.0, 0.0, size[1] / 2.0], name="lidar"))
    imu = _mapping(params.get("imu"))
    if _enabled(imu.get("enabled"), False):
        size = _float_list(imu.get("size"), 3) or [0.02, 0.02, 0.01]
        parts.append(_part("imu_mount", "box", size, "#f59e0b",
                           xyz=[0.0, 0.0, size[2] / 2.0], name="imu"))
    return parts


def _bumper_parts(params: Mapping[str, Any]) -> list:
    parts = []
    for item in _sensor_items(params.get("bumpers")):
        name = str(item.get("name") or "").strip()
        size = _float_list(item.get("size"), 3) or [0.02, 0.30, 0.05]
        if not name:
            continue
        parts.append(_part(
            f"bumper_{name}_mount",
            "box",
            size,
            "#ef4444",
            name=f"bumper_{name}",
        ))
    return parts


def _custom_parts(params: Mapping[str, Any]) -> list:
    """parts.items: pose comes from TF (link = part name), shape: frame has no geometry."""
    parts = []
    for item in _sensor_items(params.get("parts")):
        name = str(item.get("name") or "").strip()
        shape = str(item.get("shape") or "frame")
        if not name:
            continue
        if shape == "box":
            size = _float_list(item.get("size"), 3) or [0.05, 0.05, 0.05]
        elif shape == "cylinder":
            size = _float_list(item.get("size"), 2) or [0.05, 0.05]
            size = [size[0] / 2.0, size[1]]
        else:
            continue
        parts.append(_part(name, shape, size, str(item.get("color") or "#94a3b8"), name=name))
    return parts


BLUEPRINT_GEOMETRY_KEYS = ("x", "y", "yaw", "threshold")


def collect_blueprint_segments(web_block: Mapping[str, Any]) -> dict:
    """web.ui.blueprint.segments: {svg_id: topic} or {svg_id: {topic, x?, y?, yaw?, size?, threshold?}}."""
    blueprint = _mapping(_mapping(web_block.get("ui")).get("blueprint"))
    segments: dict = {}
    for seg_id, spec in _mapping(blueprint.get("segments")).items():
        seg_id = str(seg_id).strip()
        item = spec if isinstance(spec, dict) else {"topic": spec}
        topic = normalize_topic(item.get("topic"))
        if not seg_id or not topic:
            continue
        entry = {"topic": topic}
        for key in BLUEPRINT_GEOMETRY_KEYS:
            if key in item:
                entry[key] = _as_float(item.get(key), 0.0)
        size = _float_list(item.get("size"), 2)
        if size:
            entry["size"] = size
        segments[seg_id] = entry
    return segments


def _as_str(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, dict) else {}


def resolve_config_path(cli_path: Optional[str] = None) -> Optional[Path]:
    """Use only the path from launch (--config). No filesystem search."""
    if not cli_path or not str(cli_path).strip():
        return None
    path = Path(str(cli_path).strip()).expanduser()
    if path.is_file():
        return path
    print(f"rmodus_web: soubor konfigu neexistuje: {path}")
    return None


def _web_config_from_block(defaults: WebConfig, block: Mapping[str, Any], source: str) -> WebConfig:
    tf = _mapping(block.get("tf"))
    topics = _mapping(block.get("topics"))
    cmd = _mapping(block.get("cmd"))
    ui = _mapping(block.get("ui"))
    sensors = _mapping(block.get("sensors"))
    nav_overlay = _mapping(ui.get("nav_tabs"))
    nav_tabs = dict(defaults.web_ui_nav_tabs)
    for key, value in nav_overlay.items():
        nav_tabs[str(key)] = _as_bool(value)

    return WebConfig(
        testing=_as_bool(block["testing"]) if "testing" in block else defaults.testing,
        operator_pin=_as_str(block.get("operator_pin"), defaults.operator_pin),
        admin_pin=_as_str(block.get("admin_pin"), defaults.admin_pin),
        host=_as_str(block.get("host"), defaults.host),
        port=_as_int(block.get("port"), defaults.port) if "port" in block else defaults.port,
        log_level=_as_str(block.get("log_level"), defaults.log_level).lower(),
        tf_root_frame=_as_str(tf.get("root_frame"), defaults.tf_root_frame),
        tf_broadcast_rate_hz=_as_float(tf.get("broadcast_rate_hz"), defaults.tf_broadcast_rate_hz),
        tf_stale_timeout_sec=_as_float(tf.get("stale_timeout_sec"), defaults.tf_stale_timeout_sec),
        tf_resubscribe_cooldown_sec=_as_float(
            tf.get("resubscribe_cooldown_sec"), defaults.tf_resubscribe_cooldown_sec
        ),
        tf_frame_stale_warn_sec=_as_float(
            tf.get("frame_stale_warn_sec"), defaults.tf_frame_stale_warn_sec
        ),
        tf_frame_stale_error_sec=_as_float(
            tf.get("frame_stale_error_sec"), defaults.tf_frame_stale_error_sec
        ),
        lidar_topic=_as_str(topics.get("lidar"), defaults.lidar_topic),
        imu_topic=_as_str(topics.get("imu"), defaults.imu_topic),
        bumper_topic_prefix=_as_str(topics.get("bumper_prefix"), defaults.bumper_topic_prefix),
        cliff_topic_prefix=_as_str(topics.get("cliff_prefix"), defaults.cliff_topic_prefix),
        flow_topic_prefix=_as_str(topics.get("flow_prefix"), defaults.flow_topic_prefix),
        map_topic=_as_str(topics.get("map"), defaults.map_topic),
        map_updates_topic=_as_str(topics.get("map_updates"), defaults.map_updates_topic),
        plan_topic=_as_str(topics.get("plan"), defaults.plan_topic),
        goal_pose_topic=_as_str(topics.get("goal_pose"), defaults.goal_pose_topic),
        sensor_discovery_rate_hz=_as_float(
            topics.get("discovery_rate_hz"), defaults.sensor_discovery_rate_hz
        ),
        cmd_use_twist_stamped=(
            _as_bool(cmd["use_twist_stamped"])
            if "use_twist_stamped" in cmd
            else defaults.cmd_use_twist_stamped
        ),
        cmd_frame_id=_as_str(cmd.get("frame_id"), defaults.cmd_frame_id),
        cmd_vel_topic=_as_str(topics.get("cmd_vel"), defaults.cmd_vel_topic),
        e_stop_state_topic=_as_str(topics.get("e_stop_state"), defaults.e_stop_state_topic),
        e_stop_request_topic=_as_str(
            topics.get("e_stop_request"), defaults.e_stop_request_topic
        ),
        e_stop_reset_topic=_as_str(topics.get("e_stop_reset"), defaults.e_stop_reset_topic),
        sensor_max_rate_hz=_as_float(sensors.get("max_rate_hz"), defaults.sensor_max_rate_hz),
        web_ui_nav_tabs=nav_tabs,
        web_ui_persist_local=(
            _as_bool(ui["persist_local"]) if "persist_local" in ui else defaults.web_ui_persist_local
        ),
        configs_root=_as_str(block.get("configs_root"), defaults.configs_root),
        source=source,
    )


def resolve_configs_root(cfg: WebConfig, profile_path: Optional[Path] = None) -> str:
    """Hint for UI; authoritative root comes from /rmodus/config/list."""
    import os

    explicit = (cfg.configs_root or "").strip()
    if explicit:
        return str(Path(explicit).expanduser().resolve())

    if profile_path is not None:
        p = Path(profile_path).expanduser().resolve()
        if p.parent.name == "profiles":
            return str(p.parent.parent)

    env = (os.environ.get("RMODUS_CONFIGS") or "").strip()
    if env:
        return str(Path(env).expanduser().resolve())
    return str((Path.home() / "rmodus" / "configs").resolve())


def load_web_config(cli_path: Optional[str] = None) -> WebConfig:
    """Load block 'web:' from the YAML path passed by launch (--config)."""
    defaults = WebConfig()
    path = resolve_config_path(cli_path)
    if path is None:
        print("rmodus_web: neni --config, pouzivam vestavene defaulty")
        root = resolve_configs_root(defaults, None)
        print(f"rmodus_web: configs_root={root}")
        return WebConfig(configs_root=root, source=defaults.source)

    try:
        import yaml
    except ImportError:
        print("rmodus_web: chybi PyYAML, pouzivam vestavene defaulty")
        root = resolve_configs_root(defaults, path)
        return WebConfig(configs_root=root, source=defaults.source)

    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"rmodus_web: nelze cist {path}: {exc}")
        root = resolve_configs_root(defaults, path)
        return WebConfig(configs_root=root, source=defaults.source)
    except Exception as exc:
        print(f"rmodus_web: YAML parser selhal pro {path}: {exc}")
        root = resolve_configs_root(defaults, path)
        return WebConfig(configs_root=root, source=defaults.source)

    if not isinstance(loaded, dict) or not isinstance(loaded.get("web"), dict):
        print(f"rmodus_web: v {path} chybi blok web:, pouzivam vestavene defaulty")
        root = resolve_configs_root(defaults, path)
        return WebConfig(configs_root=root, source=str(path))

    cfg = _web_config_from_block(defaults, loaded["web"], str(path))
    root = resolve_configs_root(cfg, path)
    sensor_names = collect_sensor_names(loaded)
    cfg = WebConfig(
        **{
            **cfg.__dict__,
            "configs_root": root,
            "sensor_names": sensor_names,
            "sensor_layout": {
                **collect_sensor_layout(loaded),
                "segments": collect_blueprint_segments(loaded["web"]),
            },
            "robot_model": collect_robot_model(loaded),
        }
    )
    print(f"rmodus_web: nacten blok web: z {path}")
    print(f"rmodus_web: configs_root={root}")
    part_names = [p.get("name") for p in cfg.robot_model.get("parts") or []]
    print(f"rmodus_web: model parts: {len(part_names)} ({', '.join(part_names) or 'zadne'})")
    if sensor_names:
        print(f"rmodus_web: jmena senzoru z profilu: {len(sensor_names)}")
    return cfg
