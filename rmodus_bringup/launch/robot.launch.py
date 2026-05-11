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
    description_launch = PathJoinSubstitution([FindPackageShare('rmodus_description'), 'launch', 'description.launch.py'])
    web_launch = PathJoinSubstitution([FindPackageShare('rmodus_web'), 'launch', 'web.launch.py'])
    autonomy_launch = PathJoinSubstitution([FindPackageShare('rmodus_autonomy'), 'launch', 'autonomy.launch.py'])
    rviz_launch = PathJoinSubstitution([pkg_share, 'launch', 'rviz.launch.py'])

    mode = LaunchConfiguration('mode')
    use_sim_time = PythonExpression(["'true' if '", LaunchConfiguration('mode'), "' == 'sim' else 'false'"])
    localization = LaunchConfiguration('localization')
    use_mesh_visuals = LaunchConfiguration('use_mesh_visuals')
    navigation = LaunchConfiguration('navigation')
    slam = LaunchConfiguration('slam')
    rf2o = LaunchConfiguration('rf2o')
    rviz = LaunchConfiguration('rviz')
    robot_yaml = LaunchConfiguration('robot_yaml')

    mode_is_sim = IfCondition(PythonExpression(["'", mode, "' == 'sim'"]))
    mode_is_hw = IfCondition(PythonExpression(["'", mode, "' == 'hw'"]))

    return LaunchDescription([
        DeclareLaunchArgument('mode', default_value='hw', description='Launch mode: hw or sim'),
        DeclareLaunchArgument('localization', default_value='true'),
        DeclareLaunchArgument('use_mesh_visuals', default_value='true'),
        DeclareLaunchArgument('navigation', default_value='true'),
        DeclareLaunchArgument('slam', default_value='true'),
        DeclareLaunchArgument('rf2o', default_value='false'),
        DeclareLaunchArgument('rviz', default_value='false'),
        DeclareLaunchArgument(
            'robot_yaml',
            default_value=PathJoinSubstitution([pkg_share, 'config', 'robot.yaml']),
            description='Jeden soubor: URDF konfig + globální ros__parameters (stejný na Pi i PC)',
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(hw_launch),
            launch_arguments={
                'user_params_file': robot_yaml,
            }.items(),
            condition=mode_is_hw,
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(description_launch),
            launch_arguments={
                'use_sim_time': 'false',
                'robot_config_file': robot_yaml,
                'override_config_path': robot_yaml,
            }.items(),
            condition=mode_is_hw,
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(sim_launch),
            launch_arguments={
                'structure_source': 'description',
                'use_mesh_visuals': use_mesh_visuals,
                'sim_config_file': robot_yaml,
                'sim_override_file': robot_yaml,
            }.items(),
            condition=mode_is_sim,
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(web_launch),
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
            PythonLaunchDescriptionSource(rviz_launch),
            launch_arguments={
                'use_sim_time': use_sim_time,
            }.items(),
            condition=IfCondition(rviz),
        ),
    ])