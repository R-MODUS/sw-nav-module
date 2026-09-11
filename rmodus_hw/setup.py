from setuptools import setup, find_packages
from glob import glob

package_name = "rmodus_hw"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(include=[package_name, package_name + ".*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
        ("share/" + package_name, ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="pi",
    maintainer_email="pi@todo.todo",
    description="Core nav-box services: fan, system monitor, wifi.",
    license="TODO: License declaration",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "get_wifi = rmodus_hw.node_get_wifi:main",
            "system_monitor = rmodus_hw.node_system_monitor:main",
            "fan_control = rmodus_hw.node_fan_control:main",
        ],
    },
)
