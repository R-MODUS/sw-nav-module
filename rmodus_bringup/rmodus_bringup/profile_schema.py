"""Konstanty profilu R-MODUS.

Ostatní kód je importuje. Seznamy bloků se jinde neopisují.
"""

# Kořen uživatelského YAML. Všechno ostatní patří do ros__parameters.
ROOT_KEYS = ("meta", "boot", "bringup", "web", "microros")

PARAM_BLOCKS = (
    "base_link",
    "rmodus_module",
    "drive",
    "wheel_odom",
    "lidar_odom",
    "imu",
    "lidar",
    "map",
    "cmd_mux",
    "estop",
    "flow_sensor",
    "bumpers",
    "cliff_sensors",
    "display",
    "parts",
)

# Legacy jméno se bere jako stejný blok, ne jako neznámý klíč.
PARAM_ALIASES = {"nav_module": "rmodus_module"}

# Klíč bringup.* → blok v parametrech. Oba směry jsou varování, ne chyba.
BRINGUP_PAIRS = (
    ("bumper", "bumpers"),
    ("cliff", "cliff_sensors"),
    ("flow", "flow_sensor"),
    ("display", "display"),
    ("cmd_mux", "cmd_mux"),
)

# V simulaci launch těmto blokům hardware stejně nastaví na false.
SIM_IGNORES_HARDWARE = ("cliff_sensors", "flow_sensor")

# Povinné vždy.
REQUIRED_ROOT = ("bringup",)

# Když je bringup.<flag> pravda (nebo chybí a výchozí v launchi je pravda),
# musí existovat tyto bloky. chassis výchozí je true.
REQUIRED_WHEN = {
    "chassis": ("base_link", "drive"),
}

ITEM_BLOCKS = ("bumpers", "cliff_sensors")

NAME_RE = r"^[a-z][a-z0-9_]*$"

# Povolená pole položky nárazníku a cliffu. U ostatních bloků se pole nekontrolují.
ITEM_FIELDS = (
    "name",
    "label",
    "enabled",
    "pin",
    "topic",
    "frame_id",
    "mount_parent_frame",
    "mount_offset",
    "mount_rpy",
    "size",
    "contact_offset",
    "contact_rpy",
    "beam_offset",
    "beam_rpy",
    "visualize",
    "update_rate",
    "range_min",
    "range_max",
)

# size u položky. Klíč je blok z ITEM_BLOCKS.
ITEM_SIZE_LEN = {
    "bumpers": 3,
    "cliff_sensors": 3,
}

# mount_offset je povinný. Ostatní vektory se kontrolují, jen když v položce jsou.
ITEM_VECTOR_LEN = 3
ITEM_REQUIRED_VECTORS = ("mount_offset",)
ITEM_OPTIONAL_VECTORS = ("mount_rpy", "beam_offset", "beam_rpy")

# Stejné výchozí flagy, jako používá rmodus.launch.py.
# Chybějící bringup.<flag> se bere odtud.
DEFAULT_BRINGUP = {
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
    "sim_gui": False,
    "localization": True,
    "navigation": True,
    "slam": True,
    "rf2o": False,
    "obstacle_cloud": True,
    "microros": False,
    "cmd_mux": True,
}
