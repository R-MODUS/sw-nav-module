"""Entry point for the ROS2 websocket server process."""

import argparse

from rmodus_web.webbridge.app_factory import create_app, run_server
from rmodus_web.webbridge.config import load_web_config


def _config_path_from_args(args=None):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", default="")
    parsed, _unknown = parser.parse_known_args(args)
    path = (parsed.config or "").strip()
    if not path or path.startswith("-"):
        return None
    return path


def run(args=None):
    cfg = load_web_config(_config_path_from_args(args))
    app = create_app(cfg)
    run_server(app, cfg)


if __name__ == "__main__":
    run()
