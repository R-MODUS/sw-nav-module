"""Filesystem store for R-MODUS profiles, active pointer, and network.yaml.

Used by rmodus_config node_manager (ROS services) and CLI.
Boot resolve je v rmodus_entrypoint.sh (configs/active → profiles/<name>.yaml).
Default layout under ~/rmodus/configs/ (override via paths.yaml / env RMODUS_CONFIGS).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def default_configs_root() -> Path:
    env = (os.environ.get("RMODUS_CONFIGS") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / "rmodus" / "configs").resolve()


@dataclass(frozen=True)
class ConfigPaths:
    root: Path
    profiles_dir: Path
    active_file: Path
    network_yaml: Path

    @classmethod
    def from_root(cls, root: Optional[Path | str] = None) -> "ConfigPaths":
        if root is None:
            base = default_configs_root()
        else:
            base = Path(root).expanduser().resolve()
        return cls(
            root=base,
            profiles_dir=base / "profiles",
            active_file=base / "active",
            network_yaml=base / "network.yaml",
        )

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, Any], *, fallback_root: Optional[Path] = None
    ) -> "ConfigPaths":
        """Build paths from rmodus_config package config (paths.yaml)."""

        def _nonempty(key_a: str, key_b: str = "") -> str:
            for key in (key_a, key_b):
                if not key:
                    continue
                val = data.get(key)
                if val is None:
                    continue
                s = str(val).strip()
                if s:
                    return s
            return ""

        root = _nonempty("configs_root", "root")
        if root:
            base = Path(root).expanduser()
        else:
            base = fallback_root or default_configs_root()
        base = base.resolve()
        profiles = _nonempty("profiles_dir", "profiles")
        active = _nonempty("active_file", "active")
        network = _nonempty("network_yaml", "network")
        return cls(
            root=base,
            profiles_dir=Path(profiles).expanduser().resolve()
            if profiles
            else (base / "profiles"),
            active_file=Path(active).expanduser().resolve()
            if active
            else (base / "active"),
            network_yaml=Path(network).expanduser().resolve()
            if network
            else (base / "network.yaml"),
        )


def load_paths_file(path: Path) -> ConfigPaths:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        doc = yaml.safe_load(text) or {}
    except Exception:
        doc = {}
    block = doc.get("/**", doc)
    if isinstance(block, dict) and "ros__parameters" in block:
        params = block.get("ros__parameters") or {}
        if isinstance(params, dict) and "rmodus_config" in params:
            return ConfigPaths.from_mapping(params["rmodus_config"])
        if isinstance(params, dict):
            return ConfigPaths.from_mapping(params)
    if isinstance(doc, dict) and "rmodus_config" in doc:
        return ConfigPaths.from_mapping(doc["rmodus_config"])
    if isinstance(doc, dict):
        return ConfigPaths.from_mapping(doc)
    return ConfigPaths.from_root()


def validate_profile_name(name: str) -> str:
    n = (name or "").strip()
    if n.endswith(".yaml"):
        n = n[: -len(".yaml")]
    if n.endswith(".yml"):
        n = n[: -len(".yml")]
    if not n or not _NAME_RE.match(n):
        raise ValueError(f"neplatné jméno profilu: {name!r}")
    return n


def list_profiles(paths: ConfigPaths) -> list[str]:
    d = paths.profiles_dir
    if not d.is_dir():
        return []
    names: list[str] = []
    for p in sorted(d.iterdir()):
        if p.is_file() and p.suffix in (".yaml", ".yml"):
            names.append(p.stem)
    return names


def profile_path(paths: ConfigPaths, name: str) -> Path:
    n = validate_profile_name(name)
    yaml_p = paths.profiles_dir / f"{n}.yaml"
    if yaml_p.is_file():
        return yaml_p
    yml_p = paths.profiles_dir / f"{n}.yml"
    if yml_p.is_file():
        return yml_p
    return yaml_p


def read_active_name(paths: ConfigPaths) -> Optional[str]:
    if not paths.active_file.is_file():
        return None
    raw = paths.active_file.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    line = raw.splitlines()[0].split("#", 1)[0].strip()
    if not line:
        return None
    return validate_profile_name(line)


def resolve_active_profile(paths: ConfigPaths) -> Path:
    name = read_active_name(paths)
    if not name:
        raise FileNotFoundError(f"chybí active pointer: {paths.active_file}")
    path = profile_path(paths, name)
    if not path.is_file():
        raise FileNotFoundError(f"aktivní profil '{name}' neexistuje: {path}")
    return path


def set_active(paths: ConfigPaths, name: str) -> Path:
    n = validate_profile_name(name)
    path = profile_path(paths, n)
    if not path.is_file():
        raise FileNotFoundError(f"profil neexistuje: {path}")
    paths.active_file.parent.mkdir(parents=True, exist_ok=True)
    paths.active_file.write_text(n + "\n", encoding="utf-8")
    return path


def ensure_layout(paths: ConfigPaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.profiles_dir.mkdir(parents=True, exist_ok=True)


def read_profile_text(paths: ConfigPaths, name: str) -> str:
    path = profile_path(paths, name)
    if not path.is_file():
        raise FileNotFoundError(f"profil neexistuje: {path}")
    return path.read_text(encoding="utf-8")


def write_profile_text(paths: ConfigPaths, name: str, text: str) -> Path:
    """Overwrite an existing profile, or create ``<name>.yaml`` if missing."""
    n = validate_profile_name(name)
    ensure_layout(paths)
    _validate_yaml_text(text)
    path = profile_path(paths, n)
    if not path.is_file():
        path = paths.profiles_dir / f"{n}.yaml"
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return path


def create_profile(
    paths: ConfigPaths,
    name: str,
    *,
    source: Optional[str] = None,
    content: Optional[str] = None,
) -> Path:
    """Create a new profile from ``content``, copy of ``source``, or active/minimal stub.

    Copies preserve source YAML text (comments) — no round-trip dump.
    """
    n = validate_profile_name(name)
    ensure_layout(paths)
    dest = paths.profiles_dir / f"{n}.yaml"
    existing_yml = paths.profiles_dir / f"{n}.yml"
    if dest.is_file() or existing_yml.is_file():
        raise FileExistsError(f"profil už existuje: {n}")

    if content is not None:
        text = content
    elif source:
        text = read_profile_text(paths, source)
    else:
        active = read_active_name(paths)
        if active:
            text = read_profile_text(paths, active)
        else:
            text = _minimal_profile_text(n)

    _validate_yaml_text(text)
    dest.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return dest


def delete_profile(paths: ConfigPaths, name: str, *, allow_active: bool = False) -> None:
    n = validate_profile_name(name)
    if not allow_active and read_active_name(paths) == n:
        raise ValueError("nelze smazat aktivní profil — nejdřív aktivuj jiný")
    path = profile_path(paths, n)
    if not path.is_file():
        raise FileNotFoundError(f"profil neexistuje: {path}")
    path.unlink()


def configs_root_from_profile_file(profile: Path) -> Optional[Path]:
    """If ``…/configs/profiles/foo.yaml``, return ``…/configs``; else None."""
    p = Path(profile).expanduser().resolve()
    if p.parent.name == "profiles":
        return p.parent.parent
    return None


def _validate_yaml_text(text: str) -> None:
    try:
        import yaml  # type: ignore

        yaml.safe_load(text)
    except ImportError:
        return
    except Exception as exc:
        raise ValueError(f"neplatný YAML: {exc}") from exc


def _minimal_profile_text(name: str) -> str:
    return (
        f"meta:\n"
        f"  source: {name}\n"
        f"  title: {name}\n"
        f"  last_used: \"\"\n"
        f"  copied_at: \"\"\n"
        f"\n"
        f"boot:\n"
        f"  rmodus: true\n"
        f"\n"
        f"web:\n"
        f"  testing: true\n"
        f"  host: \"0.0.0.0\"\n"
        f"  port: 8080\n"
        f"\n"
        f"bringup:\n"
        f"  web: true\n"
        f"\n"
        f"/**:\n"
        f"  ros__parameters: {{}}\n"
    )
