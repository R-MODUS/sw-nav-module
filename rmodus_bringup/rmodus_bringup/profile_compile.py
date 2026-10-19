"""Kontrola a složení uživatelského profilu do dočasného ROS YAML.

Uživatelský soubor se nemění. Výstup je /tmp/rmodus/<kmen>.ros.yaml
s kořenovými ROOT_KEYS a zbytkem pod /**/ros__parameters.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from typing import NamedTuple

import yaml

from rmodus_bringup.profile_schema import (
    BRINGUP_PAIRS,
    DEFAULT_BRINGUP,
    ITEM_BLOCKS,
    ITEM_FIELDS,
    ITEM_OPTIONAL_VECTORS,
    ITEM_REQUIRED_VECTORS,
    ITEM_SIZE_LEN,
    ITEM_VECTOR_LEN,
    NAME_RE,
    PARAM_ALIASES,
    PARAM_BLOCKS,
    REQUIRED_ROOT,
    REQUIRED_WHEN,
    ROOT_KEYS,
    SIM_IGNORES_HARDWARE,
)

COMPILED_DIR = "/tmp/rmodus"
_ROS_KEY = "/**"
_PARAMS_KEY = "ros__parameters"
_NAME_RE = re.compile(NAME_RE)
_ITEM_FIELDS = frozenset(ITEM_FIELDS)
_KNOWN_PARAMS = frozenset(PARAM_BLOCKS) | frozenset(PARAM_ALIASES)
_DROP = object()

# Věty k BRINGUP_PAIRS. Seznam párů je v profile_schema.
_PAIR_NODE = {
    "bumper": "rmodus_bumper",
    "cliff": "rmodus_cliff_sensor",
    "flow": "rmodus_flow_sensor",
    "display": "rmodus_display",
    "cmd_mux": "cmd_mux",
}
_PAIR_MISSING = {
    "bumper": "žádný nárazník",
    "cliff": "žádný cliff senzor",
    "flow": "žádný flow senzor",
    "display": "žádný displej",
    "cmd_mux": "žádný cmd_mux",
}


class ProfileError(Exception):
    """Profil má chyby. Nic se nezapisuje."""

    def __init__(self, errors: list):
        self.errors = [dict(item) for item in errors]
        self.sentences = []
        for item in self.errors:
            path = str(item.get("path") or "").strip()
            message = str(item.get("message") or "").strip()
            self.sentences.append(f"{path}: {message}" if path else message)
        super().__init__("\n".join(self.sentences))


class CompileResult(NamedTuple):
    path: str
    warnings: list


def _issue(path: str, message: str) -> dict:
    return {"path": path, "message": message}


def _as_bool(value) -> bool:
    """Stejné čtení jako v launchi. bool('false') je v Pythonu True."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "y")


def _disabled(mapping) -> bool:
    return isinstance(mapping, dict) and "enabled" in mapping and not _as_bool(mapping["enabled"])


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _flag_on(bringup: dict, flag: str) -> bool:
    if flag not in bringup:
        return bool(DEFAULT_BRINGUP.get(flag, False))
    return _as_bool(bringup[flag])


def _split(loaded: dict) -> tuple:
    """Kořenové klíče a parametry. Obal /** se rozbalí, ať se při zápisu nezdvojí."""
    errors = []
    wrapped = None
    if _ROS_KEY in loaded:
        block = loaded.get(_ROS_KEY)
        if not isinstance(block, dict):
            errors.append(_issue(_ROS_KEY, "/** musí být mapa"))
            wrapped = {}
        else:
            inner = block.get(_PARAMS_KEY, {})
            if inner is None:
                inner = {}
            if not isinstance(inner, dict):
                errors.append(_issue(f"{_ROS_KEY}.{_PARAMS_KEY}", "ros__parameters musí být mapa"))
                wrapped = {}
            else:
                wrapped = dict(inner)

    roots = {}
    params = {}
    if wrapped is not None:
        params.update(wrapped)
        for key, value in loaded.items():
            if key == _ROS_KEY:
                continue
            if key in ROOT_KEYS:
                roots[key] = value
            elif key not in params:
                params[key] = value
    else:
        for key, value in loaded.items():
            if key in ROOT_KEYS:
                roots[key] = value
            else:
                params[key] = value
    return roots, params, errors


def _bringup_dict(roots: dict, errors: list) -> dict:
    for key in REQUIRED_ROOT:
        if key not in roots:
            errors.append(_issue(key, f"chybí povinný blok {key}"))
    bringup = roots.get("bringup")
    if "bringup" in roots and not isinstance(bringup, dict):
        errors.append(_issue("bringup", "bringup musí být mapa"))
        return {}
    if not isinstance(bringup, dict):
        return {}
    return bringup


def _check_required(bringup: dict, params: dict, errors: list) -> None:
    for flag, blocks in REQUIRED_WHEN.items():
        if not _flag_on(bringup, flag):
            continue
        for block in blocks:
            if block not in params:
                errors.append(_issue(block, f"bringup.{flag} je zapnutý, chybí {block}"))


