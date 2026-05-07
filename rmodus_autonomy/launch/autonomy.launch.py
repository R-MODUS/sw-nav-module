from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    autonomy_share = FindPackageShare("rmodus_autonomy")

    robot_config_file = LaunchConfiguration("robot_config_file")
    global_params_file = LaunchConfiguration("global_params_file")
    rf2o_params = LaunchConfiguration("rf2o_params_file")
    slam_params = LaunchConfiguration("slam_params_file")
    nav2_params = LaunchConfiguration("nav2_params_file")

    use_sim_time = LaunchConfiguration("use_sim_time")
    slam = LaunchConfiguration("slam")
    navigation = LaunchConfiguration("navigation")
    rf2o = LaunchConfiguration("rf2o")
    obstacle_cloud = LaunchConfiguration("obstacle_cloud")
    bumper_safety_stop = LaunchConfiguration("bumper_safety_stop")
    bumper_safety_stop_params = LaunchConfiguration("bumper_safety_stop_params_file")

    ekf_launch = PathJoinSubstitution([autonomy_share, "launch", "ekf_dynamic.launch.py"])
    nav2_launch = PathJoinSubstitution([autonomy_share, "launch", "nav2.launch.py"])
    slam_toolbox_launch = PathJoinSubstitution(
        [FindPackageShare("slam_toolbox"), "launch", "online_async_launch.py"]
    )

    return LaunchDescription(
        [
            DeclareLaunchArgument("use_sim_time", default_value="false"),
            DeclareLaunchArgument("slam", default_value="true"),
            DeclareLaunchArgument("navigation", default_value="true"),
            DeclareLaunchArgument("rf2o", default_value="false"),
            DeclareLaunchArgument("obstacle_cloud", default_value="true"),
            DeclareLaunchArgument("bumper_safety_stop", default_value="true"),
            DeclareLaunchArgument(
                "global_params_file",
                default_value="",
                description="Path to optional global params file",
            ),
            DeclareLaunchArgument(
                "robot_config_file",
                default_value=PathJoinSubstitution(
                    [FindPackageShare("rmodus_description"), "config", "default_robot_config.yaml"]
                ),
                description="Path to robot config file",
            ),
            DeclareLaunchArgument(
                "rf2o_params_file",
                default_value=PathJoinSubstitution([autonomy_share, "config", "rf2o_params.yaml"]),
                description="RF2O parameters file",
            ),
            DeclareLaunchArgument(
                "slam_params_file",
                default_value=PathJoinSubstitution([autonomy_share, "config", "slam_params.yaml"]),
                description="SLAM toolbox parameters file",
            ),
            DeclareLaunchArgument(
                "nav2_params_file",
                default_value=PathJoinSubstitution([autonomy_share, "config", "nav2_params.yaml"]),
                description="Nav2 parameters file",
            ),
            DeclareLaunchArgument(
                "bumper_safety_stop_params_file",
                default_value=PathJoinSubstitution([autonomy_share, "config", "bumper_safety_stop.yaml"]),
                description="Bumper safety stop parameters file",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(ekf_launch),
                launch_arguments={
                    "use_sim_time": use_sim_time,
                    "robot_config_file": robot_config_file,
                    "global_params_file": global_params_file,
                }.items(),
            ),
            Node(
                package="rf2o_laser_odometry",
                executable="rf2o_laser_odometry_node",
                name="rf2o_laser_odometry",
                parameters=[rf2o_params, {"use_sim_time": use_sim_time}],
                output="screen",
                emulate_tty=True,
                condition=IfCondition(rf2o),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(slam_toolbox_launch),
                launch_arguments={"slam_params_file": slam_params, "use_sim_time": use_sim_time}.items(),
                condition=IfCondition(slam),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(nav2_launch),
                launch_arguments={"params_file": nav2_params, "use_sim_time": use_sim_time}.items(),
                condition=IfCondition(navigation),
            ),
            Node(
                package="rmodus_autonomy",
                executable="obstacle_cloud",
                name="obstacle_cloud",
                parameters=[{"use_sim_time": use_sim_time}],
                output="screen",
                emulate_tty=True,
                condition=IfCondition(obstacle_cloud),
            ),
            Node(
                package="rmodus_autonomy",
                executable="bumper_safety_stop",
                name="bumper_safety_stop",
                parameters=[bumper_safety_stop_params, {"use_sim_time": use_sim_time}],
                output="screen",
                emulate_tty=True,
                condition=IfCondition(bumper_safety_stop),
            ),
        ]
    )
