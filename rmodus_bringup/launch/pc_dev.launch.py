"""Spuštění na vývojovém PC: autonomie, volitelně TF z URDF, web a RViz.

Výchozí je spustit description (robot_state_publisher) zde, když na Pi neběží
(`robot_edge.launch.py`, `launch_description:=false`). Jeden soubor `robot_yaml`
na obou strojích. Nespouštěj description na obou najednou."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare('rmodus_bringup')
    description_launch = PathJoinSubstitution([FindPackageShare('rmodus_description'), 'launch', 'description.launch.py'])
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
    robot_yaml = LaunchConfiguration('robot_yaml')
    launch_description = LaunchConfiguration('launch_description')

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
            'robot_yaml',
            default_value=PathJoinSubstitution([pkg_share, 'config', 'robot.yaml']),
            description='Stejný soubor jako na robotovi (`robot_edge.launch.py`).',
        ),
        DeclareLaunchArgument(
            'launch_description',
            default_value='true',
            description='robot_state_publisher na PC (vypni, když description už běží na Pi)',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(description_launch),
            launch_arguments={
                'use_sim_time': use_sim_time,
                'robot_config_file': robot_yaml,
                'override_config_path': robot_yaml,
            }.items(),
            condition=IfCondition(launch_description),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(autonomy_launch),
            launch_arguments={
                'use_sim_time': use_sim_time,
                'localization': localization,
                'navigation': navigation,
                'slam': slam,
                'rf2o': rf2o,
                'global_params_file': robot_yaml,
                'robot_config_file': robot_yaml,
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
