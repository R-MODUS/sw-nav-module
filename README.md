# R-MODUS nav module

## Spuštění

```bash
ros2 launch rmodus_bringup rmodus.launch.py
# aktivní profil na Pi (stejná logika jako entrypoint):
ros2 launch rmodus_bringup rmodus.launch.py \
  robot_yaml:=$HOME/rmodus/configs/profiles/$(tr -d '[:space:]' < $HOME/rmodus/configs/active).yaml
```

Na robotovi `rmodus.service` spouští totéž s aktivním souborem z `~/rmodus/configs/profiles/` (ukazatel `active`).
- `boot.rmodus` v robot profilu; `boot.network` v `network.yaml`
- co běží z bringupu: top-level `bringup:`

Přepnutí: web UI Profily (ROS services `/rmodus/config/*`), nebo
`ros2 run rmodus_config rmodus_config activate <name>`, pak `sudo systemctl restart rmodus`.

Services (node `config_manager`, `bringup.config: true`):

```bash
ros2 service call /rmodus/config/list rmodus_interface/srv/ListProfiles {}
ros2 service call /rmodus/config/activate rmodus_interface/srv/ActivateProfile "{name: demo}"
```

Co se spustí řídí **jen** top-level `bringup:` v profilu (`rmodus_bringup/config/rmodus.yaml`).  
Druhá vrstva: `*.enabled` v blocích modulů (node + TF + EKF).

Chybí-li volitelný balíček na disku (např. `rmodus_bumper`, Nav2, rf2o), launch ho **přeskočí s logem** — nespadne celý bringup.

`rosdep` / `package.xml` **netáhne** těžké optional deps. Optional jsou zapsané v `<export><rmodus><optional_depend>…`.

Kanonický ROS blok (`bringup:` + `/**`) musí sedět se `sw-install/examples/rmodus-example.yaml` (ten má navíc `meta` / `web` / `boot.rmodus`). Síť je v `network.yaml`.

## Balíčky (orientace)

| Balíček | Role |
|---|---|
| `rmodus_bringup` | profil + `rmodus.launch.py` |
| `rmodus_config` | profile services (list/get/save/create/delete/activate) |
| `rmodus_chassis` | host `base_link` |
| `rmodus_description` | sada `rmodus_mount` + imu/lidar TF |
| `rmodus_localization` | EKF + optional rf2o/slam + obstacle_cloud |
| `rmodus_navigation` | Nav2 (optional debs) |
| `rmodus_bumper` / `cliff` / `flow` / `display` / … | feature moduly (optional vůči bringup) |

## TF model

- **Host**: `base_footprint` → `base_link`
- **Sada**: `base_link` → `rmodus_mount` → volitelné imu/lidar  
  Při `bringup.chassis` + `description` → jeden URDF/RSP.
