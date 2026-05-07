"""Entry point for the ROS2 websocket server process."""

from rmodus_web.webbridge.app_factory import create_app, run_server


app = create_app()


def run(args=None):
    del args
    run_server(app)


if __name__ == "__main__":
    run()
