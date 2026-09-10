"""CLI entry: ros2 run rmodus_config rmodus_config …"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ament_index_python.packages import get_package_share_directory

from rmodus_config.store import (
    ConfigPaths,
    create_profile,
    delete_profile,
    list_profiles,
    load_paths_file,
    read_active_name,
    read_profile_text,
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

    create_p = sub.add_parser("create", help="vytvořit profil (kopie source/active)")
    create_p.add_argument("name")
    create_p.add_argument("--from", dest="source", default="", help="zdrojový profil")

    del_p = sub.add_parser("delete", help="smazat profil (ne aktivní)")
    del_p.add_argument("name")

    show_p = sub.add_parser("show", help="vypsat obsah profilu")
    show_p.add_argument("name")

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
        if args.cmd == "create":
            path = create_profile(
                paths, args.name, source=args.source or None
            )
            print(f"created {args.name} ({path})")
            return 0
        if args.cmd == "delete":
            delete_profile(paths, args.name)
            print(f"deleted {args.name}")
            return 0
        if args.cmd == "show":
            sys.stdout.write(read_profile_text(paths, args.name))
            return 0
    except (OSError, ValueError, FileNotFoundError, FileExistsError) as exc:
        print(f"rmodus_config: {exc}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
