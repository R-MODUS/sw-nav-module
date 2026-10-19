"""EKF bere jen bloky, které v profilu jsou a mají enabled, type a topic."""

import sys
from pathlib import Path

import yaml

from rmodus_localization.ekf_config import build_ekf_params
from rmodus_localization.profile_params import force_key, load_ros_parameters
from rmodus_localization.sensor_frames import (
    frame_from_topic,
    obstacle_sensor_params,
    resolve_frame,
)

_REPO = Path(__file__).resolve().parents[2]
_BRINGUP = _REPO / "rmodus_bringup"
if str(_BRINGUP) not in sys.path:
    sys.path.insert(0, str(_BRINGUP))

_ODOM_MASK = [
    True, True, False,
    False, False, True,
    True, True, False,
    False, False, True,
    False, False, False,
]
_TWIST_MASK = [
    False, False, False,
    False, False, False,
    True, True, False,
    False, False, False,
    False, False, False,
]


def test_disabled_and_missing_blocks_add_no_odom_or_twist():
    disabled = build_ekf_params(
        {
            "wheel_odom": {"enabled": False, "type": "odom", "topic": "/odom"},
            "flow_sensor": {"enabled": False, "type": "twist", "topic": "/visual_flow/data"},
            "imu": {"enabled": True, "type": "imu", "topic": "/imu/data"},
        }
    )
    assert "odom0" not in disabled
    assert "twist0" not in disabled
    assert disabled["imu0"] == "/imu/data"

    missing = build_ekf_params(
        {"imu": {"enabled": True, "type": "imu", "topic": "/imu/data"}}
    )
    assert "odom0" not in missing
    assert "twist0" not in missing
    assert missing.get("odom0") != "/odom"
    assert missing.get("twist0") != "/visual_flow/data"


def test_enabled_block_adds_its_topic():
    ekf = build_ekf_params(
        {
            "wheel_odom": {"enabled": True, "type": "odom", "topic": "/odom"},
            "lidar_odom": {"enabled": True, "type": "odom", "topic": "/odom_lidar"},
            "flow_sensor": {"enabled": True, "type": "twist", "topic": "/visual_flow/data"},
        }
    )
    assert ekf["odom0"] == "/odom"
    assert ekf["odom1"] == "/odom_lidar"
    assert ekf["twist0"] == "/visual_flow/data"
    assert ekf["odom0_config"] == _ODOM_MASK
    assert ekf["odom1_config"] == _ODOM_MASK
    assert ekf["twist0_config"] == _TWIST_MASK
    assert ekf["base_link_frame"] == "base_footprint"
    assert ekf["world_frame"] == "odom"
    assert ekf["odom_frame"] == "odom"
    assert ekf["map_frame"] == "map"
    assert ekf["publish_tf"] is True
    assert ekf["two_d_mode"] is True


def test_block_without_type_or_topic_is_skipped():
    ekf = build_ekf_params(
        {
            "wheel_odom": {"enabled": True, "topic": "/odom"},
            "flow_sensor": {"enabled": True, "type": "twist"},
        }
    )
    assert "odom0" not in ekf
    assert "twist0" not in ekf


def test_launch_defaults_use_bringup_profile():
    launch = (_REPO / "rmodus_localization" / "launch" / "localization.launch.py").read_text(
        encoding="utf-8"
    )
    ekf = (_REPO / "rmodus_localization" / "launch" / "ekf_dynamic.launch.py").read_text(
        encoding="utf-8"
    )
    assert "default_robot_config.yaml" not in launch
    assert "default_robot_config.yaml" not in ekf
    assert 'FindPackageShare("rmodus_bringup"), "config", "rmodus.yaml"' in launch
    assert 'DeclareLaunchArgument("global_params_file", default_value="")' in launch


