"""Jediný entrypoint R-MODUS — spouští rmodus_* + bringup.extras podle profilu."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory

import os
import yaml

from rmodus_bringup.package_gates import missing_packages, package_available, skip_log


_DEFAULT_BRINGUP = {
    "config": True,
    "chassis": True,
    "description": True,
    "hw": True,
    "uart_output": True,
    "estop": True,
    "bumper": True,
    "cliff": True,
    "flow": True,
    "display": True,
    "web": True,
    "rviz": False,
    "sim": False,
    "localization": True,
    "navigation": True,
    "slam": True,
    "rf2o": False,
    "obstacle_cloud": True,
    "microros": False,
    "cmd_mux": True,
}

# bringup flag → ROS package that must exist to include
_OPTIONAL_RM_PKGS = {
    "config": "rmodus_config",
    "chassis": "rmodus_chassis",
    "description": "rmodus_description",
    "hw": "rmodus_hw",
    "uart_output": "rmodus_uart_output",
    "estop": "rmodus_estop",
    "bumper": "rmodus_bumper",
    "cliff": "rmodus_cliff_sensor",
    "flow": "rmodus_flow_sensor",
    "display": "rmodus_display",
    "web": "rmodus_web",
    "localization": "rmodus_localization",
    "navigation": "rmodus_navigation",
    "sim": "rmodus_gazebo",
}


def _resolve(path: str) -> str:
    if not path:
        return ""
    return os.path.normpath(os.path.expanduser(str(path).strip()))


def _as_bool(value) -> bool:
    """YAML bool i text. bool('false') je v Pythonu True — to by zapnulo vypnuté moduly."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in ("1", "true", "yes", "on", "y")


def _configs_root_from_profile(path: str) -> str:
    """…/configs/profiles/foo.yaml → …/configs. Jinak prázdné."""
    if not path:
        return ""
    parent = os.path.dirname(path)
    if os.path.basename(parent) == "profiles":
        return os.path.dirname(parent)
    return ""


def _microros_summary(path: str) -> str:
    if not path or not os.path.isfile(path):
        return "soubor chybi"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            root = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        return f"YAML chyba: {exc}"
    block = root.get("microros", {}) if isinstance(root, dict) else {}
    if not isinstance(block, dict):
        return "microros neni slovnik"
    if not _as_bool(block.get("enabled", True)):
        return "microros.enabled=false"
    items = block.get("items")
    parts = []
    if isinstance(items, list):
        for raw in items:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "?").strip() or "?"
            if not _as_bool(raw.get("enabled", True)):
                parts.append(f"{name} vypnuto")
                continue
            device = str(raw.get("device") or "").strip() or "(prazdne device)"
            baud = raw.get("baudrate") or 115200
            transport = str(raw.get("transport") or "serial").strip()
            parts.append(f"{name} {transport} {device} @ {baud}")
    elif block.get("device"):
        parts.append(
            f"{block.get('name') or 'serial'} {block.get('transport') or 'serial'} "
            f"{block.get('device')} @ {block.get('baudrate') or 115200}"
        )
    return ", ".join(parts) if parts else "zadne items"


def _load_bringup(path: str) -> dict:
    cfg = dict(_DEFAULT_BRINGUP)
    if not path or not os.path.isfile(path):
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    if not isinstance(root, dict):
        return cfg
    block = root.get("bringup", {})
    if not isinstance(block, dict):
        return cfg
    for key in cfg:
        if key in block:
            cfg[key] = _as_bool(block[key])
    # legacy: bringup.autonomy.*
    auto = block.get("autonomy", {})
    if isinstance(auto, dict):
        for key in ("localization", "navigation", "slam", "rf2o", "obstacle_cloud"):
            if key in auto:
                cfg[key] = _as_bool(auto[key])
    return cfg


def _load_extras(path: str) -> list:
    """bringup.extras: list of {package, launch, args?} or {path, args?}."""
    if not path or not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        root = yaml.safe_load(f) or {}
    if not isinstance(root, dict):
        return []
    block = root.get("bringup", {})
    if not isinstance(block, dict):
        return []
    extras = block.get("extras", [])
    if not isinstance(extras, list):
        return []
    return [e for e in extras if isinstance(e, dict)]


def _stringify_launch_args(raw_args, robot_yaml: str) -> dict:
    if not isinstance(raw_args, dict):
        return {}
    out = {}
    for key, value in raw_args.items():
        if value is None:
            continue
        text = str(value).strip()
        if text == "$robot_yaml":
            text = robot_yaml
        out[str(key)] = text
    return out


def _flag(v: bool) -> str:
    return "true" if v else "false"


