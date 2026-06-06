from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    input_mode = LaunchConfiguration('input_mode')
    speech_language = LaunchConfiguration('speech_language')
    voice_trigger_key = LaunchConfiguration('voice_trigger_key')
    model = LaunchConfiguration('model')

    return LaunchDescription([
        DeclareLaunchArgument(
            'input_mode',
            default_value='text',
            description='Input mode: text, voice, or both',
        ),
        DeclareLaunchArgument(
            'speech_language',
            default_value='ko-KR',
            description='Google STT language code',
        ),
        DeclareLaunchArgument(
            'voice_trigger_key',
            default_value='v',
            description='Push-to-talk key for voice input',
        ),
        DeclareLaunchArgument(
            'model',
            default_value='gpt-4o-mini',
            description='OpenAI model name (API key from .env)',
        ),
        Node(
            package='llm_serving_core',
            executable='user_input_node',
            name='user_input_node',
            output='screen',
            emulate_tty=True,
            parameters=[{
                'input_mode': input_mode,
                'speech_language': speech_language,
                'voice_trigger_key': voice_trigger_key,
            }],
        ),
        Node(
            package='llm_serving_core',
            executable='llm_agent_node',
            name='llm_agent_node',
            output='screen',
            parameters=[{
                'model': model,
            }],
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
