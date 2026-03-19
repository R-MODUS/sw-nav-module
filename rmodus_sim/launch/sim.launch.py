import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, SetEnvironmentVariable
from launch.substitutions import PathJoinSubstitution, Command
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    pkg_share = FindPackageShare('rmodus_sim')
    src_str = os.path.join(get_package_share_directory('rmodus_sim'), '..')
    world = PathJoinSubstitution([pkg_share, 'worlds', 'my_world.world'])
    sim_gui_config = PathJoinSubstitution([pkg_share, 'config', 'simulation.config'])
    bridge_config = PathJoinSubstitution([pkg_share, 'config', 'bridge_parameters.yaml'])
    robot_xacro = PathJoinSubstitution([pkg_share, 'urdf', 'robot.xacro'])

    #gazebo options
    verbose = False
    paused = False

    verbose = '-v' if verbose else ''
    paused = '-r' if  not paused else ''
    
    return LaunchDescription([

        SetEnvironmentVariable(
            'GZ_SIM_RESOURCE_PATH', [src_str]
        ),
        ExecuteProcess(
            cmd=[
                'gz', 'sim', 
                verbose, paused, 
                '--gui-config', sim_gui_config, 
                world
            ],
            output='screen'
        ),
        Node(
            package='ros_gz_bridge',
            executable='parameter_bridge',
            parameters=[{'config_file': bridge_config}],
            output='screen'
        ),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{
                'use_sim_time': True,
                'robot_description': Command(['xacro ', robot_xacro, ' is_sim:=', 'true'])
            }],
            output='screen',
            emulate_tty=True,
        ),
        Node(
            package='ros_gz_sim',
            executable='create',
            arguments=['-topic', '/robot_description', '-name', 'my_robot', '-z', '0.2'],
            output='screen'
        ),
    ])