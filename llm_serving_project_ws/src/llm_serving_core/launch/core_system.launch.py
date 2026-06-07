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
        DeclareLaunchArgument('input_mode', default_value='text'),
        DeclareLaunchArgument('speech_language', default_value='ko-KR'),
        DeclareLaunchArgument('voice_trigger_key', default_value='v'),
        DeclareLaunchArgument('model', default_value='gpt-4o-mini'),

        # 1. 관제탑 (Multi-threaded Fleet Manager)
        Node(
            package='llm_serving_core',
            executable='fleet_manager_node',
            name='fleet_manager_node',
            output='screen',
            emulate_tty=True,
        ),
        # 2. LLM 두뇌
        Node(
            package='llm_serving_core',
            executable='llm_agent_node',
            name='llm_agent_node',
            output='screen',
            parameters=[{'model': model}],
        ),
        # 3. 로봇 상태 관리
        Node(
            package='llm_serving_core',
            executable='robot_state_node',
            name='robot_state_node',
            output='screen',
        ),
        # 4. 테이블 상태 관리
        Node(
            package='llm_serving_core',
            executable='table_state_node',
            name='table_state_node',
            output='screen',
        ),
        # 5. [추가] 손님 명령 입력창 (이게 있어야 입력을 하죠!)
        Node(
            package='llm_serving_core',
            executable='user_input_node',
            name='user_input_node',
            output='screen',
            emulate_tty=True,
        ),
    ])