"""Entry point for the ROS2 websocket server process.

Websocket backend file overview:
- node_websocket.py: Process entrypoint used by ROS2 console script.
- webbridge/app_factory.py: FastAPI app creation, websocket endpoint, and ROS lifecycle.
- webbridge/config.py: Runtime constants, TF settings, and sensor topic definitions.
- webbridge/connection_manager.py: Connected clients, roles, and broadcast utilities.
- webbridge/role_state.py: Current admin/operator state and disconnect cleanup.
- webbridge/message_dispatcher.py: Message-type routing and command handlers.
- webbridge/ros_bridge.py: ROS2 subscriptions/publications bridged to websocket messages.
- webbridge/sensor_catalog.py: Reusable sensor metadata objects for the dashboard.
- webbridge/tf_utils.py: Helpers for converting TF rotations into 2D yaw values.
- webbridge/__init__.py: Package marker and package-level description.

Websocket frontend file overview:
- websocket/index.html: Main shell with sidebar navigation and global script loading.
- websocket/static/css/style.css: Shared styles for all websocket pages, including Sensors.
- websocket/static/js/app.js: SPA page loading, websocket connection, and message routing.
- websocket/static/js/map.js: Existing map and lidar visualization logic.
- websocket/static/js/robot_view.js: Dedicated 2D robot/TF renderer for the Sensors page.
- websocket/static/js/sensors.js: Sensors dashboard state, selection, and rendering logic.
- websocket/static/pages/*.html: Individual tab contents loaded into the main view.
"""

from rmodus_brain.webbridge.app_factory import create_app, run_server


app = create_app()


def run(args=None):
    del args
    run_server(app)

if __name__ == "__main__":
    run()
