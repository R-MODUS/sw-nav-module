import os
import yaml
import tempfile
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, SetEnvironmentVariable
from launch.substitutions import PathJoinSubstitution, Command
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch_ros.parameter_descriptions import ParameterValue

def generate_launch_description():
    pkg_name = 'rmodus_sim'
    pkg_share = FindPackageShare(pkg_name)
    world = PathJoinSubstitution([pkg_share, 'worlds', 'my_world.world'])
    sim_gui_config = PathJoinSubstitution([pkg_share, 'config', 'simulation.config'])
    robot_xacro = PathJoinSubstitution([pkg_share, 'urdf', 'robot.urdf.xacro'])

    src_str = os.path.join(get_package_share_directory(pkg_name), '..')
    bridge_config_str = os.path.join(get_package_share_directory(pkg_name), 'config', 'bridge_parameters.yaml')
    config_str = os.path.join(get_package_share_directory('rmodus_description'), 'config', 'robot_config.yaml')

    # merge static bridge config with dynamic sensor topics from robot config
    final_bridge_config_path, bumper_names = create_combined_bridge_config(
        bridge_config_str, 
        config_str
    )

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
            parameters=[{
                'config_file': final_bridge_config_path
                }],
            output='screen'
        ),
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            parameters=[{
                'use_sim_time': True,
                'robot_description': ParameterValue(
                    Command([
                        'xacro ', robot_xacro, ' ',
                        'config_path:=', config_str
                        ]),
                    value_type=str
                )
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
        Node(
            package=pkg_name,
            executable='sim_bumper_bridge',
            name='sim_bumper_bridge',
            output='screen',
            parameters=[{
                'use_sim_time': True,
                'bumper_names': bumper_names,
                }]
        ),
    ])

def create_combined_bridge_config(static_yaml_path, robot_config_path):
    """
    Spojí statický bridge YAML s dynamickými senzory z robot configu.
    Vrací cestu k dočasnému souboru.
    """
    # 1. Načtení statického základu (Twist, Odom, Lidar...)
    with open(static_yaml_path, 'r') as f:
        bridge_data = yaml.safe_load(f) or []

    # 2. Načtení robot configu pro zjištění senzorů
    with open(robot_config_path, 'r') as f:
        robot_data = yaml.safe_load(f)
        params = robot_data.get('/**', {}).get('ros__parameters', {})
        bumper_names = [b['name'] for b in params.get('bumpers', [])]

    # 3. Přidání bumperů
    for b in params.get('bumpers', []):
        name = b['name']
        bridge_data.append({
            'ros_topic_name': f'/bumper/{name}/contact',
            'gz_topic_name': f'/world/my_world/model/my_robot/link/bumper_{name}_link/sensor/bumper_{name}_sensor/contact',
            'ros_type_name': 'ros_gz_interfaces/msg/Contacts',
            'gz_type_name': 'gz.msgs.Contacts',
            'direction': 'GZ_TO_ROS'
        })

    # 4. Přidání cliff senzorů
    for c in params.get('cliff_sensors', []):
        name = c['name']
        bridge_data.append({
            'ros_topic_name': f'/cliff/{name}',
            'gz_topic_name': f'/cliff/{name}',
            'ros_type_name': 'sensor_msgs/msg/Range',
            'gz_type_name': 'gz.msgs.LaserScan',
            'direction': 'GZ_TO_ROS'
        })

    # 5. Uložení do dočasného souboru
    # delete=False zajistí, že soubor nezmizí dřív, než ho bridge načte
    tmp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml')
    yaml.dump(bridge_data, tmp_file)
    tmp_file.close()
    
    return tmp_file.name, bumper_names