def _build(context):
    robot_yaml = _resolve(LaunchConfiguration("robot_yaml").perform(context))
    if not robot_yaml:
        robot_yaml = os.path.join(
            get_package_share_directory("rmodus_bringup"), "config", "rmodus.yaml"
        )

    if not os.path.isfile(robot_yaml):
        missing_profile = True
    else:
        missing_profile = False
    b = _load_bringup(robot_yaml)
    extras = _load_extras(robot_yaml)
    enabled = [key for key, value in b.items() if value]
    extra_labels = []
    for entry in extras:
        label = str(entry.get("package") or entry.get("path") or "?").strip() or "?"
        state = "true" if _as_bool(entry.get("enabled", True)) else "false"
        extra_labels.append(f"{label}={state}")
    actions = [
        LogInfo(msg=f"[rmodus_bringup] profile={robot_yaml}"),
        LogInfo(
            msg="[rmodus_bringup] soubor chybi, flags jsou vychozi"
            if missing_profile
            else f"[rmodus_bringup] zapnuto: {', '.join(enabled) or '(nic)'}"
        ),
        LogInfo(msg=f"[rmodus_bringup] microros: {_microros_summary(robot_yaml)}"),
        LogInfo(
            msg="[rmodus_bringup] extras: "
            + (", ".join(extra_labels) if extra_labels else "(zadne)")
        ),
    ]

    def _include(pkg: str, launch_file: str, **launch_arguments):
        return IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                PathJoinSubstitution([FindPackageShare(pkg), "launch", launch_file])
            ),
            launch_arguments=launch_arguments.items(),
        )

    def _try_feature(flag: str, pkg: str, launch_file: str, **launch_arguments):
        if not b.get(flag, False):
            return
        if not package_available(pkg):
            actions.append(skip_log(flag, pkg))
            return
        actions.append(_include(pkg, launch_file, **launch_arguments))

    def _try_extra(entry: dict, index: int) -> None:
        label = str(entry.get("package") or entry.get("path") or f"extras[{index}]").strip()
        label = label or f"extras[{index}]"
        if not _as_bool(entry.get("enabled", True)):
            actions.append(LogInfo(msg=f"[rmodus] skip '{label}': enabled is false"))
            return
        launch_args = _stringify_launch_args(entry.get("args"), robot_yaml)
        abs_path = _resolve(str(entry.get("path") or ""))
        if abs_path:
            if not os.path.isfile(abs_path):
                actions.append(
                    LogInfo(
                        msg=(
                            f"[rmodus] skip '{label}': launch file not found: {abs_path}"
                        )
                    )
                )
                return
            actions.append(
                IncludeLaunchDescription(
                    PythonLaunchDescriptionSource(abs_path),
                    launch_arguments=launch_args.items(),
                )
            )
            actions.append(LogInfo(msg=f"[rmodus_bringup] extras include path={abs_path}"))
            return

        pkg = str(entry.get("package") or "").strip()
        launch_file = str(entry.get("launch") or "").strip()
        if not pkg or not launch_file:
            actions.append(
                LogInfo(
                    msg=(
                        f"[rmodus] skip '{label}': need package+launch or path "
                        f"(got package={pkg!r} launch={launch_file!r})"
                    )
                )
            )
            return
        if not package_available(pkg):
            actions.append(skip_log(f"{label}/{pkg}", pkg))
            return
        share = get_package_share_directory(pkg)
        full = os.path.join(share, "launch", launch_file)
        if not os.path.isfile(full):
            actions.append(
                LogInfo(
                    msg=(
                        f"[rmodus] skip '{label}': {pkg}/launch/{launch_file} not found"
                    )
                )
            )
            return
        actions.append(_include(pkg, launch_file, **launch_args))
        actions.append(
            LogInfo(msg=f"[rmodus_bringup] extras include {pkg}/launch/{launch_file}")
        )

    # TF: one RSP — description composes chassis when both enabled and present.
    want_desc = b["description"]
    want_chassis = b["chassis"]
    if want_desc:
        if package_available("rmodus_description"):
            include_chassis = want_chassis and package_available("rmodus_chassis")
            if want_chassis and not include_chassis:
                actions.append(skip_log("chassis", "rmodus_chassis"))
            actions.append(
                _include(
                    "rmodus_description",
                    "description.launch.py",
                    use_sim_time="false",
                    robot_config_file=robot_yaml,
                    override_config_path=robot_yaml,
                    include_chassis=_flag(include_chassis),
                )
            )
        else:
            actions.append(skip_log("description", "rmodus_description"))
            if want_chassis:
                _try_feature(
                    "chassis",
                    "rmodus_chassis",
                    "chassis.launch.py",
                    use_sim_time="false",
                    robot_config_file=robot_yaml,
                )
    elif want_chassis:
        _try_feature(
            "chassis",
            "rmodus_chassis",
            "chassis.launch.py",
            use_sim_time="false",
            robot_config_file=robot_yaml,
        )

    # Drive (cmd_vel -> wheel units) runs independently of which launch owns the chassis TF.
    if want_chassis and package_available("rmodus_chassis"):
        ekf_runs = (
            b["localization"]
            and package_available("rmodus_localization")
            and package_available("robot_localization")
        )
        actions.append(
            _include(
                "rmodus_chassis",
                "drive.launch.py",
                robot_config_file=robot_yaml,
                publish_tf=_flag(not ekf_runs),
            )
        )

    _try_feature("hw", "rmodus_hw", "hw.launch.py", user_params_file=robot_yaml)
    _try_feature(
        "uart_output", "rmodus_uart_output", "uart_output.launch.py", config_file=robot_yaml
    )
    _try_feature("estop", "rmodus_estop", "estop.launch.py", config_file=robot_yaml)
    _try_feature("cmd_mux", "rmodus_bringup", "cmd_mux.launch.py", config_file=robot_yaml)
    # Agent musi bezet driv, nez ESP zacne publikovat /robot/bumpers/state.
    _try_feature("microros", "rmodus_bringup", "microros.launch.py", config_file=robot_yaml)
    _try_feature("bumper", "rmodus_bumper", "bumper.launch.py", config_file=robot_yaml)
    _try_feature(
        "cliff", "rmodus_cliff_sensor", "cliff_sensor.launch.py", config_file=robot_yaml
    )
    _try_feature(
        "flow", "rmodus_flow_sensor", "flow_sensor.launch.py", config_file=robot_yaml
    )
    _try_feature("display", "rmodus_display", "display.launch.py", config_file=robot_yaml)
    # Profile manager before web so /rmodus/config/* services exist for UI.
    # Stejný strom jako robot_yaml (…/configs), ne odhad z $HOME.
    configs_root = _configs_root_from_profile(robot_yaml)
    if configs_root:
        _try_feature(
            "config",
            "rmodus_config",
            "config.launch.py",
            configs_root=configs_root,
        )
    else:
        _try_feature("config", "rmodus_config", "config.launch.py")
    _try_feature("web", "rmodus_web", "web.launch.py", robot_yaml=robot_yaml)

    if b["localization"] or b["slam"] or b["rf2o"] or b["obstacle_cloud"]:
        if package_available("rmodus_localization"):
            actions.append(
                _include(
                    "rmodus_localization",
                    "localization.launch.py",
                    use_sim_time="false",
                    robot_config_file=robot_yaml,
                    global_params_file=robot_yaml,
                    localization=_flag(b["localization"]),
                    slam=_flag(b["slam"]),
                    rf2o=_flag(b["rf2o"]),
                    obstacle_cloud=_flag(b["obstacle_cloud"]),
                )
            )
        else:
            actions.append(skip_log("localization", "rmodus_localization"))

    if b["navigation"]:
        if package_available("rmodus_navigation"):
            actions.append(
                _include(
                    "rmodus_navigation",
                    "navigation.launch.py",
                    use_sim_time="false",
                    robot_yaml=robot_yaml,
                    navigation="true",
                )
            )
        else:
            actions.append(skip_log("navigation", "rmodus_navigation"))

    if b["sim"]:
        if package_available("rmodus_gazebo"):
            gz_missing = missing_packages(["ros_gz_sim", "ros_gz_bridge"])
            if gz_missing:
                actions.append(skip_log("sim/gazebo-runtime", gz_missing))
            else:
                actions.append(
                    LogInfo(
                        msg=(
                            "[rmodus_bringup] bringup.sim=true: rmodus_gazebo is present, "
                            "but sim launch wiring is still reserved (not started yet)."
                        )
                    )
                )
        else:
            actions.append(skip_log("sim", "rmodus_gazebo"))

    if b["rviz"]:
        if package_available("rviz2"):
            actions.append(_include("rmodus_bringup", "rviz.launch.py", use_sim_time="false"))
        else:
            actions.append(skip_log("rviz", "rviz2"))

    # User / third-party launches. enabled: false polozku preskoci, definice zustava.
    for i, entry in enumerate(extras):
        _try_extra(entry, i)

    return actions


def generate_launch_description():
    pkg_share = FindPackageShare("rmodus_bringup")
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "robot_yaml",
                default_value=PathJoinSubstitution([pkg_share, "config", "rmodus.yaml"]),
                description="Profil s bringup: + extras + /**/ros__parameters",
            ),
            OpaqueFunction(function=_build),
        ]
    )
