"""CLI entry: ros2 run rmodus_config rmodus_config …"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from rmodus_config.store import (
    ConfigPaths,
    list_profiles,
    load_paths_file,
    read_active_name,
    resolve_active_profile,
    set_active,
)


def _paths(configs_root: str, paths_yaml: str) -> ConfigPaths:
    if paths_yaml:
        return load_paths_file(Path(paths_yaml))
    share = Path(get_package_share_directory("rmodus_config")) / "config" / "paths.yaml"
    if share.is_file():
        base = load_paths_file(share)
        if configs_root:
            return ConfigPaths.from_root(Path(configs_root))
        # empty configs_root in yaml → defaults already in from_mapping
        if base.root and str(base.root) not in (".", ""):
            return base
    if configs_root:
        return ConfigPaths.from_root(Path(configs_root))
    return ConfigPaths.from_root()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="R-MODUS profiles (ROS wrapper)")
    parser.add_argument("--configs-root", default="")
    parser.add_argument("--paths-yaml", default="", help="optional paths.yaml override")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    sub.add_parser("active")
    path_p = sub.add_parser("path")
    g = path_p.add_mutually_exclusive_group(required=True)
    g.add_argument("--active", action="store_true")
    g.add_argument("--network", action="store_true")
    g.add_argument("--active-file", action="store_true")
    g.add_argument("--profiles-dir", action="store_true")
    act = sub.add_parser("activate")
    act.add_argument("name")

    args = parser.parse_args(argv)
    paths = _paths(args.configs_root, args.paths_yaml)

    try:
        if args.cmd == "list":
            for name in list_profiles(paths):
                mark = " *" if name == read_active_name(paths) else ""
                print(f"{name}{mark}")
            return 0
        if args.cmd == "active":
            name = read_active_name(paths)
            if not name:
                print(f"rmodus_config: no active at {paths.active_file}", file=sys.stderr)
                return 1
            print(name)
            return 0
        if args.cmd == "path":
            if args.active:
                print(resolve_active_profile(paths))
            elif args.network:
                print(paths.network_yaml)
            elif args.active_file:
                print(paths.active_file)
            else:
                print(paths.profiles_dir)
            return 0
        if args.cmd == "activate":
            path = set_active(paths, args.name)
            print(f"active -> {args.name} ({path})")
            return 0
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"rmodus_config: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
