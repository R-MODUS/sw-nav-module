from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, Command, PathJoinSubstitution
from launch_ros.actions import Node
from launch.conditions import IfCondition
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    pkg_share = FindPackageShare('sim_robot')
    config_dir = PathJoinSubstitution([pkg_share, 'config'])

    slam_toolbox_launch = PathJoinSubstitution([FindPackageShare('slam_toolbox'), 'launch', 'online_async_launch.py'])
    navigation_launch = PathJoinSubstitution([pkg_share, 'launch', 'navigation.launch.py'])

    use_sim_time = LaunchConfiguration('use_sim_time')
    navigation_enabled = LaunchConfiguration('navigation')
    slam_enabled = LaunchConfiguration('slam')

    robot_xacro = PathJoinSubstitution([pkg_share, 'urdf', 'robot.xacro'])
    rl_params = PathJoinSubstitution([config_dir, 'ekf_params.yaml'])
    rf2o_params = PathJoinSubstitution([config_dir, 'rf2o_params.yaml'])
    slam_params = PathJoinSubstitution([config_dir, 'slam_params.yaml'])
    nav2_params = PathJoinSubstitution([config_dir, 'nav2_params.yaml'])

    robot_launch = PathJoinSubstitution([pkg_share, 'launch', 'robot.launch.py'])
    rviz_launch = PathJoinSubstitution([pkg_share, 'launch', 'rviz.launch.py'])

    use_sim_time = True

    slam = True
    navigation = True

    rviz = True

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false'),
        DeclareLaunchArgument('navigation', default_value='true'),
        DeclareLaunchArgument('slam', default_value='true'),


        Node(
            package='mecanum_navigation',
            executable='websocket',
            name='websocket_node',
            output='screen',
            emulate_tty=True,
        ),
        #Node(
        #    package='rf2o_laser_odometry',
        #    executable='rf2o_laser_odometry_node',
        #    parameters=[rf2o_params, {'use_sim_time': use_sim_time}],
        #    output='screen',
        #    emulate_tty=True,
        #),
        Node(
            package='robot_localization',
            executable='ekf_node',
            parameters=[rl_params, {'use_sim_time': use_sim_time}],
            output='screen',
            emulate_tty=True,
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(slam_toolbox_launch),
            launch_arguments={
                'params_file': slam_params,
                'use_sim_time': use_sim_time
            }.items(),
            condition=IfCondition(slam_enabled)
        ),
        # Navigation - Spustí se jen pokud je navigation='true'
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(navigation_launch),
            launch_arguments={
                'params_file': nav2_params,
                'use_sim_time': use_sim_time
            }.items(),
            condition=IfCondition(navigation_enabled)
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([robot_launch]),
            launch_arguments={
                'use_sim_time': str(use_sim_time).lower(),
                'navigation': str(navigation).lower(),
                'slam': str(slam).lower()
                }.items()
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([rviz_launch]),
            condition=IfCondition(str(rviz).lower())
        ),
    ])