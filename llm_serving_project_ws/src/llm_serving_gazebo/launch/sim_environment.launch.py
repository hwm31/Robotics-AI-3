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

    spawn_robot2_arg = DeclareLaunchArgument(
        'spawn_robot2',
        default_value='false',
        description=(
            'Spawn robot2. Keep false for the single-Nav2 demo to avoid TF '
            'frame collisions.'
        ),
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
    
    # === 로봇 1 스폰 ===
    spawn_robot1 = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=[
            '-entity', 'robot1',  # 엔티티 이름: robot1
            '-file', os.path.join(local_models, 'serving_robot', 'model.sdf'),
            '-x', '-7.451785', '-y', '-6.672494', '-z', '0.3',  # 로봇 1 시작 위치
            '-robot_namespace', 'robot1',          # 네임스페이스 분리
            '-timeout', '60.0',
        ],
        output='screen',
    )

    # === 로봇 2 스폰 ===
    spawn_robot2 = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=[
            '-entity', 'robot2',  # 엔티티 이름: robot2
            '-file', os.path.join(local_models, 'serving_robot', 'model.sdf'), 
            '-x', ' 8.132760', '-y', '-1.000040', '-z', '0.3',  # 로봇 2 시작 위치
            '-robot_namespace', 'robot2',          # 네임스페이스 분리
            '-timeout', '60.0',
        ],
        output='screen',
        condition=IfCondition(LaunchConfiguration('spawn_robot2')),
    )

    base_to_link_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        arguments=[
            '0', '0', '0',
            '0', '0', '0',
            'base_footprint', 'base_link',
        ],
        output='screen',
    )

    link_to_scan_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        arguments=[
            '-0.032', '0', '0.171',
            '0', '0', '0',
            'base_link', 'base_scan',
        ],
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
        }.items(),
        condition=IfCondition(LaunchConfiguration('start_nav2')),
    )

    # === [로봇 1 제어 노드들] ===
    safety_robot1 = Node(
        package='llm_serving_gazebo',
        executable='safety_controller_node',
        namespace='robot1',  # [핵심] robot1 네임스페이스 추가
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'cmd_vel_in': '/cmd_vel',
            'cmd_vel_out': 'cmd_vel',
            'min_distance': 0.35,
            'clear_distance': 0.45,
            'front_angle_deg': 90.0,
            'scan_timeout_sec': 1.0,
            'cmd_timeout_sec': 0.8,
            'safety_status_topic': 'safety_status',
            'emergency_stop_service': 'emergency_stop',
        }],
    )

    action_robot1 = Node(
        package='llm_serving_gazebo',
        executable='move_action_server',
        namespace='robot1',  # [핵심] robot1 네임스페이스 추가
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'nav_action_name': '/navigate_to_pose',
        }],
    )

    # === [로봇 2 제어 노드들] ===
    safety_robot2 = Node(
        package='llm_serving_gazebo',
        executable='safety_controller_node',
        namespace='robot2',  # [핵심] robot2 네임스페이스 추가
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'cmd_vel_in': 'cmd_vel',
            'cmd_vel_out': 'cmd_vel_safe',
            'min_distance': 0.35,
            'clear_distance': 0.45,
            'front_angle_deg': 90.0,
            'scan_timeout_sec': 1.0,
            'cmd_timeout_sec': 0.8,
            'safety_status_topic': 'safety_status',
            'emergency_stop_service': 'emergency_stop',
        }],
        condition=IfCondition(LaunchConfiguration('spawn_robot2')),
    )

    action_robot2 = Node(
        package='llm_serving_gazebo',
        executable='move_action_server',
        namespace='robot2',  # [핵심] robot2 네임스페이스 추가
        output='screen',
        parameters=[{
            'use_sim_time': LaunchConfiguration('use_sim_time'),
            'nav_action_name': '/navigate_to_pose',
        }],
        condition=IfCondition(LaunchConfiguration('spawn_robot2')),
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
        base_to_link_tf,
        link_to_scan_tf,
        safety_robot1,  # 기존 safety_controller 대신 교체
        action_robot1,  # 기존 move_server 대신 교체
        safety_robot2,  # 로봇 2용 추가
        action_robot2,  # 로봇 2용 추가
    ])
