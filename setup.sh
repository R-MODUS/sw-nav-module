#!/bin/bash

OPS_DIR="$(cd "$(dirname "$0")" && pwd)"
WS_SRC="$HOME/ros2_ws/src"
PACKAGES=("rmodus_hw" "rmodus_web" "rmodus_autonomy" "rmodus_interface" "rmodus_bringup")

mkdir -p "$WS_SRC"

echo "Creating symlinks for selected packages..."
for PKG in "${PACKAGES[@]}"; do
    if [ -d "$OPS_DIR/$PKG" ]; then
        ln -sf "$OPS_DIR/$PKG" "$WS_SRC/$PKG"
        echo "Linked: $PKG"
    else
        echo "Warning: Directory $PKG not found in $OPS_DIR!"
    fi
done

echo "Done."