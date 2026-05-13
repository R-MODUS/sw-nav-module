# Rosdep a systémové závislosti (R-Modus / sw-nav-module)

Tento dokument shrnuje **ROS 2 balíčky** a **Python/systémové závislosti** potřebné pro strom `package.xml` v tomto repozitáři. Cíl je, aby `rosdep install` na cílovém systému (typicky Ubuntu + ROS 2 Jazzy) doinstalovalo co nejvíc automaticky.

## Rychlý postup na novém stroji

1. Naklonuj workspace a vlož balíčky do `src/` (nebo použij tento repozitář jako zdroj).
2. **Volitelně – vlastní rosdep** (kvůli `pmw3901` a SSD1306 knihovně, které nejsou v centrálním rosdistro):

   ```bash
   sudo sh -c 'echo "yaml file://ABSOLUTNI_CESTA/sw-nav-module/rosdep/rmodus_custom.yaml" > /etc/ros/rosdep/sources.list.d/20-rmodus.list'
   rosdep update
   ```

   Nahraď `ABSOLUTNI_CESTA` skutečnou cestou k repozitáři.

3. Instalace závislostí:

   ```bash
   cd /cesta/k/workspace
   rosdep install --from-paths src --ignore-src -r -y --rosdistro jazzy
   ```

   Bez zaregistrovaného `rmodus_custom.yaml` můžeš místo toho tyto dva balíčky doinstalovat ručně přes pip (viz sekce „Pouze přes pip“).

## Přehled ROS 2 balíčků (podle `package.xml`)

| Balíček | Kde se používá |
|--------|----------------|
| `ament_cmake`, `rosidl_default_generators`, `rosidl_default_runtime` | `rmodus_interface` (generované zprávy/služby) |
| `std_msgs` | rozhraní + uzly |
| `rclpy` | Python uzly |
| `geometry_msgs`, `nav_msgs`, `sensor_msgs`, `tf2_msgs` | hw, web, autonomy, sim |
| `tf2_ros` | lidar TF, obstacle cloud |
| `rmodus_interface`, `rmodus_description`, `rmodus_hw`, `rmodus_sim`, `rmodus_web`, `rmodus_autonomy`, `rmodus_bringup` | interní závislosti mezi balíčky |
| `robot_state_publisher`, `xacro` | URDF / launch |
| `joint_state_publisher_gui` | hw, bringup |
| `rosbridge_server` | hw, bringup |
| `robot_localization` | EKF, hw |
| `slam_toolbox` | SLAM launch |
| `nav2_common`, `nav2_controller`, `nav2_smoother`, `nav2_planner`, `nav2_behaviors`, `nav2_bt_navigator`, `nav2_waypoint_follower`, `nav2_velocity_smoother`, `nav2_lifecycle_manager` | Nav2 stack |
| `rf2o_laser_odometry` | volitelná laserová odometrie |
| `ros_gz_sim`, `ros_gz_bridge`, `ros_gz_interfaces` | simulace Gazebo ↔ ROS |
| `sensor_msgs_py` | `node_obstacle_cloud` (`point_cloud2`) |
| `launch`, `launch_ros`, `ament_index_python` | Python launch soubory |
| `rviz2` | volitelně přes `rviz:=true` v bringup |

## Přehled systémových / Python klíčů (rosdep)

Tyto klíče odpovídají položkám `<exec_depend>` / `<depend>` v `package.xml` a mapují se přes veřejný [rosdistro](https://github.com/ros/rosdistro) (Ubuntu/Debian apod.):

| Rosdep klíč | Typické použití v projektu |
|-------------|----------------------------|
| `python3-yaml` | launch + konfigurace YAML |
| `python3-fastapi`, `python3-uvicorn` | web bridge (`rmodus_web`, část `rmodus_hw`) |
| `python3-numpy` | lidar, fan, flow senzor |
| `python3-serial` | LiDAR UART, sériová linka |
| `python3-psutil` | system monitor |
| `python3-gpiozero` | PWM ventilátor |
| `python3-pil` | OLED (Pillow) |
| `python3-spidev-pip` | SPI (flow senzor); na novějších Ubuntu často přepnuto na apt `python3-spidev` |
| `python3-adafruit-blinka-pip` | `board`, `busio`, `digitalio` (Raspberry Pi / kompatibilní HW) |
| `python3-adafruit-circuitpython-mcp230xx-pip` | expandér MCP23017 (bumpery) |
| `python3-adafruit-circuitpython-ads1x15-pip` | ADS1115 (cliff senzory) |
| `ament_lint_auto`, `ament_lint_common`, `ament_copyright`, `ament_flake8`, `ament_pep257`, `python3-pytest` | testy / lint (kde jsou v `package.xml`) |

## Vlastní rosdep soubor (`rosdep/rmodus_custom.yaml`)

| Klíč | Pip balíček | Použití v kódu |
|------|-------------|----------------|
| `rmodus-pmw3901-pip` | `pmw3901` | optický flow senzor |
| `rmodus-adafruit-ssd1306-pip` | `adafruit-circuitpython-ssd1306` | OLED knihovna `adafruit_ssd1306` |

Bez registrace tohoto YAML souboru `rosdep` tyto klíče **nepozná** – buď přidej zdroj výše, nebo:

```bash
pip install --user pmw3901 adafruit-circuitpython-ssd1306
```

## Mapování balíček → soubory (stručně)

| ROS balíček | Hlavní obsah |
|-------------|----------------|
| **rmodus_interface** | `msg/`, `srv/`, CMake generování |
| **rmodus_description** | `urdf/`, `config/`, `launch/description.launch.py` |
| **rmodus_hw** | uzly motorů, LiDAR, bumper, cliff, display, flow, fan, WiFi, monitor; `launch/hw.launch.py` |
| **rmodus_sim** | `sim_bumper_bridge`, Gazebo world, `launch/sim.launch.py`, URDF pro sim |
| **rmodus_web** | FastAPI WebSocket bridge, `launch/web.launch.py` |
| **rmodus_autonomy** | Nav2/SLAM/EKF launch, bumper safety, obstacle cloud |
| **rmodus_bringup** | sjednocující `robot.launch.py`, RViz, PC/edge launch |

## Poznámky

- Sim balíček `rmodus_sim` má v `package.xml` export s podmínkou distro **jazzy** – na jiném ROS 2 distru ověř kompatibilitu `ros_gz_*`.
- HW závislosti (Adafruit, SPI, GPIO) dávají smysl hlavně na **Raspberry Pi** nebo kompatibilní desce; na čistém PC pro vývoj je můžeš při `rosdep install` přeskočit pomocí `--skip-keys` pro konkrétní klíče, pokud HW nodes nespouštíš.

Poslední aktualizace: odvozeno z obsahu `package.xml` a importů v `.py` souborech ve workspace.
