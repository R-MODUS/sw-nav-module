"""Gazebo twin of the profile robot.

The model is rmodus_description/urdf/robot.urdf.xacro. This launch asks for
continuous wheel joints and the Gazebo plugin overlay, then spawns that URDF.
"""

import os
import tempfile

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    LogInfo,
    OpaqueFunction,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def _resolve(path):
    if path is None:
        return ""
    text = str(path).strip()
    if not text:
        return ""
    return os.path.normpath(os.path.expanduser(text))


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _wants_gui(value):
    """auto: okno jen když proces už vidí displej. true/false bere profil (bringup.sim_gui)."""
    text = str(value or "").strip().lower()
    if text in ("", "auto"):
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    return _as_bool(text, False)


def _gui_env():
    """Extra environment for the gz process only.

    A terminal already has DISPLAY and Wayland; leave that session alone.
    A systemd service has neither. Filling DISPLAY=:0 by itself makes Qt open
    a taskbar icon whose window never maps on WSLg, so prefer the Wayland socket.
    """
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return {}
    env = {}
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not runtime:
        candidate = f"/run/user/{os.getuid()}"
        if os.path.isdir(candidate):
            runtime = candidate
    if runtime:
        env["XDG_RUNTIME_DIR"] = runtime
        bus = os.path.join(runtime, "bus")
        if os.path.exists(bus):
            env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=" + bus
        if os.path.exists(os.path.join(runtime, "wayland-0")):
            env["WAYLAND_DISPLAY"] = os.environ.get("WAYLAND_DISPLAY") or "wayland-0"
    if os.environ.get("DISPLAY") or os.path.exists("/tmp/.X11-unix/X0"):
        env["DISPLAY"] = os.environ.get("DISPLAY") or ":0"
    if os.path.exists("/mnt/wslg/PulseServer"):
        env["PULSE_SERVER"] = "unix:/mnt/wslg/PulseServer"
    # Do not set QT_QPA_PLATFORM. A terminal leaves it unset and gz itself
    # switches Wayland sessions to xcb. Forcing wayland here breaks the window.
    return env


def _load_profile(path):
    with open(path, "r", encoding="utf-8") as handle:
        root = yaml.safe_load(handle) or {}
    if not isinstance(root, dict):
        return {}
    params = (root.get("/**") or {}).get("ros__parameters") or {}
    return params if isinstance(params, dict) else {}


def _items(block):
    if isinstance(block, dict):
        if not _as_bool(block.get("enabled"), False):
            return []
        raw = block.get("items") or []
    elif isinstance(block, list):
        raw = block
    else:
        return []
    return [item for item in raw if isinstance(item, dict) and item.get("name") and _as_bool(item.get("enabled"), True)]


def _topic(block, default):
    if isinstance(block, dict) and str(block.get("topic") or "").strip():
        return str(block["topic"]).strip()
    return default


def _cmd_topic(params):
    mux = params.get("cmd_mux")
    if isinstance(mux, dict) and str(mux.get("output_topic") or "").strip():
        return str(mux["output_topic"]).strip()
    return "/cmd_vel"


def _teleop_output(params, drive_topic):
    """ROS topic fed by the GUI card.

    With cmd_mux the card must enter as the teleop input. Publishing straight
    onto the drive topic would fight the mux, which is the only /cmd_vel source.
    """
    mux = params.get("cmd_mux")
    if isinstance(mux, dict) and not _as_bool(mux.get("enabled"), True):
        return drive_topic
    if isinstance(mux, dict):
        for item in mux.get("inputs") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("name") or "").strip() != "teleop":
                continue
            if not _as_bool(item.get("enabled"), True):
                continue
            topic = str(item.get("topic") or "").strip()
            if topic:
                return topic
    return "/teleop/cmd_vel"


def _bridge(ros_topic, gz_topic, ros_type, gz_type, direction):
    return {
        "ros_topic_name": ros_topic,
        "gz_topic_name": gz_topic,
        "ros_type_name": ros_type,
        "gz_type_name": gz_type,
        "direction": direction,
    }


