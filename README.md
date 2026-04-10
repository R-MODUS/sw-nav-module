# sw-nav-module

ROS 2 navigation workspace for R-Modus packages.

## Parameter Config Migration

The parameter layout was simplified to remove redundant YAML copies.

Active parameter sources are now:

- `rmodus_description/config/robot_config.yaml` for shared robot and sensor model.
- `rmodus_sim/config/robot_config.yaml` for standalone sim package robot model.
- `rmodus_hw/config/base_params.yaml` for HW node default parameters.
- `rmodus_bringup/config/user_params.yaml` for global runtime overrides.

Removed redundant files:

- `rmodus_hw/config/robot_config.yaml`
- `rmodus_bringup/config/base_params.yaml`
- `rmodus_sim/config/base_params.yaml`

If you used any removed file in custom scripts, switch to the active sources listed above.