"""Složení parametrů EKF z profilu. Bez ROS, ať to jde pustit v testu.

Vstup se přidá jen když blok ve YAML je, enabled je true a má type i topic.
Chybějící blok se nedoplňuje. Kompilátor mapy s enabled: false maže celé.
"""

from __future__ import annotations


# Pořadí je pořadí odom0, odom1, … Stejné masky jako dřív v launchi.
_BLOCKS = (
    ("wheel_odom", "odom"),
    ("lidar_odom", "odom"),
    ("imu", "imu"),
    ("flow_sensor", "twist"),
)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "y")


def _odom_config():
    return [
        True,
        True,
        False,
        False,
        False,
        True,
        True,
        True,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
    ]


def _imu_config():
    return [
        False,
        False,
        False,
        True,
        True,
        True,
        False,
        False,
        False,
        True,
        True,
        True,
        False,
        False,
        False,
    ]


def _twist_config():
    return [
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    ]


def _input_ok(block, expected_type: str) -> bool:
    if not isinstance(block, dict):
        return False
    if "enabled" not in block or not _as_bool(block.get("enabled")):
        return False
    if block.get("type") != expected_type:
        return False
    topic = block.get("topic")
    return isinstance(topic, str) and bool(topic.strip())


def iter_ekf_inputs(params: dict):
    """(jméno bloku, type, topic) v pořadí, v jakém je EKF dostane."""
    if not isinstance(params, dict):
        return
    for name, expected in _BLOCKS:
        if name not in params:
            continue
        block = params[name]
        if not _input_ok(block, expected):
            continue
        yield name, expected, str(block["topic"]).strip()


def _append(ekf_params: dict, counters: dict, sensor_type: str, topic: str) -> None:
    idx = counters[sensor_type]
    prefix = f"{sensor_type}{idx}"
    ekf_params[prefix] = topic
    if sensor_type == "odom":
        ekf_params[f"{prefix}_config"] = _odom_config()
        ekf_params[f"{prefix}_differential"] = False
        ekf_params[f"{prefix}_queue_size"] = 10
    elif sensor_type == "imu":
        ekf_params[f"{prefix}_config"] = _imu_config()
        ekf_params[f"{prefix}_differential"] = False
        ekf_params[f"{prefix}_queue_size"] = 10
        ekf_params[f"{prefix}_remove_gravitational_acceleration"] = True
    elif sensor_type == "twist":
        ekf_params[f"{prefix}_config"] = _twist_config()
        ekf_params[f"{prefix}_relative"] = False
    counters[sensor_type] += 1


def build_ekf_params(params: dict, use_sim_time: bool = False) -> dict:
    """Parametry ekf_node. Žádný senzor se nezapne jen proto, že v YAML není."""
    ekf_params = {
        "use_sim_time": bool(use_sim_time),
        "frequency": 30.0,
        "two_d_mode": True,
        "publish_tf": True,
        "map_frame": "map",
        "odom_frame": "odom",
        "base_link_frame": "base_footprint",
        "world_frame": "odom",
    }
    counters = {"odom": 0, "imu": 0, "twist": 0}
    for _name, sensor_type, topic in iter_ekf_inputs(params):
        _append(ekf_params, counters, sensor_type, topic)
    return ekf_params
