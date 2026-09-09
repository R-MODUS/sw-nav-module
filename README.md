# Parameter layout after modular HW split.

Active sources:

- `rmodus_description/config/default_robot_config.yaml` — shared TF / EKF model (lidar/IMU contract)
- `rmodus_bringup/config/robot.yaml` — profile passed to bringup (modules + autonomy + web)
- Per-module defaults: `rmodus_bumper`, `rmodus_cliff_sensor`, `rmodus_flow_sensor`, `rmodus_display`, `rmodus_uart_output`
- `rmodus_hw/config/base_params.yaml` — fan / box services only

Optional packages (each: `enabled`, topic, mount_parent_frame, mount_offset, mount_rpy):

- `rmodus_uart_output` — `/cmd_vel_safe` → UART (no kinematics, no `/vector`)
- `rmodus_bumper`, `rmodus_cliff_sensor`, `rmodus_flow_sensor`, `rmodus_display`

Lidar/IMU drivers are **not** part of R-MODUS core.

- Optional vendor package in this repo: `neato_lidar` (`ros2 launch neato_lidar neato_lidar.launch.py`)
- Xsens / other IMUs: install upstream driver separately; profile only sets `topic` + TF
