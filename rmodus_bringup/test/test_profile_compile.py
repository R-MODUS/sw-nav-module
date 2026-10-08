"""pytest bez ROS: složení profilu a lint."""

import os
from pathlib import Path

import yaml

from rmodus_bringup.profile_compile import (
    COMPILED_DIR,
    ProfileError,
    compile_profile,
    lint_profile,
)
from rmodus_bringup.profile_schema import PARAM_ALIASES, PARAM_BLOCKS

_QUIET_FLAGS = {
    "chassis": False,
    "bumper": False,
    "cliff": False,
    "flow": False,
    "display": False,
    "cmd_mux": False,
}


def _bringup(**flags) -> str:
    merged = dict(_QUIET_FLAGS)
    merged.update(flags)
    lines = ["bringup:"]
    for key, value in merged.items():
        lines.append(f"  {key}: {'true' if value else 'false'}")
    return "\n".join(lines) + "\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _load_compiled(result) -> dict:
    return yaml.safe_load(Path(result.path).read_text(encoding="utf-8"))


def _params(doc: dict) -> dict:
    assert "/**" in doc
    block = doc["/**"]
    assert isinstance(block, dict)
    params = block["ros__parameters"]
    assert isinstance(params, dict)
    assert "/**" not in params
    return params


def test_flat_yaml_wraps_root_keys_and_drops_disabled(tmp_path):
    text = _bringup(chassis=True, bumper=True, cliff=False) + """
web:
  port: 8080
base_link:
  mass: 1
drive:
  enabled: true
imu:
  enabled: false
  topic: /imu
bumpers:
  enabled: true
  items:
    - name: front
      enabled: true
      pin: 0
      topic: /bumper/front
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
    - name: rear
      enabled: false
      pin: 1
      topic: /bumper/rear
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
"""
    source = _write(tmp_path, "flat_robot.yaml", text)
    before = source.read_text(encoding="utf-8")
    result = compile_profile(str(source))
    assert source.read_text(encoding="utf-8") == before
    assert result.warnings == []

    raw = Path(result.path).read_text(encoding="utf-8")
    assert raw.count("ros__parameters:") == 1
    doc = yaml.safe_load(raw)
    assert "bringup" in doc and "web" in doc
    assert list(doc).index("bringup") < list(doc).index("/**")
    assert list(doc).index("web") < list(doc).index("/**")
    assert doc["web"]["port"] == 8080
    assert doc["bringup"]["cliff"] is False
    params = _params(doc)
    assert "bringup" not in params and "web" not in params
    assert params["base_link"]["mass"] == 1
    assert "drive" in params
    assert "imu" not in params
    names = [item["name"] for item in params["bumpers"]["items"]]
    assert names == ["front"]


def test_wrapped_yaml_is_not_doubled(tmp_path):
    text = _bringup(chassis=True) + """
web:
  port: 9
/**:
  ros__parameters:
    base_link:
      mass: 2
    drive:
      enabled: true
"""
    source = _write(tmp_path, "wrapped_robot.yaml", text)
    result = compile_profile(str(source))
    raw = Path(result.path).read_text(encoding="utf-8")
    assert raw.count("ros__parameters:") == 1
    params = _params(yaml.safe_load(raw))
    assert params["base_link"]["mass"] == 2
    assert "drive" in params
    assert "web" not in params

    again = compile_profile(result.path)
    second = Path(again.path).read_text(encoding="utf-8")
    assert second.count("ros__parameters:") == 1
    assert _params(yaml.safe_load(second))["base_link"]["mass"] == 2


def test_disabled_block_warns_before_removal(tmp_path):
    text = _bringup(bumper=True, cliff=False) + """
  extras:
    - enabled: false
      path: /tmp/nope.launch.py
    - enabled: true
      package: demo
      launch: demo.launch.py
bumpers:
  enabled: false
  items:
    - name: front
      enabled: true
      pin: 0
      topic: /bumper/front
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
"""
    source = _write(tmp_path, "disabled_bumper.yaml", text)
    before = source.read_text(encoding="utf-8")
    result = compile_profile(str(source))
    assert source.read_text(encoding="utf-8") == before
    assert any("vypnut" in item["message"] for item in result.warnings)
    doc = _load_compiled(result)
    assert "bumpers" not in _params(doc)
    assert doc["bringup"]["cliff"] is False
    extras = doc["bringup"]["extras"]
    assert len(extras) == 1
    assert extras[0]["package"] == "demo"


def test_duplicate_pin_is_error():
    text = _bringup(bumper=True) + """
bumpers:
  enabled: true
  items:
    - name: front
      enabled: true
      pin: 1
      topic: /bumper/front
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
    - name: side
      enabled: true
      pin: 1
      topic: /bumper/side
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
"""
    report = lint_profile(text)
    pin_errors = [item for item in report["errors"] if "pin" in item["path"] or "pin" in item["message"]]
    assert pin_errors
    assert any("duplicitní pin" in item["message"] for item in pin_errors)


def test_same_name_anywhere_is_error():
    text = _bringup() + """
imu:
  name: front
lidar:
  name: front
microros:
  items:
    - name: board
"""
    report = lint_profile(text)
    name_errors = [item for item in report["errors"] if item["message"] == "duplicitní name front"]
    assert name_errors
    assert name_errors[0]["path"] == "lidar.name"


