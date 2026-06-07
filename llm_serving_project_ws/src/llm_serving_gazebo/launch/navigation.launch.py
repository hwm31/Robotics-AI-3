import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    gazebo_share = get_package_share_directory('llm_serving_gazebo')
    nav2_share = get_package_share_directory('nav2_bringup')

    default_map = os.path.join(gazebo_share, 'maps', 'map.yaml')
    default_params = os.path.join(gazebo_share, 'config', 'nav2_params.yaml')
    bringup_launch = os.path.join(nav2_share, 'launch', 'bringup_launch.py')

    use_sim_time = LaunchConfiguration('use_sim_time')
    return LaunchDescription([
        DeclareLaunchArgument(
            'use_sim_time',
            default_value='true',
            description='Use Gazebo simulation time.',
        ),
        DeclareLaunchArgument(
            'map',
            default_value=default_map,
            description='Map yaml file for Nav2 localization.',
        ),
        DeclareLaunchArgument(
            'params_file',
            default_value=default_params,
            description='Nav2 parameter file.',
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(bringup_launch),
            launch_arguments={
                'map': default_map,
                'use_sim_time': use_sim_time,
                'params_file': default_params,
                'slam': 'False',
                'autostart': 'True',
                'use_composition': 'False',
            }.items(),
        ),
    ])
