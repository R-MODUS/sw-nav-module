from glob import glob
from pathlib import Path
from setuptools import find_packages, setup

package_name = "rmodus_web"
websocket_root = Path(package_name) / "websocket"
websocket_data_files = []
for directory in sorted(path for path in websocket_root.rglob("*") if path.is_dir()):
    files = [str(path) for path in sorted(directory.glob("*")) if path.is_file()]
    if files:
        install_dir = str(Path("share") / package_name / directory.as_posix().split("/", 1)[1])
        websocket_data_files.append((install_dir, files))

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(include=[package_name, package_name + ".*"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name + "/launch", glob("launch/*.py")),
        ("share/" + package_name + "/websocket", [str(websocket_root / "index.html")]),
        ("share/" + package_name, ["package.xml"]),
    ] + websocket_data_files,
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="pi",
    maintainer_email="pi@todo.todo",
    description="Web UI bridge package for R-Modus.",
    license="TODO: License declaration",
    extras_require={"test": ["pytest"]},
    entry_points={
        "console_scripts": [
            "websocket = rmodus_web.node_websocket:run",
        ],
    },
)