def _check_unknown_params(params: dict, warnings: list) -> None:
    for key in params:
        if key in _KNOWN_PARAMS:
            continue
        warnings.append(_issue(key, f"neznámý klíč {key}"))


def _check_vector(item: dict, field: str, path: str, errors: list, required: bool) -> None:
    if field not in item:
        if required:
            errors.append(_issue(f"{path}.{field}", f"chybí {field}"))
        return
    value = item[field]
    ok = (
        isinstance(value, list)
        and len(value) == ITEM_VECTOR_LEN
        and all(_is_number(part) for part in value)
    )
    if not ok:
        errors.append(_issue(f"{path}.{field}", f"{field} musí být seznam {ITEM_VECTOR_LEN} čísel"))


def _remember(seen: dict, value, path: str, label: str, errors: list) -> None:
    if value in seen:
        errors.append(_issue(path, f"duplicitní {label} {value}"))
        return
    seen[value] = path


def _identity_text(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _take_identity(node: dict, field: str, path: str, seen: dict, errors: list) -> None:
    text = _identity_text(node.get(field))
    if not text:
        return
    field_path = f"{path}.{field}" if path else field
    _remember(seen, text, field_path, field, errors)


def _walk_identities(node, path: str, names: dict, frames: dict, errors: list) -> None:
    """Každé name a frame_id v profilu je jedinečné. Vypnutá mapa se nepočítá."""
    if isinstance(node, dict):
        if _disabled(node):
            return
        _take_identity(node, "name", path, names, errors)
        _take_identity(node, "frame_id", path, frames, errors)
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            _walk_identities(value, child, names, frames, errors)
        return
    if isinstance(node, list):
        for index, item in enumerate(node):
            _walk_identities(item, f"{path}[{index}]", names, frames, errors)


def _check_unique_identities(roots: dict, params: dict, errors: list) -> None:
    names = {}
    frames = {}
    _walk_identities(roots, "", names, frames, errors)
    _walk_identities(params, "", names, frames, errors)


def _check_items(params: dict, errors: list, warnings: list) -> None:
    for block_name in ITEM_BLOCKS:
        block = params.get(block_name)
        if not isinstance(block, dict) or "items" not in block:
            continue
        items = block.get("items")
        if not isinstance(items, list):
            errors.append(_issue(f"{block_name}.items", "items musí být seznam"))
            continue
        names = {}
        topics = {}
        pins = {}
        size_len = ITEM_SIZE_LEN.get(block_name, ITEM_VECTOR_LEN)
        for index, item in enumerate(items):
            path = f"{block_name}.items[{index}]"
            if not isinstance(item, dict):
                errors.append(_issue(path, "položka musí být mapa"))
                continue
            for key in item:
                if key not in _ITEM_FIELDS:
                    warnings.append(_issue(f"{path}.{key}", f"neznámý klíč {key}"))
            if _disabled(item):
                continue
            name = item.get("name")
            if not isinstance(name, str) or _NAME_RE.fullmatch(name) is None:
                errors.append(_issue(f"{path}.name", f"name musí být řetězec podle {NAME_RE}"))
            else:
                _remember(names, name, f"{path}.name", "name", errors)
            topic = item.get("topic")
            if not isinstance(topic, str) or not topic.startswith("/"):
                errors.append(_issue(f"{path}.topic", "topic musí být řetězec začínající na /"))
            else:
                _remember(topics, topic, f"{path}.topic", "topic", errors)
            pin = item.get("pin")
            if isinstance(pin, bool) or not isinstance(pin, int):
                errors.append(_issue(f"{path}.pin", "pin musí být celé číslo"))
            else:
                _remember(pins, pin, f"{path}.pin", "pin", errors)
            size = item.get("size")
            size_ok = (
                isinstance(size, list)
                and len(size) == size_len
                and all(_is_number(part) for part in size)
            )
            if not size_ok:
                errors.append(_issue(f"{path}.size", f"size musí být seznam {size_len} čísel"))
            for field in ITEM_REQUIRED_VECTORS:
                _check_vector(item, field, path, errors, True)
            for field in ITEM_OPTIONAL_VECTORS:
                _check_vector(item, field, path, errors, False)


def _block_active(block_name: str, block) -> bool:
    if not isinstance(block, dict) or _disabled(block):
        return False
    if block_name not in ITEM_BLOCKS:
        return True
    items = block.get("items")
    if not isinstance(items, list):
        return False
    return any(isinstance(item, dict) and not _disabled(item) for item in items)


def _check_pairs(bringup: dict, params: dict, warnings: list) -> None:
    for flag, block_name in BRINGUP_PAIRS:
        flag_on = _flag_on(bringup, flag)
        block = params.get(block_name)
        active = _block_active(block_name, block)
        node = _PAIR_NODE.get(flag, flag)
        if active and not flag_on:
            if block_name in ITEM_BLOCKS:
                message = (
                    f"{block_name} má zapnuté položky, ale bringup.{flag} je false, "
                    f"{node} se nespustí"
                )
            else:
                message = (
                    f"{block_name} je zapnutý, ale bringup.{flag} je false, "
                    f"{node} se nespustí"
                )
            warnings.append(_issue(f"bringup.{flag}", message))
            continue
        if flag_on and not active:
            if isinstance(block, dict) and _disabled(block):
                message = (
                    f"bringup.{flag} je true, ale {block_name} je vypnutý (enabled: false)"
                )
                warnings.append(_issue(f"{block_name}.enabled", message))
            else:
                missing = _PAIR_MISSING.get(flag, f"žádný {block_name}")
                warnings.append(
                    _issue(f"bringup.{flag}", f"bringup.{flag} je true, v profilu není {missing}")
                )


def _check_sim(bringup: dict, params: dict, warnings: list) -> None:
    if not _flag_on(bringup, "sim"):
        return
    for name in SIM_IGNORES_HARDWARE:
        block = params.get(name)
        if not isinstance(block, dict) or _disabled(block):
            continue
        if "hardware" in block and _as_bool(block["hardware"]):
            warnings.append(
                _issue(f"{name}.hardware", "v simulaci se hardware přepne na false")
            )


def lint_profile(text: str) -> dict:
    """Kontrola textu. Nic nezapisuje. Neplatný YAML je jedna chyba a konec."""
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return {"errors": [_issue("", f"YAML nejde přečíst: {exc}")], "warnings": []}
    if not isinstance(loaded, dict):
        return {"errors": [_issue("", "kořen profilu musí být mapa")], "warnings": []}

    errors = []
    warnings = []
    roots, params, split_errors = _split(loaded)
    errors.extend(split_errors)
    bringup = _bringup_dict(roots, errors)
    _check_required(bringup, params, errors)
    _check_unknown_params(params, warnings)
    _check_unique_identities(roots, params, errors)
    _check_items(params, errors, warnings)
    _check_pairs(bringup, params, warnings)
    _check_sim(bringup, params, warnings)
    return {"errors": errors, "warnings": warnings}


def _strip(node):
    """Rekurzivně vyhodí mapy s enabled: false. Prázdné items smažou i rodiče."""
    if isinstance(node, dict):
        if _disabled(node):
            return _DROP
        out = {}
        for key, value in node.items():
            stripped = _strip(value)
            if stripped is _DROP:
                continue
            out[key] = stripped
        if "items" in node and isinstance(node.get("items"), list):
            left = out.get("items")
            if not isinstance(left, list) or len(left) == 0:
                return _DROP
        return out
    if isinstance(node, list):
        out = []
        for item in node:
            stripped = _strip(item)
            if stripped is _DROP:
                continue
            out.append(stripped)
        return out
    return node


def _strip_tree(node: dict) -> dict:
    stripped = _strip(node)
    if stripped is _DROP or not isinstance(stripped, dict):
        return {}
    return stripped


def _compose(roots: dict, params: dict) -> dict:
    document = {}
    for key in ROOT_KEYS:
        if key in roots:
            document[key] = roots[key]
    document[_ROS_KEY] = {_PARAMS_KEY: params}
    return document


def _output_path(source_path: str) -> str:
    stem = os.path.splitext(os.path.basename(os.path.abspath(source_path)))[0]
    return os.path.join(COMPILED_DIR, f"{stem}.ros.yaml")


def _write_compiled(path: str, text: str) -> None:
    os.makedirs(COMPILED_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".ros-", suffix=".tmp", dir=COMPILED_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def compile_profile(source_path: str) -> CompileResult:
    """Načte soubor, zkontroluje ho a zapíše dočasný ROS YAML.

    Při chybách vyhodí ProfileError a nic nezapíše. Varování jsou na výsledku.
    """
    try:
        with open(source_path, "r", encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeError) as exc:
        raise ProfileError([_issue("", f"soubor nejde přečíst: {exc}")]) from exc

    report = lint_profile(text)
    if report["errors"]:
        raise ProfileError(report["errors"])

    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ProfileError([_issue("", "kořen profilu musí být mapa")])
    roots, params, _split_errors = _split(loaded)
    document = _compose(_strip_tree(roots), _strip_tree(params))
    payload = yaml.safe_dump(
        document,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    out_path = _output_path(source_path)
    _write_compiled(out_path, payload)
    return CompileResult(out_path, list(report["warnings"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Složí dočasný ROS profil z uživatelského YAML."
    )
    parser.add_argument("--input", required=True, help="Cesta k uživatelskému YAML profilu")
    args = parser.parse_args(argv)
    try:
        result = compile_profile(args.input)
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for warning in result.warnings:
        where = str(warning.get("path") or "").strip()
        message = str(warning.get("message") or "").strip()
        print(f"{where}: {message}" if where else message, file=sys.stderr)
    print(result.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
