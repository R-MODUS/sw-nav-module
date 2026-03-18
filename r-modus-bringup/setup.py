from setuptools import setup, find_packages
from glob import glob
import os

package_name = 'r-modus-bringup'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(include=[package_name, package_name + '.*']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
	    ('share/' + package_name + '/config', glob('config/*.yaml')),
	    ('share/' + package_name + '/config', glob('config/*.config')),
        ('share/' + package_name + '/config', glob('config/*.rviz')),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
        ('share/' + package_name + '/worlds', glob('worlds/*.world')),
        ('share/' + package_name + '/urdf', glob('urdf/*.xacro')),
        ('share/' + package_name + '/urdf', glob('urdf/*.gazebo')),
        ('share/' + package_name + '/urdf', glob('urdf/*.sdf')),
        ('share/' + package_name + '/scripts', glob('scripts/*.py')),
        ('share/' + package_name + '/meshes', glob('meshes/*.obj')),
        ('share/' + package_name + '/meshes', glob('meshes/*.mtl')),
	    ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='pi',
    maintainer_email='pi@todo.todo',
    description='TODO: Package description',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
        ],
    },
)
