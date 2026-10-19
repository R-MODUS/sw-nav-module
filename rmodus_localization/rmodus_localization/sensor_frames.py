"""Rámy bumperů a cliffů. Stejný vzor jako URDF: <name>_contact a <name>_beam.

Bez ROS. Launch z toho složí parametry obstacle_cloud, uzel stejné funkce
použije, když ve zprávě chybí header.frame_id.
"""

from __future__ import annotations


_ALIASES = {
    "front_left": "fl",
    "front_right": "fr",
    "rear_left": "rl",
    "rear_right": "rr",
}


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "y")


def _explicitly_off(node: dict) -> bool:
    return isinstance(node, dict) and "enabled" in node and not _as_bool(node.get("enabled"))


def frame_from_topic(topic: str, kind: str) -> str:
    """Suffix topicu je name. /bumper/front → front_contact, /cliff/fl → fl_beam."""
    suffix = str(topic or "").rstrip("/").split("/")[-1]
    suffix = _ALIASES.get(suffix, suffix)
    if kind == "bumper":
        return f"{suffix}_contact"
    return f"{suffix}_beam"


def item_frame(item: dict, kind: str) -> str:
    explicit = item.get("frame_id") if isinstance(item, dict) else None
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    name = str(item.get("name") or "").strip() if isinstance(item, dict) else ""
    if name:
        stem = _ALIASES.get(name, name)
        if kind == "bumper":
            return f"{stem}_contact"
        return f"{stem}_beam"
    return frame_from_topic(str(item.get("topic") or "") if isinstance(item, dict) else "", kind)


def resolve_frame(header_frame: str, topic: str, mapping: dict, kind: str) -> str:
    """header.frame_id má přednost. Jinak mapa z profilu, jinak <name>_contact / <name>_beam."""
    text = str(header_frame or "").strip()
    if text:
        return text
    mapped = ""
    if isinstance(mapping, dict):
        mapped = str(mapping.get(topic) or "").strip()
    if mapped:
        return mapped
    return frame_from_topic(topic, kind)


def _items(block) -> list:
    if not isinstance(block, dict) or _explicitly_off(block):
        return []
    found = []
    for item in block.get("items") or []:
        if not isinstance(item, dict) or _explicitly_off(item):
            continue
        topic = item.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            continue
        found.append(item)
    return found


def obstacle_sensor_params(params: dict) -> dict:
    """Topicy a rámy z bumpers.items a cliff_sensors.items. Chybí blok → prázdný seznam."""
    params = params if isinstance(params, dict) else {}
    bumper_topics = []
    bumper_topic_frames = []
    for item in _items(params.get("bumpers")):
        topic = str(item["topic"]).strip()
        frame = item_frame(item, "bumper")
        bumper_topics.append(topic)
        bumper_topic_frames.append(f"{topic}:{frame}")
    range_topics = []
    range_topic_frames = []
    for item in _items(params.get("cliff_sensors")):
        topic = str(item["topic"]).strip()
        frame = item_frame(item, "range")
        range_topics.append(topic)
        range_topic_frames.append(f"{topic}:{frame}")
    return {
        "bumper_topics": bumper_topics,
        "bumper_topic_frames": bumper_topic_frames,
        "range_topics": range_topics,
        "range_topic_frames": range_topic_frames,
        "has_sensors": bool(bumper_topics or range_topics),
    }
