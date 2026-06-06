from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='llm_serving_core',
            executable='user_input_node',
            name='user_input_node',
            output='screen',
        ),
        Node(
            package='llm_serving_core',
            executable='llm_agent_node',
            name='llm_agent_node',
            output='screen',
        ),
        Node(
            package='llm_serving_core',
            executable='task_executor_node',
            name='task_executor_node',
            output='screen',
        ),
        Node(
            package='llm_serving_core',
            executable='robot_state_node',
            name='robot_state_node',
            output='screen',
        ),
        Node(
            package='llm_serving_core',
            executable='table_state_node',
            name='table_state_node',
            output='screen',
        ),
    ])
