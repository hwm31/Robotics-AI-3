import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
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
        ],
        output='screen',
    )

    safety_controller = Node(
        package='llm_serving_gazebo',
        executable='safety_controller_node',
        name='safety_controller_node',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
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
        gazebo,
        spawn_robot1,
        spawn_robot2,
        safety_controller,
        move_server,
    ])
