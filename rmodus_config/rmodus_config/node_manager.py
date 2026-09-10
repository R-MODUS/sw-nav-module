"""ROS node: profile CRUD + network config + system restart."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger

from rmodus_interface.srv import (
    ActivateProfile,
    CreateProfile,
    DeleteProfile,
    GetNetworkConfig,
    GetProfile,
    ListProfiles,
    RenameProfile,
    SaveProfile,
    SetNetworkConfig,
)

from rmodus_config.network_store import (
    network_public_view,
    read_network_doc,
    schedule_network_apply,
    write_network_doc,
)
from rmodus_config.store import (
    ConfigPaths,
    create_profile,
    delete_profile,
    ensure_layout,
    list_profiles,
    load_paths_file,
    profile_path,
    read_active_name,
    read_profile_text,
    rename_profile,
    resolve_active_profile,
    set_active,
    write_profile_text,
    validate_profile_name,
)


def _load_paths(node: Node) -> ConfigPaths:
    share = Path(get_package_share_directory("rmodus_config")) / "config" / "paths.yaml"
    root = node.declare_parameter("configs_root", "").get_parameter_value().string_value
    paths_yaml = node.declare_parameter("paths_yaml", str(share)).get_parameter_value().string_value
    if paths_yaml and Path(paths_yaml).is_file():
        paths = load_paths_file(Path(paths_yaml))
    else:
        paths = ConfigPaths.from_root()
    if root.strip():
        paths = ConfigPaths.from_root(Path(root.strip()))
    ensure_layout(paths)
    return paths


def _schedule_rmodus_restart(delay_sec: float = 1.5) -> None:
    """Detach so restart survives this process dying with the service."""
    delay = max(0.5, float(delay_sec))
    cmd = (
        f"sleep {delay:.1f}; "
        "sudo -n /usr/bin/systemctl restart rmodus.service"
    )
    subprocess.Popen(
        ["bash", "-c", cmd],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


class ConfigManagerNode(Node):
    def __init__(self) -> None:
        super().__init__("rmodus_config_manager")
        self._paths = _load_paths(self)
        qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            history=HistoryPolicy.KEEP_LAST,
        )
        self._pub_name = self.create_publisher(String, "/rmodus/config/active_name", qos)
        self._pub_path = self.create_publisher(String, "/rmodus/config/active_path", qos)

        self.create_service(ListProfiles, "/rmodus/config/list", self._on_list)
        self.create_service(GetProfile, "/rmodus/config/get", self._on_get)
        self.create_service(SaveProfile, "/rmodus/config/save", self._on_save)
        self.create_service(CreateProfile, "/rmodus/config/create", self._on_create)
        self.create_service(DeleteProfile, "/rmodus/config/delete", self._on_delete)
        self.create_service(RenameProfile, "/rmodus/config/rename", self._on_rename)
        self.create_service(ActivateProfile, "/rmodus/config/activate", self._on_activate)
        self.create_service(Trigger, "/rmodus/config/reload", self._on_reload)
        self.create_service(Trigger, "/rmodus/system/restart", self._on_restart)
        self.create_service(GetNetworkConfig, "/rmodus/network/get", self._on_network_get)
        self.create_service(SetNetworkConfig, "/rmodus/network/set", self._on_network_set)
        self.create_service(Trigger, "/rmodus/network/apply", self._on_network_apply)

        self._publish()
        self.get_logger().info(
            f"configs_root={self._paths.root} profiles={self._paths.profiles_dir} "
            f"network={self._paths.network_yaml}"
        )

    def _publish(self) -> None:
        name = read_active_name(self._paths) or ""
        msg_n = String()
        msg_n.data = name
        self._pub_name.publish(msg_n)
        msg_p = String()
        try:
            msg_p.data = str(resolve_active_profile(self._paths))
        except FileNotFoundError:
            msg_p.data = ""
        self._pub_path.publish(msg_p)

    def _on_reload(self, _req, res):
        try:
            self._publish()
            res.success = True
            res.message = read_active_name(self._paths) or ""
        except Exception as exc:  # noqa: BLE001
            res.success = False
            res.message = str(exc)
        return res

    def _on_restart(self, _req, res):
        try:
            probe = subprocess.run(
                ["sudo", "-n", "/usr/bin/systemctl", "cat", "rmodus.service"],
                capture_output=True,
                text=True,
                check=False,
            )
            if probe.returncode != 0:
                detail = (probe.stderr or probe.stdout or "").strip() or f"rc={probe.returncode}"
                lower = detail.lower()
                if "password" in lower:
                    detail = (
                        "chybí passwordless sudo pro systemctl "
                        "(install → /etc/sudoers.d/rmodus-restart)"
                    )
                res.success = False
                res.message = detail
                return res
            _schedule_rmodus_restart()
            res.success = True
            res.message = "Restart rmodus.service naplánován (~1.5 s)."
            self.get_logger().warn(res.message)
        except Exception as exc:  # noqa: BLE001
            res.success = False
            res.message = str(exc)
        return res

    def _on_list(self, _req, res):
        try:
            active = read_active_name(self._paths) or ""
            res.names = list_profiles(self._paths)
            res.active = active
            res.configs_root = str(self._paths.root)
            res.profiles_dir = str(self._paths.profiles_dir)
            res.success = True
            res.message = ""
        except Exception as exc:  # noqa: BLE001
            res.names = []
            res.active = ""
            res.configs_root = str(self._paths.root)
            res.profiles_dir = str(self._paths.profiles_dir)
            res.success = False
            res.message = str(exc)
        return res

    def _on_get(self, req, res):
        try:
            content = read_profile_text(self._paths, req.name)
            path = profile_path(self._paths, req.name)
            res.name = req.name
            res.content = content
            res.path = str(path)
            res.active = req.name == read_active_name(self._paths)
            res.success = True
            res.message = ""
        except Exception as exc:  # noqa: BLE001
            res.name = req.name
            res.content = ""
            res.path = ""
            res.active = False
            res.success = False
            res.message = str(exc)
        return res

    def _on_save(self, req, res):
        try:
            path = write_profile_text(self._paths, req.name, req.content)
            res.name = req.name
            res.path = str(path)
            res.success = True
            res.message = ""
            self._publish()
        except Exception as exc:  # noqa: BLE001
            res.name = req.name
            res.path = ""
            res.success = False
            res.message = str(exc)
        return res

    def _on_create(self, req, res):
        try:
            source = (req.source or "").strip() or None
            content = req.content if (req.content or "").strip() else None
            path = create_profile(
                self._paths,
                req.name,
                source=source,
                content=content,
            )
            res.name = req.name
            res.path = str(path)
            res.success = True
            res.message = ""
            self._publish()
        except Exception as exc:  # noqa: BLE001
            res.name = req.name
            res.path = ""
            res.success = False
            res.message = str(exc)
        return res

    def _on_delete(self, req, res):
        try:
            delete_profile(self._paths, req.name)
            res.name = req.name
            res.success = True
            res.message = ""
            self._publish()
        except Exception as exc:  # noqa: BLE001
            res.name = req.name
            res.success = False
            res.message = str(exc)
        return res

    def _on_rename(self, req, res):
        try:
            path = rename_profile(self._paths, req.old_name, req.new_name)
            new_n = validate_profile_name(req.new_name)
            res.old_name = req.old_name
            res.new_name = new_n
            res.path = str(path)
            res.active = read_active_name(self._paths) == new_n
            res.success = True
            res.message = ""
            self._publish()
        except Exception as exc:  # noqa: BLE001
            res.old_name = req.old_name
            res.new_name = req.new_name
            res.path = ""
            res.active = False
            res.success = False
            res.message = str(exc)
        return res

    def _on_activate(self, req, res):
        try:
            path = set_active(self._paths, req.name)
            res.active = req.name
            res.path = str(path)
            res.success = True
            res.message = "Aktivní na disku; restartuj rmodus.service pro načtení bringupu."
            self._publish()
        except Exception as exc:  # noqa: BLE001
            res.active = ""
            res.path = ""
            res.success = False
            res.message = str(exc)
        return res

    def _on_network_get(self, _req, res):
        try:
            doc = read_network_doc(self._paths)
            res.config_json = json.dumps(network_public_view(doc), ensure_ascii=False)
            res.path = str(self._paths.network_yaml)
            res.success = True
            res.message = ""
        except Exception as exc:  # noqa: BLE001
            res.config_json = "{}"
            res.path = str(self._paths.network_yaml)
            res.success = False
            res.message = str(exc)
        return res

    def _on_network_set(self, req, res):
        try:
            payload = json.loads(req.config_json or "{}")
            if not isinstance(payload, dict):
                raise ValueError("config_json musí být JSON objekt")
            path = write_network_doc(self._paths, payload, merge_secrets=True)
            res.path = str(path)
            res.applied = False
            if req.apply:
                schedule_network_apply(path)
                res.applied = True
                res.message = "Uloženo; apply naplánován (~1 s)."
            else:
                res.message = "Uloženo do network.yaml."
            res.success = True
        except Exception as exc:  # noqa: BLE001
            res.path = str(self._paths.network_yaml)
            res.applied = False
            res.success = False
            res.message = str(exc)
        return res

    def _on_network_apply(self, _req, res):
        try:
            bin_path = Path("/usr/local/sbin/rmodus-network")
            if not bin_path.is_file():
                res.success = False
                res.message = f"chybí {bin_path}"
                return res
            schedule_network_apply(self._paths.network_yaml)
            res.success = True
            res.message = "Apply network.yaml naplánován (~1 s)."
            self.get_logger().warn(res.message)
        except Exception as exc:  # noqa: BLE001
            res.success = False
            res.message = str(exc)
        return res


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ConfigManagerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
