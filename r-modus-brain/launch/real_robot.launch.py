from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    pkg_share = FindPackageShare('mecanum_navigation')
    config_dir = PathJoinSubstitution([pkg_share, 'config'])

    params_base = PathJoinSubstitution([config_dir, 'base_params.yaml'])
    params_user = PathJoinSubstitution([config_dir, 'user_params.yaml'])
    params = [params_base, params_user]

    xsens_config = PathJoinSubstitution([FindPackageShare('xsens_mti_ros2_driver'), 'param', 'xsens_mti_node.yaml'])
    robot_launch = PathJoinSubstitution([pkg_share, 'launch', 'robot.launch.py'])

    return LaunchDescription([
        Node(package='mecanum_navigation', executable='get_wifi', name='wifi_service', parameters=params),
        Node(package='mecanum_navigation', executable='system_monitor', name='sys_mon', parameters=params),
        Node(package='mecanum_navigation', executable='fan_control', name='fan_ctrl', parameters=params),
        Node(package='mecanum_navigation', executable='display', name='display_node', parameters=params),
        Node(package='mecanum_navigation', executable='motors', name='motors_node', parameters=params),
        Node(package='mecanum_navigation', executable='lidar', name='lidar_node', parameters=params),
        
        Node(
            package='xsens_mti_ros2_driver',
            executable='xsens_mti_node',
            parameters=[xsens_config],
            remappings=[('/temperature', '/xsens/temperature')]
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource([robot_launch]),
            launch_arguments={'use_sim_time': 'false'}.items()
        )
    ])