from setuptools import setup
import os
from glob import glob

package_name = 'llm_serving_gazebo'

setup(
    name=package_name,
    version='0.1.0',
    packages=[],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'worlds'), glob('worlds/*')),
        (os.path.join('share', package_name, 'models', 'serving_robot'),
         glob('models/serving_robot/*')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Robotics AI Team',
    maintainer_email='team@todo.todo',
    description='Gazebo simulation for LLM serving robot',
    license='MIT',
    tests_require=['pytest'],
    scripts=[
        'scripts/safety_controller_node.py',
        'scripts/move_action_server.py',
    ],
)
