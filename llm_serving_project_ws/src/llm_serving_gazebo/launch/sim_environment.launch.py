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

    spawn_robot = Node(
        package='gazebo_ros',
        executable='spawn_entity.py',
        arguments=[
            '-entity', 'serving_robot',
            '-file', os.path.join(local_models, 'serving_robot', 'model.sdf'),
            '-x', '0.0', '-y', '0.0', '-z', '0.1',
        ],
        output='screen',
    )

    safety_controller = Node(
        package='llm_serving_gazebo',
        executable='safety_controller_node.py',
        name='safety_controller_node',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
    )

    move_server = Node(
        package='llm_serving_gazebo',
        executable='move_action_server.py',
        name='move_action_server',
        output='screen',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
    )

    return LaunchDescription([
        gazebo_model_path,
        world_arg,
        use_sim_time,
        gazebo,
        spawn_robot,
        safety_controller,
        move_server,
    ])