def _write_bridge(params, gui_cmd_topic=""):
    cmd_topic = _cmd_topic(params)
    odom_topic = _topic(params.get("wheel_odom"), "/odom")
    imu = params.get("imu") if isinstance(params.get("imu"), dict) else {}
    lidar = params.get("lidar") if isinstance(params.get("lidar"), dict) else {}

    bridge = [
        _bridge("/clock", "/clock", "rosgraph_msgs/msg/Clock", "gz.msgs.Clock", "GZ_TO_ROS"),
        _bridge(
            "/joint_states",
            "/joint_states",
            "sensor_msgs/msg/JointState",
            "gz.msgs.Model",
            "GZ_TO_ROS",
        ),
        _bridge(cmd_topic, cmd_topic, "geometry_msgs/msg/Twist", "gz.msgs.Twist", "ROS_TO_GZ"),
        _bridge(odom_topic, odom_topic, "nav_msgs/msg/Odometry", "gz.msgs.Odometry", "GZ_TO_ROS"),
    ]
    if gui_cmd_topic:
        bridge.append(
            _bridge(
                gui_cmd_topic,
                gui_cmd_topic,
                "geometry_msgs/msg/Twist",
                "gz.msgs.Twist",
                "GZ_TO_ROS",
            )
        )
    if _as_bool(imu.get("enabled"), False):
        topic = _topic(imu, "/imu/data")
        bridge.append(_bridge(topic, topic, "sensor_msgs/msg/Imu", "gz.msgs.IMU", "GZ_TO_ROS"))
    if _as_bool(lidar.get("enabled"), False):
        topic = _topic(lidar, "/scan")
        bridge.append(
            _bridge(topic, topic, "sensor_msgs/msg/LaserScan", "gz.msgs.LaserScan", "GZ_TO_ROS")
        )

    bumpers_cfg = params.get("bumpers") if isinstance(params.get("bumpers"), dict) else {}
    bumpers = _items(params.get("bumpers"))
    for bumper in bumpers:
        topic = f"/sim/bumper/{bumper['name']}/contact"
        bridge.append(
            _bridge(topic, topic, "ros_gz_interfaces/msg/Contacts", "gz.msgs.Contacts", "GZ_TO_ROS")
        )

    cliffs_cfg = params.get("cliff_sensors") if isinstance(params.get("cliff_sensors"), dict) else {}
    cliffs = _items(params.get("cliff_sensors"))
    for cliff in cliffs:
        topic = f"/sim/cliff/{cliff['name']}/scan"
        bridge.append(
            _bridge(topic, topic, "sensor_msgs/msg/LaserScan", "gz.msgs.LaserScan", "GZ_TO_ROS")
        )

    handle = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml", encoding="utf-8")
    yaml.safe_dump(bridge, handle, sort_keys=False)
    handle.close()
    return handle.name, bumpers, bumpers_cfg, cliffs, cliffs_cfg, odom_topic


def _yaw(block):
    rpy = block.get("mount_rpy") if isinstance(block.get("mount_rpy"), (list, tuple)) else []
    if len(rpy) > 2:
        return float(rpy[2])
    return 0.0


def _offset(block):
    raw = block.get("mount_offset") if isinstance(block.get("mount_offset"), (list, tuple)) else []
    values = [float(v) for v in list(raw)[:3]]
    while len(values) < 3:
        values.append(0.0)
    return values


