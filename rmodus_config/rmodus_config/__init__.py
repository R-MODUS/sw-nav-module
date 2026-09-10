"""R-MODUS profile selection (filesystem + CLI)."""

from rmodus_config.store import (  # noqa: F401
    ConfigPaths,
    list_profiles,
    read_active_name,
    resolve_active_profile,
    set_active,
)
