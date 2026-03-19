from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
	brain_share = FindPackageShare('rmodus_brain')

	ekf_params = LaunchConfiguration('ekf_params_file')
	rf2o_params = LaunchConfiguration('rf2o_params_file')
	slam_params = LaunchConfiguration('slam_params_file')
	nav2_params = LaunchConfiguration('nav2_params_file')

	use_sim_time = LaunchConfiguration('use_sim_time')
	slam = LaunchConfiguration('slam')
	navigation = LaunchConfiguration('navigation')
	rf2o = LaunchConfiguration('rf2o')

	nav2_launch = PathJoinSubstitution([brain_share, 'launch', 'nav2.launch.py'])
	slam_toolbox_launch = PathJoinSubstitution(
		[FindPackageShare('slam_toolbox'), 'launch', 'online_async_launch.py']
	)

	return LaunchDescription([
		DeclareLaunchArgument('use_sim_time', default_value='false'),
		DeclareLaunchArgument('slam', default_value='true'),
		DeclareLaunchArgument('navigation', default_value='true'),
		DeclareLaunchArgument('rf2o', default_value='false'),
		DeclareLaunchArgument(
			'ekf_params_file',
			default_value=PathJoinSubstitution([brain_share, 'config', 'ekf_params.yaml']),
			description='EKF parameters file',
		),
		DeclareLaunchArgument(
			'rf2o_params_file',
			default_value=PathJoinSubstitution([brain_share, 'config', 'rf2o_params.yaml']),
			description='RF2O parameters file',
		),
		DeclareLaunchArgument(
			'slam_params_file',
			default_value=PathJoinSubstitution([brain_share, 'config', 'slam_params.yaml']),
			description='SLAM toolbox parameters file',
		),
		DeclareLaunchArgument(
			'nav2_params_file',
			default_value=PathJoinSubstitution([brain_share, 'config', 'nav2_params.yaml']),
			description='Nav2 parameters file',
		),

		Node(
			package='rmodus_brain',
			executable='websocket',
			name='websocket_node',
			output='screen',
			emulate_tty=True,
		),

		Node(
			package='robot_localization',
			executable='ekf_node',
			name='ekf_filter_node',
			parameters=[ekf_params, {'use_sim_time': use_sim_time}],
			output='screen',
			emulate_tty=True,
		),

		Node(
			package='rf2o_laser_odometry',
			executable='rf2o_laser_odometry_node',
			name='rf2o_laser_odometry',
			parameters=[rf2o_params, {'use_sim_time': use_sim_time}],
			output='screen',
			emulate_tty=True,
			condition=IfCondition(rf2o),
		),

		IncludeLaunchDescription(
			PythonLaunchDescriptionSource(slam_toolbox_launch),
			launch_arguments={
				'slam_params_file': slam_params,
				'use_sim_time': use_sim_time,
			}.items(),
			condition=IfCondition(slam),
		),

		IncludeLaunchDescription(
			PythonLaunchDescriptionSource(nav2_launch),
			launch_arguments={
				'params_file': nav2_params,
				'use_sim_time': use_sim_time,
			}.items(),
			condition=IfCondition(navigation),
		),
	])