def _create(context):
    robot_yaml = _resolve(LaunchConfiguration("robot_yaml").perform(context))
    if not robot_yaml or not os.path.isfile(robot_yaml):
        return [LogInfo(msg=f"[rmodus_gazebo] robot_yaml chybí nebo není soubor: {robot_yaml!r}")]

    gui_requested = _wants_gui(LaunchConfiguration("gui").perform(context))
    # A systemd service does not inherit the desktop. Attach to the WSLg
    # sockets when sim_gui is on. If those sockets are missing, stay headless:
    # Qt without a display aborts inside gz and takes the physics server with it.
    extra_env = _gui_env() if gui_requested else {}
    has_session = bool(
        os.environ.get("DISPLAY")
        or os.environ.get("WAYLAND_DISPLAY")
        or extra_env.get("DISPLAY")
        or extra_env.get("WAYLAND_DISPLAY")
    )
    gui = gui_requested and has_session
    gui_env = extra_env if gui else {}
    publish_tf = _as_bool(LaunchConfiguration("publish_tf").perform(context), True)
    spawn_z = LaunchConfiguration("spawn_z").perform(context).strip() or "0.05"

    share = get_package_share_directory("rmodus_gazebo")
    world = os.path.join(share, "worlds", "my_world.world")
    robot_xacro = os.path.join(
        get_package_share_directory("rmodus_description"), "urdf", "robot.urdf.xacro"
    )
    chassis_contents = os.path.join(
        get_package_share_directory("rmodus_chassis"), "urdf", "chassis_contents.urdf.xacro"
    )
    gazebo_urdf = os.path.join(share, "urdf")

    params = _load_profile(robot_yaml)
    gui_cmd_topic = "/sim_gui/cmd_vel" if gui else ""
    bridge_path, bumpers, bumpers_cfg, cliffs, cliffs_cfg, odom_topic = _write_bridge(
        params, gui_cmd_topic
    )
    flow = params.get("flow_sensor") if isinstance(params.get("flow_sensor"), dict) else {}
    flow_on = _as_bool(flow.get("enabled"), False)
    teleop_output = _teleop_output(params, _cmd_topic(params))

    resource_path = share
    existing = os.environ.get("GZ_SIM_RESOURCE_PATH", "")
    if existing:
        resource_path = share + os.pathsep + existing

    gz_cmd = ["gz", "sim", "-r"]
    if gui:
        gz_cmd.extend(["--gui-config", os.path.join(share, "config", "gui.config")])
    else:
        gz_cmd.append("-s")
    gz_cmd.append(world)

    sim_time = {"use_sim_time": True}
    actions = [
        LogInfo(
            msg=(
                f"[rmodus_gazebo] profile={robot_yaml} gui={gui} "
                f"(requested={gui_requested}) publish_tf={publish_tf}"
                + (f" teleop={gui_cmd_topic}→{teleop_output}" if gui else "")
            )
        ),
        SetEnvironmentVariable("GZ_SIM_RESOURCE_PATH", resource_path),
        ExecuteProcess(cmd=gz_cmd, additional_env=gui_env, output="screen"),
        Node(
            package="ros_gz_bridge",
            executable="parameter_bridge",
            parameters=[{"config_file": bridge_path, **sim_time}],
            output="screen",
        ),
        Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            parameters=[
                {
                    **sim_time,
                    "robot_description": ParameterValue(
                        Command(
                            [
                                "xacro ",
                                robot_xacro,
                                " config_path:=",
                                robot_yaml,
                                " include_chassis:=true",
                                " joint_type:=continuous",
                                " gazebo_overlay:=true",
                                " chassis_contents_path:=",
                                chassis_contents,
                                " gazebo_urdf_dir:=",
                                gazebo_urdf,
                            ]
                        ),
                        value_type=str,
                    ),
                }
            ],
            output="screen",
        ),
        TimerAction(
            period=3.0,
            actions=[
                Node(
                    package="ros_gz_sim",
                    executable="create",
                    arguments=["-topic", "robot_description", "-name", "rmodus", "-z", spawn_z],
                    parameters=[sim_time],
                    output="screen",
                )
            ],
        ),
    ]

    if gui:
        actions.append(
            Node(
                package="rmodus_gazebo",
                executable="sim_teleop_repeat",
                name="sim_teleop_repeat",
                parameters=[
                    {
                        **sim_time,
                        "input_topic": gui_cmd_topic,
                        "output_topic": teleop_output,
                    }
                ],
                output="screen",
            )
        )

    if publish_tf:
        actions.append(
            Node(
                package="rmodus_gazebo",
                executable="sim_odom_tf",
                name="sim_odom_tf",
                parameters=[{**sim_time, "odom_topic": odom_topic}],
                output="screen",
            )
        )

    if bumpers:
        actions.append(
            Node(
                package="rmodus_gazebo",
                executable="sim_bumper_bridge",
                name="sim_bumper_bridge",
                parameters=[
                    {
                        **sim_time,
                        "state_topic": str(bumpers_cfg.get("state_topic") or "/robot/bumpers/state"),
                        "bumper_names": [str(item["name"]) for item in bumpers],
                        "bumper_pins": [int(item.get("pin", index)) for index, item in enumerate(bumpers)],
                    }
                ],
                output="screen",
            )
        )

    if cliffs:
        actions.append(
            Node(
                package="rmodus_gazebo",
                executable="sim_cliff_bridge",
                name="sim_cliff_bridge",
                parameters=[
                    {
                        **sim_time,
                        "state_topic": str(cliffs_cfg.get("state_topic") or "/robot/cliffs/range"),
                        "cliff_names": [str(item["name"]) for item in cliffs],
                        "cliff_pins": [int(item.get("pin", index)) for index, item in enumerate(cliffs)],
                    }
                ],
                output="screen",
            )
        )

    if flow_on:
        actions.append(
            Node(
                package="rmodus_gazebo",
                executable="sim_flow_bridge",
                name="sim_flow_bridge",
                parameters=[
                    {
                        **sim_time,
                        "motion_topic": str(flow.get("motion_topic") or "/robot/flow/motion"),
                        "odom_topic": odom_topic,
                        "mount_yaw": _yaw(flow),
                        "mount_offset": _offset(flow),
                        "z_height": float(flow.get("z_height", 0.025)),
                        "fov_deg": float(flow.get("fov_deg", 42.0)),
                        "res_pix": int(flow.get("res_pix", 35)),
                        "timer_period": float(flow.get("timer_period", 0.05)),
                    }
                ],
                output="screen",
            )
        )

    return actions


def generate_launch_description():
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "robot_yaml",
                default_value="",
                description="Profil s /**/ros__parameters (stejný soubor jako bringup)",
            ),
            DeclareLaunchArgument(
                "gui",
                default_value="auto",
                description="true/false, nebo auto: okno jen při DISPLAY/WAYLAND, jinak gz sim -s",
            ),
            DeclareLaunchArgument(
                "publish_tf",
                default_value="true",
                description="odom → base_footprint z /odom. false když TF drží EKF",
            ),
            DeclareLaunchArgument(
                "spawn_z",
                default_value="0.05",
                description="Výška spawnu base_footprint nad zemí [m]",
            ),
            OpaqueFunction(function=_create),
        ]
    )
