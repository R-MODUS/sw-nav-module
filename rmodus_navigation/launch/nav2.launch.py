"""Nav2 uzly. Parametry se přepíšou z robot_yaml (otisk, scan, limity, use_sim_time).

Výstup velocity_smootheru je cmd_vel_topic, výchozí /nav/cmd_vel. Na /cmd_vel se nepublikuje.
"""

import os

import yaml
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction, OpaqueFunction, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration, PythonExpression
from launch_ros.actions import LoadComposableNodes, Node, PushRosNamespace
from launch_ros.descriptions import ComposableNode
from nav2_common.launch import RewrittenYaml

from rmodus_navigation.nav_params import apply_robot_profile, load_robot_parameters, write_params


def _as_bool(raw: str) -> bool:
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def _create(context):
    namespace = LaunchConfiguration("namespace")
    use_sim_time = LaunchConfiguration("use_sim_time")
    autostart = LaunchConfiguration("autostart")
    use_composition = LaunchConfiguration("use_composition")
    container_name = LaunchConfiguration("container_name")
    container_name_full = (namespace, "/", container_name)
    use_respawn = LaunchConfiguration("use_respawn")
    log_level = LaunchConfiguration("log_level")
    cmd_vel_topic = LaunchConfiguration("cmd_vel_topic")

    use_sim = _as_bool(use_sim_time.perform(context))
    start_amcl = _as_bool(LaunchConfiguration("start_amcl").perform(context))
    start_navigate = _as_bool(LaunchConfiguration("start_navigate").perform(context))
    robot_yaml = LaunchConfiguration("robot_yaml").perform(context).strip()
    map_yaml = LaunchConfiguration("map").perform(context).strip()
    params_path = LaunchConfiguration("params_file").perform(context).strip()

    if not params_path or not os.path.isfile(params_path):
        raise RuntimeError(f"nav2 params file not found: {params_path}")
    with open(params_path, "r", encoding="utf-8") as handle:
        nav_params = yaml.safe_load(handle) or {}
    rewritten = apply_robot_profile(
        nav_params,
        load_robot_parameters(robot_yaml),
        use_sim,
        map_yaml if start_amcl else "",
    )
    rewritten_path = write_params(rewritten)
    configured_params = RewrittenYaml(
        source_file=rewritten_path,
        root_key=namespace,
        param_rewrites={"use_sim_time": use_sim_time, "autostart": autostart},
        convert_types=True,
    )

    lifecycle_nodes = []
    if start_amcl:
        lifecycle_nodes.extend(["map_server", "amcl"])
    lifecycle_nodes.extend(["controller_server", "smoother_server"])
    if start_navigate:
        lifecycle_nodes.append("planner_server")
    lifecycle_nodes.append("behavior_server")
    if start_navigate:
        lifecycle_nodes.extend(["bt_navigator", "waypoint_follower"])
    lifecycle_nodes.append("velocity_smoother")

    remappings = [("/tf", "tf"), ("/tf_static", "tf_static")]
    cmd_remap = ("cmd_vel", "cmd_vel_nav")
    smooth_remap = ("cmd_vel_smoothed", cmd_vel_topic)

    def _screen_node(package, executable, name, extra_remaps, extra_args=None):
        arguments = ["--ros-args", "--log-level", log_level]
        if extra_args:
            arguments.extend(extra_args)
        return Node(
            package=package,
            executable=executable,
            name=name,
            output="screen",
            respawn=use_respawn,
            respawn_delay=2.0,
            parameters=[configured_params],
            arguments=arguments,
            remappings=remappings + extra_remaps,
        )

    nodes = []
    if start_amcl:
        nodes.append(_screen_node("nav2_map_server", "map_server", "map_server", []))
        nodes.append(_screen_node("nav2_amcl", "amcl", "amcl", []))
    nodes.append(
        _screen_node(
            "nav2_controller",
            "controller_server",
            "controller_server",
            [cmd_remap],
            ["--log-level", "controller_server:=warn"],
        )
    )
    nodes.append(_screen_node("nav2_smoother", "smoother_server", "smoother_server", []))
    if start_navigate:
        nodes.append(
            _screen_node(
                "nav2_planner",
                "planner_server",
                "planner_server",
                [],
                ["--log-level", "planner_server:=warn"],
            )
        )
    nodes.append(_screen_node("nav2_behaviors", "behavior_server", "behavior_server", [cmd_remap]))
    if start_navigate:
        nodes.append(_screen_node("nav2_bt_navigator", "bt_navigator", "bt_navigator", []))
        nodes.append(
            _screen_node("nav2_waypoint_follower", "waypoint_follower", "waypoint_follower", [])
        )
    nodes.append(
        _screen_node(
            "nav2_velocity_smoother",
            "velocity_smoother",
            "velocity_smoother",
            [cmd_remap, smooth_remap],
        )
    )
    nodes.append(
        Node(
            package="nav2_lifecycle_manager",
            executable="lifecycle_manager",
            name="lifecycle_manager_navigation",
            output="screen",
            arguments=["--ros-args", "--log-level", log_level],
            parameters=[
                {"use_sim_time": use_sim_time},
                {"autostart": autostart},
                {"node_names": lifecycle_nodes},
            ],
        )
    )

    composable = []
    if start_amcl:
        composable.append(
            ComposableNode(
                package="nav2_map_server",
                plugin="nav2_map_server::MapServer",
                name="map_server",
                parameters=[configured_params],
                remappings=remappings,
            )
        )
        composable.append(
            ComposableNode(
                package="nav2_amcl",
                plugin="nav2_amcl::AmclNode",
                name="amcl",
                parameters=[configured_params],
                remappings=remappings,
            )
        )
    composable.append(
        ComposableNode(
            package="nav2_controller",
            plugin="nav2_controller::ControllerServer",
            name="controller_server",
            parameters=[configured_params],
            remappings=remappings + [cmd_remap],
        )
    )
    composable.append(
        ComposableNode(
            package="nav2_smoother",
            plugin="nav2_smoother::SmootherServer",
            name="smoother_server",
            parameters=[configured_params],
            remappings=remappings,
        )
    )
    if start_navigate:
        composable.append(
            ComposableNode(
                package="nav2_planner",
                plugin="nav2_planner::PlannerServer",
                name="planner_server",
                parameters=[configured_params],
                remappings=remappings,
            )
        )
    composable.append(
        ComposableNode(
            package="nav2_behaviors",
            plugin="behavior_server::BehaviorServer",
            name="behavior_server",
            parameters=[configured_params],
            remappings=remappings + [cmd_remap],
        )
    )
    if start_navigate:
        composable.append(
            ComposableNode(
                package="nav2_bt_navigator",
                plugin="nav2_bt_navigator::BtNavigator",
                name="bt_navigator",
                parameters=[configured_params],
                remappings=remappings,
            )
        )
        composable.append(
            ComposableNode(
                package="nav2_waypoint_follower",
                plugin="nav2_waypoint_follower::WaypointFollower",
                name="waypoint_follower",
                parameters=[configured_params],
                remappings=remappings,
            )
        )
    composable.append(
        ComposableNode(
            package="nav2_velocity_smoother",
            plugin="nav2_velocity_smoother::VelocitySmoother",
            name="velocity_smoother",
            parameters=[configured_params],
            remappings=remappings + [cmd_remap, smooth_remap],
        )
    )
    composable.append(
        ComposableNode(
            package="nav2_lifecycle_manager",
            plugin="nav2_lifecycle_manager::LifecycleManager",
            name="lifecycle_manager_navigation",
            parameters=[
                {
                    "use_sim_time": use_sim_time,
                    "autostart": autostart,
                    "node_names": lifecycle_nodes,
                }
            ],
        )
    )

    load_nodes = GroupAction(
        condition=IfCondition(PythonExpression(["not ", use_composition])),
        actions=[PushRosNamespace(namespace=namespace), *nodes],
    )
    load_composable_nodes = LoadComposableNodes(
        condition=IfCondition(use_composition),
        target_container=container_name_full,
        composable_node_descriptions=composable,
    )
    return [load_nodes, load_composable_nodes]


