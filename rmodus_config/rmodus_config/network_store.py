"""Read/write configs/network.yaml with password redaction for UI/API."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Optional

from rmodus_config.store import ConfigPaths, ensure_layout

_PASSWORD_KEYS = ("password", "psk", "passphrase")


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ValueError(f"neplatný network.yaml: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError("network.yaml musí být YAML mapování")
    return doc


def _dump_yaml(doc: Mapping[str, Any]) -> str:
    import yaml  # type: ignore

    return yaml.safe_dump(dict(doc), sort_keys=False, allow_unicode=True)


def default_network_doc() -> dict[str, Any]:
    return {
        "boot": {"network": True},
        "network": {
            "mode": "client",
            "networks": [],
            "ap": {
                "ssid": "R-MODUS",
                "password": "",
                "address": "192.168.50.1/24",
                "hidden": False,
            },
            "fallback_ap": {
                "enabled": True,
                "timeout": 60,
                "ssid": "R-MODUS-fallback",
                "password": "",
                "hidden": False,
            },
            "country": "CZ",
            "ros_domain_id": 0,
        },
    }


def read_network_doc(paths: ConfigPaths) -> dict[str, Any]:
    ensure_layout(paths)
    if not paths.network_yaml.is_file():
        return default_network_doc()
    return _load_yaml(paths.network_yaml)


def _redact_mapping(obj: Any) -> Any:
    if isinstance(obj, list):
        return [_redact_mapping(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out: dict[str, Any] = {}
    for key, val in obj.items():
        if str(key).lower() in _PASSWORD_KEYS:
            has = bool(str(val or "").strip())
            out[key] = ""
            out[f"{key}_set"] = has
        else:
            out[key] = _redact_mapping(val)
    return out


def network_public_view(doc: Mapping[str, Any]) -> dict[str, Any]:
    """Copy suitable for UI/API — passwords cleared, *_set flags added."""
    return _redact_mapping(copy.deepcopy(dict(doc)))


def _merge_passwords(existing: Any, incoming: Any) -> Any:
    """Empty password in incoming keeps existing value."""
    if isinstance(existing, list) and isinstance(incoming, list):
        # Merge client networks by index; extras from incoming appended.
        merged: list[Any] = []
        for i, inc in enumerate(incoming):
            prev = existing[i] if i < len(existing) else None
            merged.append(_merge_passwords(prev, inc))
        return merged
    if isinstance(incoming, dict):
        base = dict(existing) if isinstance(existing, dict) else {}
        out = dict(base)
        for key, val in incoming.items():
            if str(key).endswith("_set"):
                continue
            if str(key).lower() in _PASSWORD_KEYS:
                text = "" if val is None else str(val)
                if text.strip():
                    out[key] = text
                elif key not in out:
                    out[key] = ""
                # else keep existing
            elif isinstance(val, (dict, list)):
                out[key] = _merge_passwords(base.get(key), val)
            else:
                out[key] = val
        return out
    return incoming


def write_network_doc(
    paths: ConfigPaths,
    incoming: Mapping[str, Any],
    *,
    merge_secrets: bool = True,
) -> Path:
    ensure_layout(paths)
    current = read_network_doc(paths) if merge_secrets else {}
    if merge_secrets:
        merged = _merge_passwords(current, dict(incoming))
    else:
        merged = dict(incoming)

    if not isinstance(merged.get("network"), dict) and "mode" in merged:
        # allow flat {mode, networks, ...} payload
        boot = merged.pop("boot", current.get("boot", {"network": True}))
        doc = {"boot": boot if isinstance(boot, dict) else {"network": True}, "network": merged}
    else:
        doc = merged

    if "boot" not in doc:
        doc["boot"] = current.get("boot", {"network": True})
    if "network" not in doc or not isinstance(doc["network"], dict):
        raise ValueError("chybí blok network:")

    text = _dump_yaml(doc)
    path = paths.network_yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def schedule_network_apply(config_path: Optional[Path] = None, delay_sec: float = 1.0) -> None:
    """Detach apply so UI gets a response even if Wi-Fi drops."""
    import subprocess

    delay = max(0.3, float(delay_sec))
    cfg_arg = f' "{config_path}"' if config_path else ""
    cmd = (
        f"sleep {delay:.1f}; "
        f"sudo -n /usr/local/sbin/rmodus-network apply{cfg_arg}"
    )
    subprocess.Popen(
        ["bash", "-c", cmd],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
