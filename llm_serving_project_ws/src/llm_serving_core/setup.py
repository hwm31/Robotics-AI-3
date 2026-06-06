from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'llm_serving_core'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'prompts'), glob('prompts/*')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Robotics AI Team',
    maintainer_email='team@todo.todo',
    description='LLM agent, task executor, and robot state management',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'user_input_node = llm_serving_core.user_input_node:main',
            'llm_agent_node = llm_serving_core.llm_agent_node:main',
            'task_executor_node = llm_serving_core.task_executor_node:main',
            'robot_state_node = llm_serving_core.robot_state_node:main',
            'table_state_node = llm_serving_core.table_state_node:main',
            'greeting_node = llm_serving_core.greeting_node:main',
            'greeting_to_table_node = llm_serving_core.greeting_to_table_node:main',
        ],
    },
)
