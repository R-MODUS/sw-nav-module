"""Gazebo twin of the profile robot: same YAML, chassis + kit URDF, gz sensors and drive."""

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


def _bridge(ros_topic, gz_topic, ros_type, gz_type, direction):
    return {
        "ros_topic_name": ros_topic,
        "gz_topic_name": gz_topic,
        "ros_type_name": ros_type,
        "gz_type_name": gz_type,
        "direction": direction,
    }


def _write_bridge(params):
    cmd_topic = "/cmd_vel"
    mux = params.get("cmd_mux")
    if isinstance(mux, dict) and str(mux.get("output_topic") or "").strip():
        cmd_topic = str(mux["output_topic"]).strip()
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
    if _as_bool(imu.get("enabled"), False):
        topic = _topic(imu, "/imu/data")
        bridge.append(_bridge(topic, topic, "sensor_msgs/msg/Imu", "gz.msgs.IMU", "GZ_TO_ROS"))
    if _as_bool(lidar.get("enabled"), False):
        topic = _topic(lidar, "/scan")
        bridge.append(
            _bridge(topic, topic, "sensor_msgs/msg/LaserScan", "gz.msgs.LaserScan", "GZ_TO_ROS")
        )

    bumpers = _items(params.get("bumpers"))
    for bumper in bumpers:
        topic = f"/sim/bumper/{bumper['name']}/contact"
        bridge.append(
            _bridge(topic, topic, "ros_gz_interfaces/msg/Contacts", "gz.msgs.Contacts", "GZ_TO_ROS")
        )

    cliffs = _items(params.get("cliff_sensors"))
    for cliff in cliffs:
        topic = f"/sim/cliff/{cliff['name']}/scan"
        bridge.append(
            _bridge(topic, topic, "sensor_msgs/msg/LaserScan", "gz.msgs.LaserScan", "GZ_TO_ROS")
        )

    handle = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".yaml", encoding="utf-8")
    yaml.safe_dump(bridge, handle, sort_keys=False)
    handle.close()
    return handle.name, bumpers, cliffs, odom_topic


def _size(item, index, default):
    size = item.get("size") if isinstance(item.get("size"), (list, tuple)) else []
    if index < len(size):
        return float(size[index])
    return default


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
    robot_xacro = os.path.join(share, "urdf", "robot.urdf.xacro")
    chassis_contents = os.path.join(
        get_package_share_directory("rmodus_chassis"), "urdf", "chassis_contents.urdf.xacro"
    )
    description_urdf = os.path.join(get_package_share_directory("rmodus_description"), "urdf")

    params = _load_profile(robot_yaml)
    bridge_path, bumpers, cliffs, odom_topic = _write_bridge(params)

    resource_path = share
    existing = os.environ.get("GZ_SIM_RESOURCE_PATH", "")
    if existing:
        resource_path = share + os.pathsep + existing

    gz_cmd = ["gz", "sim", "-r"]
    if not gui:
        gz_cmd.append("-s")
    gz_cmd.append(world)

    sim_time = {"use_sim_time": True}
    actions = [
        LogInfo(
            msg=(
                f"[rmodus_gazebo] profile={robot_yaml} gui={gui} "
                f"(requested={gui_requested}) publish_tf={publish_tf}"
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
                                " chassis_contents_path:=",
                                chassis_contents,
                                " description_urdf_dir:=",
                                description_urdf,
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
                        "bumper_names": [str(item["name"]) for item in bumpers],
                        "bumper_topics": [
                            str(item.get("topic") or f"/bumper/{item['name']}") for item in bumpers
                        ],
                        "bumper_frames": [
                            str(item.get("frame_id") or f"bumper_{item['name']}_contact")
                            for item in bumpers
                        ],
                        # Same mapping as rmodus_bumper: width=size[1], depth=size[0], height=size[2].
                        "bumper_widths": [_size(item, 1, 0.3) for item in bumpers],
                        "bumper_depths": [_size(item, 0, 0.02) for item in bumpers],
                        "bumper_heights": [_size(item, 2, 0.05) for item in bumpers],
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
                        "cliff_names": [str(item["name"]) for item in cliffs],
                        "cliff_topics": [
                            str(item.get("topic") or f"/cliff/{item['name']}") for item in cliffs
                        ],
                        "cliff_frames": [
                            str(item.get("frame_id") or f"cliff_sensor_{item['name']}_beam")
                            for item in cliffs
                        ],
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
