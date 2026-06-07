import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    pkg_share = get_package_share_directory('llm_serving_gazebo')
    default_world = os.path.join(pkg_share, 'worlds', 'RoboRestaurant__.world')
    local_models = os.path.join(pkg_share, 'models')

    gazebo_model_path = SetEnvironmentVariable(
        name='GAZEBO_MODEL_PATH',
        value=f"{os.environ.get('GAZEBO_MODEL_PATH', '')}:{local_models}",
    )

    world_arg = DeclareLaunchArgument(
        'world',
        default_value=default_world,
        description='Path to Gazebo world file',
    )

    use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='true',
        description='Use simulation clock',
    )

    start_nav2 = DeclareLaunchArgument(
        'start_nav2',
        default_value='true',
        description='Start Nav2 localization and navigation stack',
    )

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('gazebo_ros'),
                'launch',
                'gazebo.launch.py',
            ])
        ]),
        launch_arguments={'world': LaunchConfiguration('world')}.items(),
    )
    
    spawn_robot1 = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=[
            '-entity', 'robot1',
            '-file', os.path.join(local_models, 'serving_robot', 'model.sdf'),
            '-x', '-7.451785', '-y', '-6.672494', '-z', '0.3',
        ],
        output='screen',
    )

    spawn_robot2_arg = DeclareLaunchArgument(
        'spawn_robot2',
        default_value='false',
        description='Spawn the second robot. Disabled by default because this launch runs a single Nav2 stack.',
    )

    spawn_robot2 = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=[
            '-entity', 'robot2',
            '-file', os.path.join(local_models, 'serving_robot', 'model.sdf'), 
            '-x', '8.132760', '-y', '-1.000040', '-z', '0.3',
            '-robot_namespace', 'robot2',
        ],
        condition=IfCondition(LaunchConfiguration('spawn_robot2')),
        output='screen',
    )

    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('llm_serving_gazebo'),
                'launch',
                'navigation.launch.py',
            ])
        ]),
        launch_arguments={
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'map': os.path.join(pkg_share, 'maps', 'roborestaurant_static_003.yaml'),
            'params_file': os.path.join(pkg_share, 'config', 'nav2_params.yaml'),
        }.items(),
        condition=IfCondition(LaunchConfiguration('start_nav2')),
    )

    safety_controller = Node(
        package='llm_serving_gazebo',
        executable='safety_controller_node',
        name='safety_controller_node',
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'cmd_vel_in': 'cmd_vel',
            'cmd_vel_out': 'cmd_vel_safe',
            'scan_topic': 'scan',
            'min_distance': 0.35,
            'clear_distance': 0.45,
            'front_angle_deg': 90.0,
            'scan_timeout_sec': 1.0,
            'cmd_timeout_sec': 0.8,
            'safety_status_topic': 'safety_status',
            'emergency_stop_service': 'emergency_stop',
        }],
    )

    move_server = Node(
        package='llm_serving_gazebo',
        executable='move_action_server',
        name='move_action_server',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
    )

    return LaunchDescription([
        gazebo_model_path,
        world_arg,
        use_sim_time,
        start_nav2,
        spawn_robot2_arg,
        gazebo,
        spawn_robot1,
        spawn_robot2,
        nav2,
        safety_controller,
        move_server,
    ])
