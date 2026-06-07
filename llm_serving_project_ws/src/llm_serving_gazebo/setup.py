from setuptools import find_packages, setup
import os
from glob import glob

package_name = 'llm_serving_gazebo'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'config'), glob('config/*.yaml')),
        (os.path.join('share', package_name, 'worlds'), glob('worlds/*')),
        (os.path.join('share', package_name, 'maps'), glob('maps/*')),
        (os.path.join('share', package_name, 'models', 'serving_robot'),
         glob('models/serving_robot/*')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Robotics AI Team3',
    maintainer_email='ihson127@gachon.ac.kr',
    description='Gazebo simulation for LLM serving robot',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'safety_controller_node = llm_serving_gazebo.safety_controller_node:main',
            'move_action_server = llm_serving_gazebo.move_action_server:main',
        ],
    },
)