def test_stock_profile_fuses_wheel_imu_and_flow_only():
    from rmodus_bringup.profile_compile import compile_profile

    source = _REPO / "rmodus_bringup" / "config" / "rmodus.yaml"
    result = compile_profile(str(source))
    params = load_ros_parameters(result.path)
    assert "lidar_odom" not in params
    assert "map" in params
    ekf = build_ekf_params(params)
    assert ekf["odom0"] == "/odom"
    assert "odom1" not in ekf
    assert ekf["imu0"] == "/imu/data"
    assert ekf["twist0"] == "/visual_flow/data"


def test_compiled_profile_does_not_restore_disabled_inputs(tmp_path):
    from rmodus_bringup.profile_compile import compile_profile

    text = """
bringup:
  chassis: false
  bumper: false
  cliff: false
  flow: false
  display: false
  cmd_mux: false
wheel_odom:
  enabled: false
  type: odom
  topic: /odom
flow_sensor:
  enabled: false
  type: twist
  topic: /visual_flow/data
lidar_odom:
  enabled: false
  type: odom
  topic: /odom_lidar
imu:
  enabled: true
  type: imu
  topic: /imu/data
"""
    source = tmp_path / "ekf_robot.yaml"
    source.write_text(text, encoding="utf-8")
    result = compile_profile(str(source))
    params = load_ros_parameters(result.path)
    assert "wheel_odom" not in params
    assert "flow_sensor" not in params
    assert "lidar_odom" not in params
    ekf = build_ekf_params(params)
    assert "odom0" not in ekf
    assert "twist0" not in ekf
    assert ekf["imu0"] == "/imu/data"


def test_slam_use_sim_time_follows_the_argument_not_the_file():
    source = _REPO / "rmodus_localization" / "config" / "slam_params.yaml"
    document = yaml.safe_load(source.read_text(encoding="utf-8"))
    assert document["slam_toolbox"]["ros__parameters"]["use_sim_time"] is True
    rewritten = force_key(document, "use_sim_time", False)
    assert rewritten["slam_toolbox"]["ros__parameters"]["use_sim_time"] is False
    assert document["slam_toolbox"]["ros__parameters"]["use_sim_time"] is True


def test_stock_bumper_and_cliff_frames():
    root = yaml.safe_load((_REPO / "rmodus_bringup" / "config" / "rmodus.yaml").read_text(encoding="utf-8"))
    params = root["/**"]["ros__parameters"]
    spec = obstacle_sensor_params(params)
    bumpers = dict(item.split(":", 1) for item in spec["bumper_topic_frames"])
    cliffs = dict(item.split(":", 1) for item in spec["range_topic_frames"])
    assert bumpers["/bumper/front"] == "front_contact"
    assert cliffs["/cliff/fl"] == "fl_beam"
    assert cliffs["/cliff/fr"] == "fr_beam"
    assert "/range/sensor_0" not in spec["range_topics"]
    assert resolve_frame("front_contact", "/bumper/front", {}, "bumper") == "front_contact"
    assert resolve_frame("", "/bumper/front", bumpers, "bumper") == "front_contact"
    assert resolve_frame("", "/cliff/fl", {}, "range") == "fl_beam"
    assert frame_from_topic("/cliff/fl", "range") == "fl_beam"
    assert frame_from_topic("/bumper/front", "bumper") == "front_contact"
    assert "cliff_sensor_" not in frame_from_topic("/cliff/front_left", "range")
    assert frame_from_topic("/cliff/front_left", "range") == "fl_beam"


def test_obstacle_cloud_without_sensor_blocks_invents_nothing():
    spec = obstacle_sensor_params({})
    assert spec["bumper_topics"] == []
    assert spec["range_topics"] == []
    assert spec["has_sensors"] is False
    off = obstacle_sensor_params(
        {
            "bumpers": {
                "enabled": False,
                "items": [{"name": "front", "enabled": True, "topic": "/bumper/front"}],
            },
            "cliff_sensors": {
                "enabled": False,
                "items": [{"name": "fl", "enabled": True, "topic": "/cliff/fl"}],
            },
        }
    )
    assert off["has_sensors"] is False
