#!/usr/bin/env bash
# Start a local seekdb 1.4.x instance for the Memory Pawnshop demo.
# Usage: SEEKDB_HOME=/path/to/seekdb ./seekdb-start.sh
set -euo pipefail

SEEKDB_HOME=${SEEKDB_HOME:?set SEEKDB_HOME to the extracted seekdb package root}
BASE_DIR=${SEEKDB_BASE_DIR:-$PWD/seekdb-data}
PORT=${SEEKDB_PORT:-2886}
MEMORY_LIMIT=${SEEKDB_MEMORY_LIMIT:-4G}

mkdir -p "$BASE_DIR/store/redo"
exec "$SEEKDB_HOME/usr/bin/seekdb" \
  --nodaemon \
  --base-dir="$BASE_DIR" \
  --port="$PORT" \
  --data-dir="$BASE_DIR/store" \
  --redo-dir="$BASE_DIR/store/redo" \
  --parameter memory_limit="$MEMORY_LIMIT" \
  --parameter datafile_size=2G \
  --parameter log_disk_size=2G
