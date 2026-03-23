from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import PathJoinSubstitution, LaunchConfiguration, Command
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    pkg_name = 'rmodus_hw'
    pkg_share = FindPackageShare(pkg_name)
    config_dir = PathJoinSubstitution([pkg_share, 'config'])

    params_base = PathJoinSubstitution([config_dir, 'base_params.yaml'])
    params_xsens = PathJoinSubstitution([config_dir, 'xsens_mti_node.yaml'])

    params_user_arg = DeclareLaunchArgument(
        'user_params_file',
        default_value=params_base,
        description='Path to user parameter file'
    )

    params_user = LaunchConfiguration('user_params_file')
    params = [params_base, params_user]

    robot_xacro = PathJoinSubstitution([pkg_share, 'urdf', 'robot.urdf.xacro'])

    return LaunchDescription([
        params_user_arg,

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{
                'use_sim_time': False,
                'robot_description': ParameterValue(
                    Command(['xacro ', robot_xacro]),
                    value_type=str
                )
            }],
            output='screen',
        ),

        Node(package=pkg_name, executable='get_wifi', name='wifi_service', parameters=params),
        Node(package=pkg_name, executable='system_monitor', name='sys_mon', parameters=params),
        Node(package=pkg_name, executable='fan_control', name='fan_ctrl', parameters=params),
        Node(package=pkg_name, executable='display', name='display_node', parameters=params),
        Node(package=pkg_name, executable='motors', name='motors_node', parameters=params),
        Node(package=pkg_name, executable='lidar', name='lidar_node', parameters=params),
        Node(package=pkg_name, executable='cliff_sensors', name='cliff_sensors_node', parameters=params),
        Node(package=pkg_name, executable='bumper_sensors', name='bumper_sensors_node', parameters=params),
        
        Node(
            package='xsens_mti_ros2_driver',
            executable='xsens_mti_node',
            parameters=[params_xsens],
            remappings=[('/temperature', '/xsens/temperature')]
        ),
    ])