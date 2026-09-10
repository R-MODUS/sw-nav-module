"""R-MODUS profile selection (filesystem + CLI)."""

from rmodus_config.store import (  # noqa: F401
    ConfigPaths,
    configs_root_from_profile_file,
    create_profile,
    default_configs_root,
    delete_profile,
    list_profiles,
    read_active_name,
    read_profile_text,
    rename_profile,
    resolve_active_profile,
    set_active,
    write_profile_text,
)