def test_same_frame_id_anywhere_is_error():
    text = _bringup() + """
imu:
  frame_id: sensor_link
flow_sensor:
  frame_id: sensor_link
"""
    report = lint_profile(text)
    frame_errors = [
        item for item in report["errors"] if item["message"] == "duplicitní frame_id sensor_link"
    ]
    assert frame_errors
    assert frame_errors[0]["path"] == "flow_sensor.frame_id"


def test_disabled_element_name_is_not_duplicate():
    text = _bringup() + """
imu:
  name: front
  frame_id: sensor_link
lidar:
  enabled: false
  name: front
  frame_id: sensor_link
"""
    report = lint_profile(text)
    assert report["errors"] == []


def test_disabled_item_pin_is_not_duplicate():
    text = _bringup(bumper=True) + """
bumpers:
  enabled: true
  items:
    - name: front
      enabled: true
      pin: 3
      topic: /bumper/front
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
    - name: rear
      enabled: false
      pin: 3
      topic: /bumper/rear
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
"""
    report = lint_profile(text)
    assert report["errors"] == []


def test_unknown_key_is_warning():
    text = _bringup() + """
nav_module:
  mass: 1
not_a_block: true
bumpers:
  items:
    - name: front
      enabled: false
      weird: 1
"""
    report = lint_profile(text)
    assert report["errors"] == []
    warned = {item["path"]: item["message"] for item in report["warnings"]}
    assert "not_a_block" in warned
    assert "neznámý klíč" in warned["not_a_block"]
    assert "nav_module" not in warned
    assert any(path.endswith(".weird") for path in warned)


def test_bumper_flag_without_block_is_warning():
    text = _bringup(bumper=True)
    report = lint_profile(text)
    assert report["errors"] == []
    messages = [item["message"] for item in report["warnings"]]
    assert "bringup.bumper je true, v profilu není žádný nárazník" in messages


def test_compile_error_writes_nothing(tmp_path):
    text = _bringup(bumper=True) + """
bumpers:
  enabled: true
  items:
    - name: front
      enabled: true
      pin: 1
      topic: /bumper/front
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
    - name: side
      enabled: true
      pin: 1
      topic: /bumper/side
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
"""
    source = _write(tmp_path, "compile_must_not_write.yaml", text)
    before = source.read_text(encoding="utf-8")
    out = os.path.join(COMPILED_DIR, "compile_must_not_write.ros.yaml")
    os.makedirs(COMPILED_DIR, exist_ok=True)
    sentinel = "SENTINEL\n"
    Path(out).write_text(sentinel, encoding="utf-8")
    try:
        try:
            compile_profile(str(source))
        except ProfileError as exc:
            assert exc.sentences
            assert any("pin" in sentence for sentence in exc.sentences)
        else:
            raise AssertionError("ProfileError nebyla vyhozena")
        assert Path(out).read_text(encoding="utf-8") == sentinel
        assert source.read_text(encoding="utf-8") == before
    finally:
        if os.path.exists(out):
            os.remove(out)


def test_omitted_chassis_requires_base_link_and_drive():
    text = """
bringup:
  bumper: false
  cliff: false
  flow: false
  display: false
  cmd_mux: false
"""
    report = lint_profile(text)
    paths = {item["path"] for item in report["errors"]}
    assert "base_link" in paths
    assert "drive" in paths


def test_invalid_yaml_is_a_single_error():
    report = lint_profile("bringup: [\n")
    assert len(report["errors"]) == 1
    assert report["warnings"] == []
    assert "YAML" in report["errors"][0]["message"]


def test_sim_switches_hardware_off():
    text = _bringup(sim=True) + """
cliff_sensors:
  enabled: true
  hardware: true
  items:
    - name: fl
      enabled: true
      pin: 0
      topic: /cliff/fl
      size: [1, 2, 3]
      mount_offset: [0, 0, 0]
"""
    report = lint_profile(text)
    assert any(
        item["path"] == "cliff_sensors.hardware"
        and item["message"] == "v simulaci se hardware přepne na false"
        for item in report["warnings"]
    )


def test_stock_profile_compiles_once():
    source = Path(__file__).resolve().parents[1] / "config" / "rmodus.yaml"
    before = source.read_text(encoding="utf-8")
    original = yaml.safe_load(before)
    result = compile_profile(str(source))
    assert source.read_text(encoding="utf-8") == before
    raw = Path(result.path).read_text(encoding="utf-8")
    assert raw.count("ros__parameters:") == 1
    doc = yaml.safe_load(raw)
    params = _params(doc)
    assert "base_link" in params and "drive" in params
    assert "lidar_odom" not in params
    known = set(PARAM_BLOCKS) | set(PARAM_ALIASES)
    warned = {item["path"] for item in result.warnings}
    for key in original["/**"]["ros__parameters"]:
        if key not in known:
            assert key in warned
    microros_items = doc["microros"]["items"]
    assert all(item.get("enabled") is not False for item in microros_items)
    assert any(item["name"] == "bumpers" for item in microros_items)