def generate_launch_description():
    bringup_dir = get_package_share_directory("rmodus_navigation")
    ld = LaunchDescription()
    ld.add_action(SetEnvironmentVariable("RCUTILS_LOGGING_BUFFERED_STREAM", "1"))
    ld.add_action(DeclareLaunchArgument("namespace", default_value="", description="Top-level namespace"))
    ld.add_action(
        DeclareLaunchArgument("use_sim_time", default_value="false", description="Use simulation (Gazebo) clock")
    )
    ld.add_action(
        DeclareLaunchArgument(
            "params_file",
            default_value=os.path.join(bringup_dir, "config", "nav2_params.yaml"),
            description="Full path to ROS2 parameters file",
        )
    )
    ld.add_action(DeclareLaunchArgument("robot_yaml", default_value=""))
    ld.add_action(DeclareLaunchArgument("map", default_value=""))
    ld.add_action(
        DeclareLaunchArgument(
            "start_amcl",
            default_value="false",
            description="true = map_server + AMCL (uložená mapa). Se slam_toolbox se nezapíná.",
        )
    )
    ld.add_action(
        DeclareLaunchArgument(
            "start_navigate",
            default_value="true",
            description="false = bez planneru, bt_navigator a waypoint_follower (NavigateToPose přeskočené)",
        )
    )
    ld.add_action(DeclareLaunchArgument("autostart", default_value="true", description="Auto-start nav2 stack"))
    ld.add_action(DeclareLaunchArgument("use_composition", default_value="False"))
    ld.add_action(DeclareLaunchArgument("container_name", default_value="nav2_container"))
    ld.add_action(DeclareLaunchArgument("use_respawn", default_value="False"))
    ld.add_action(DeclareLaunchArgument("log_level", default_value="info"))
    ld.add_action(
        DeclareLaunchArgument(
            "cmd_vel_topic",
            default_value="/nav/cmd_vel",
            description="Výstup velocity_smootheru = vstup nav v cmd_mux",
        )
    )
    ld.add_action(OpaqueFunction(function=_create))
    return ld
