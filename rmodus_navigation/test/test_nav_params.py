"""Nav2 parametry ze stock profilu: obdélník, mecanum, scan, use_sim_time."""

from pathlib import Path

import yaml

from rmodus_navigation.nav_params import (
    apply_robot_profile,
    footprint_from_size,
    navigation_sources,
    ros_parameters,
)

_REPO = Path(__file__).resolve().parents[2]


def _stock():
    robot = yaml.safe_load(
        (_REPO / "rmodus_bringup" / "config" / "rmodus.yaml").read_text(encoding="utf-8")
    )
    nav = yaml.safe_load(
        (_REPO / "rmodus_navigation" / "config" / "nav2_params.yaml").read_text(encoding="utf-8")
    )
    return ros_parameters(robot), nav


def _follow(nav):
    return nav["controller_server"]["ros__parameters"]["FollowPath"]


def _local(nav):
    return nav["local_costmap"]["local_costmap"]["ros__parameters"]


def _global(nav):
    return nav["global_costmap"]["global_costmap"]["ros__parameters"]


def test_stock_profile_is_rectangle_mecanum_and_scan():
    robot, nav = _stock()
    out = apply_robot_profile(nav, robot, use_sim_time=False)
    local = _local(out)
    follow = _follow(out)
    assert "robot_radius" not in local
    assert "robot_radius" not in _global(out)
    assert local["footprint"] == footprint_from_size(robot["base_link"]["size"])
    assert "0.2500" in local["footprint"]
    assert "0.0973" not in local["footprint"]
    assert follow["max_vel_y"] > 0
    assert follow["vy_samples"] > 1
    assert follow["acc_lim_y"] != 0
    assert follow["max_vel_x"] == 0.5
    assert follow["max_vel_theta"] == 0.7
    assert local["voxel_layer"]["scan"]["topic"] == "/scan"
    assert _global(out)["obstacle_layer"]["scan"]["topic"] == "/scan"
    assert out["amcl"]["ros__parameters"]["scan_topic"] == "/scan"
    assert out["amcl"]["ros__parameters"]["base_frame_id"] == "base_footprint"
    assert out["amcl"]["ros__parameters"]["odom_frame_id"] == "odom"
    assert out["amcl"]["ros__parameters"]["global_frame_id"] == "map"
    assert out["amcl"]["ros__parameters"]["use_sim_time"] is False
    assert local["voxel_layer"]["obstacle_cloud"]["topic"] == "/sensors/combined_cloud"
    assert _global(out)["obstacle_layer"]["obstacle_cloud_map"]["topic"] == "/sensors/combined_cloud_map"
    assert out["velocity_smoother"]["ros__parameters"]["max_velocity"][1] > 0


def test_diff_modes_have_no_lateral_velocity():
    robot, nav = _stock()
    for mode in ("diff2", "diff4"):
        robot["drive"]["mode"] = mode
        out = apply_robot_profile(nav, robot, use_sim_time=False)
        follow = _follow(out)
        assert follow["max_vel_y"] == 0.0
        assert follow["vy_samples"] == 1
        assert follow["acc_lim_y"] == 0.0
        assert follow["decel_lim_y"] == 0.0
        assert out["velocity_smoother"]["ros__parameters"]["max_velocity"][1] == 0.0


def test_missing_wheel_limits_keep_defaults():
    robot, nav = _stock()
    del robot["drive"]["wheel_radius"]
    del robot["drive"]["max_wheel_speed"]
    follow = _follow(apply_robot_profile(nav, robot, use_sim_time=False))
    assert follow["max_vel_x"] == 0.5
    assert follow["max_vel_theta"] == 0.7


def test_missing_lidar_topic_falls_back_to_scan():
    robot, nav = _stock()
    del robot["lidar"]
    out = apply_robot_profile(nav, robot, use_sim_time=True)
    assert _local(out)["voxel_layer"]["scan"]["topic"] == "/scan"
    assert out["controller_server"]["ros__parameters"]["use_sim_time"] is True


def test_map_sources_are_never_both():
    assert navigation_sources(True, "/tmp/map.yaml", True) == {
        "start_amcl": False,
        "start_navigate": True,
        "reason": "slam",
    }
    assert navigation_sources(False, "/tmp/map.yaml", True)["start_amcl"] is True
    assert navigation_sources(False, "/tmp/map.yaml", True)["start_navigate"] is True
    empty = navigation_sources(False, "", False)
    assert empty["start_amcl"] is False
    assert empty["start_navigate"] is False
    missing = navigation_sources(False, "/tmp/no-such-map.yaml", False)
    assert missing["start_amcl"] is False
    assert missing["start_navigate"] is False


def test_velocity_output_stays_on_nav_cmd_vel():
    launch = (_REPO / "rmodus_navigation" / "launch" / "nav2.launch.py").read_text(encoding="utf-8")
    parent = (_REPO / "rmodus_navigation" / "launch" / "navigation.launch.py").read_text(encoding="utf-8")
    assert 'default_value="/nav/cmd_vel"' in launch
    assert 'default_value="/nav/cmd_vel"' in parent
    assert '("cmd_vel_smoothed", cmd_vel_topic)' in launch
    assert 'cmd_vel_smoothed", "/cmd_vel"' not in launch
