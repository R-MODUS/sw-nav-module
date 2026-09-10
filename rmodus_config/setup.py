from glob import glob
from setuptools import find_packages, setup

package_name = "rmodus_config"

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
    description="R-MODUS profile selection and paths.",
    license="TODO: License declaration",
    entry_points={
        "console_scripts": [
            "rmodus_config = rmodus_config.cli:main",
            "config_manager = rmodus_config.node_manager:main",
            "config_status = rmodus_config.node_status:main",
        ],
    },
)
