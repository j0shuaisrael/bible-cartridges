#!/bin/sh
# Thin wrapper: build one psalm end-to-end. See tools/build_psalm.py.
#   tools/build_psalm.sh --psalm 2
#   tools/build_psalm.sh --psalm 2 --steps data,audio,cover,viewer
exec python3 "$(dirname "$0")/build_psalm.py" "$@"
