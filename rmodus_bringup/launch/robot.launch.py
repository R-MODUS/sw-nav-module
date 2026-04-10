from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution, PythonExpression
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = FindPackageShare('rmodus_bringup')

    hw_launch = PathJoinSubstitution([FindPackageShare('rmodus_hw'), 'launch', 'hw.launch.py'])
    sim_launch = PathJoinSubstitution([FindPackageShare('rmodus_sim'), 'launch', 'sim.launch.py'])
    brain_launch = PathJoinSubstitution([FindPackageShare('rmodus_brain'), 'launch', 'brain.launch.py'])
    rviz_launch = PathJoinSubstitution([pkg_share, 'launch', 'rviz.launch.py'])

    mode = LaunchConfiguration('mode')
    use_sim_time = PythonExpression(["'true' if '", LaunchConfiguration('mode'), "' == 'sim' else 'false'"])
    navigation = LaunchConfiguration('navigation')
    slam = LaunchConfiguration('slam')
    rf2o = LaunchConfiguration('rf2o')
    rviz = LaunchConfiguration('rviz')
    user_params_file = LaunchConfiguration('user_params_file')

    mode_is_sim = IfCondition(PythonExpression(["'", mode, "' == 'sim'"]))
    mode_is_hw = IfCondition(PythonExpression(["'", mode, "' == 'hw'"]))

    return LaunchDescription([
        DeclareLaunchArgument('mode', default_value='hw', description='Launch mode: hw or sim'),
        DeclareLaunchArgument('navigation', default_value='true'),
        DeclareLaunchArgument('slam', default_value='true'),
        DeclareLaunchArgument('rf2o', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='false'),
        DeclareLaunchArgument(
            'user_params_file',
            default_value=PathJoinSubstitution([pkg_share, 'config', 'user_params.yaml']),
            description='Global override params file for all packages',
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(hw_launch),
            launch_arguments={'user_params_file': user_params_file}.items(),
            condition=mode_is_hw,
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(sim_launch),
            launch_arguments={
                'global_params_file': user_params_file,
                'structure_source': 'description',
            }.items(),
            condition=mode_is_sim,
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(brain_launch),
            launch_arguments={
                'use_sim_time': use_sim_time,
                'navigation': navigation,
                'slam': slam,
                'rf2o': rf2o,
                'global_params_file': user_params_file,
            }.items(),
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(rviz_launch),
            condition=IfCondition(rviz),
        ),
    ])