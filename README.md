# R-MODUS nav module

## Spuštění

```bash
ros2 launch rmodus_bringup rmodus.launch.py
# volitelně:
ros2 launch rmodus_bringup rmodus.launch.py robot_yaml:=/cesta/k/profilu.yaml
```

Co se spustí řídí **jen** top-level `bringup:` v profilu (`rmodus_bringup/config/robot.yaml`).  
Druhá vrstva: `*.enabled` v blocích modulů (node + TF + EKF).

Chybí-li volitelný balíček na disku (např. `rmodus_bumper`, Nav2, rf2o), launch ho **přeskočí s logem** — nespadne celý bringup.

`rosdep` / `package.xml` **netáhne** těžké optional deps. Instalaci profilů řeší `sw_install` (později). Optional jsou zapsané v `<export><rmodus><optional_depend>…`.

## Balíčky (orientace)

| Balíček | Role |
|---|---|
| `rmodus_bringup` | profil + `rmodus.launch.py` |
| `rmodus_chassis` | host `base_link` |
| `rmodus_description` | sada `rmodus_mount` + imu/lidar TF |
| `rmodus_localization` | EKF + optional rf2o/slam + obstacle_cloud |
| `rmodus_navigation` | Nav2 (optional debs) |
| `rmodus_bumper` / `cliff` / `flow` / `display` / … | feature moduly (optional vůči bringup) |

## TF model

- **Host**: `base_footprint` → `base_link`
- **Sada**: `base_link` → `rmodus_mount` → volitelné imu/lidar  
  Při `bringup.chassis` + `description` → jeden URDF/RSP.
