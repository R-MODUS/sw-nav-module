import os
import yaml
import tempfile
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import ExecuteProcess, SetEnvironmentVariable, DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

def _deep_merge(base_obj, override_obj):
    if isinstance(base_obj, dict) and isinstance(override_obj, dict):
        merged = dict(base_obj)
        for key, value in override_obj.items():
            if key in merged:
                merged[key] = _deep_merge(merged[key], value)
            else:
                merged[key] = value
        return merged
    return override_obj


def _resolve_config_path(p):
    if p is None:
        return ''
    s = str(p).strip()
    if not s:
        return ''
    return os.path.normpath(os.path.expanduser(s))


def _create_sim_actions(context):
    pkg_name = 'rmodus_sim'
    structure_source = LaunchConfiguration('structure_source').perform(context)
    use_mesh_visuals = LaunchConfiguration('use_mesh_visuals').perform(context)
    sim_config_file = _resolve_config_path(LaunchConfiguration('sim_config_file').perform(context))
    sim_override_file = _resolve_config_path(LaunchConfiguration('sim_override_file').perform(context))
    dynamic_bridge_base_config_file = _resolve_config_path(
        LaunchConfiguration('dynamic_bridge_base_config_file').perform(context)
    )
    world = os.path.join(get_package_share_directory(pkg_name), 'worlds', 'my_world.world')
    sim_gui_config = os.path.join(get_package_share_directory(pkg_name), 'config', 'simulation.config')
    robot_xacro = os.path.join(get_package_share_directory(pkg_name), 'urdf', 'robot.urdf.xacro')

    src_str = os.path.join(get_package_share_directory(pkg_name), '..')

    final_robot_config = sim_config_file
    if sim_override_file and os.path.exists(sim_override_file):
        with open(sim_config_file, 'r', encoding='utf-8') as f:
            base_cfg = yaml.safe_load(f) or {}
        with open(sim_override_file, 'r', encoding='utf-8') as f:
            global_cfg = yaml.safe_load(f) or {}

        merged_cfg = _deep_merge(base_cfg, global_cfg)
        tmp_cfg = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.yaml')
        yaml.safe_dump(merged_cfg, tmp_cfg)
        tmp_cfg.close()
        final_robot_config = tmp_cfg.name

    final_bridge_config_path, bumper_names = create_combined_bridge_config(
        dynamic_bridge_base_config_file,
        final_robot_config,
    )

    verbose = ''
    paused = '-r'

    return [
        SetEnvironmentVariable(
            'GZ_SIM_RESOURCE_PATH', [src_str]
        ),
        ExecuteProcess(
            cmd=[
                'gz', 'sim',
                verbose, paused,
                '--gui-config', sim_gui_config,
                world,
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
                        'config_path:=', final_robot_config, ' ',
                        'structure_source:=', structure_source, ' ',
                        'use_mesh_visuals:=', use_mesh_visuals
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
    ]


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'structure_source',
            default_value='description',
            description='Robot structure source: description or local',
        ),
        DeclareLaunchArgument(
            'use_mesh_visuals',
            default_value='true',
            description='Use mesh visuals instead of collision-like primitives',
        ),
        DeclareLaunchArgument(
            'sim_config_file',
            default_value=os.path.join(
                get_package_share_directory('rmodus_sim'),
                'config',
                'sim.yaml',
            ),
            description='Base simulation YAML config',
        ),
        DeclareLaunchArgument(
            'sim_override_file',
            default_value='',
            description='Path to optional simulation override YAML',
        ),
        DeclareLaunchArgument(
            'dynamic_bridge_base_config_file',
            default_value=os.path.join(
                get_package_share_directory('rmodus_sim'),
                'config',
                'bridge_parameters.yaml',
            ),
            description='Base bridge config used for dynamic bridge generation',
        ),
        OpaqueFunction(function=_create_sim_actions),
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
        bumpers = [b for b in params.get('bumpers', []) if b.get('enabled', True)]
        cliff_sensors = [c for c in params.get('cliff_sensors', []) if c.get('enabled', True)]
        bumper_names = [b['name'] for b in bumpers]

    # 3. Přidání bumperů
    for b in bumpers:
        name = b['name']
        bridge_data.append({
            'ros_topic_name': f'/bumper/{name}/contact',
            'gz_topic_name': f'/world/my_world/model/my_robot/link/bumper_{name}_mount/sensor/bumper_{name}_sensor/contact',
            'ros_type_name': 'ros_gz_interfaces/msg/Contacts',
            'gz_type_name': 'gz.msgs.Contacts',
            'direction': 'GZ_TO_ROS'
        })

    # 4. Přidání cliff senzorů
    for c in cliff_sensors:
        name = c['name']
        bridge_data.append({
            'ros_topic_name': c.get('topic', f'/cliff/{name}'),
            'gz_topic_name': c.get('topic', f'/cliff/{name}'),
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