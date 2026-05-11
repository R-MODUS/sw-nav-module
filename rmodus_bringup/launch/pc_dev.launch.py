"""Spuštění na vývojovém PC: autonomie (Nav2, EKF, …), volitelně web a RViz.

Nepoužívej robot_state_publisher z desktopu, pokud už běží na robotovi — jinak máš
duplicitní TF. Senzorová data a /cmd_vel musí přes DDS dojít z robota (stejný domain)."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare('rmodus_bringup')
    autonomy_launch = PathJoinSubstitution([FindPackageShare('rmodus_autonomy'), 'launch', 'autonomy.launch.py'])
    rviz_launch = PathJoinSubstitution([pkg_share, 'launch', 'rviz.launch.py'])
    web_launch = PathJoinSubstitution([FindPackageShare('rmodus_web'), 'launch', 'web.launch.py'])

    use_sim_time = LaunchConfiguration('use_sim_time')
    localization = LaunchConfiguration('localization')
    navigation = LaunchConfiguration('navigation')
    slam = LaunchConfiguration('slam')
    rf2o = LaunchConfiguration('rf2o')
    rviz = LaunchConfiguration('rviz')
    launch_web = LaunchConfiguration('launch_web')
    user_params_file = LaunchConfiguration('user_params_file')
    robot_config_file = LaunchConfiguration('robot_config_file')

    return LaunchDescription([
        DeclareLaunchArgument('use_sim_time', default_value='false', description='false při řízení skutečného robota'),
        DeclareLaunchArgument('localization', default_value='true'),
        DeclareLaunchArgument('navigation', default_value='true'),
        DeclareLaunchArgument('slam', default_value='true'),
        DeclareLaunchArgument('rf2o', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='true'),
        DeclareLaunchArgument(
            'launch_web',
            default_value='true',
            description='Web UI na PC; na robotovi vypni, pokud tam už běží websocket',
        ),
        DeclareLaunchArgument(
            'user_params_file',
            default_value=PathJoinSubstitution([pkg_share, 'config', 'user_params.yaml']),
            description='Stejný jako na robotovi (parametry pro EKF / globální přepsání)',
        ),
        DeclareLaunchArgument(
            'robot_config_file',
            default_value=PathJoinSubstitution([
                FindPackageShare('rmodus_description'), 'config', 'default_robot_config.yaml',
            ]),
            description='Stejný URDF konfig jako na robotovi',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(autonomy_launch),
            launch_arguments={
                'use_sim_time': use_sim_time,
                'localization': localization,
                'navigation': navigation,
                'slam': slam,
                'rf2o': rf2o,
                'global_params_file': user_params_file,
                'robot_config_file': robot_config_file,
            }.items(),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(web_launch),
            condition=IfCondition(launch_web),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(rviz_launch),
            launch_arguments={'use_sim_time': use_sim_time}.items(),
            condition=IfCondition(rviz),
        ),
    ])
