#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
NODE_ARCHIVE="$ROOT/runtime/node-v22.15.1-linux-x64.tar.xz"
NODE_BIN="$ROOT/runtime/node"

if [[ ! -x "$NODE_BIN" ]]; then
  tar -xJf "$NODE_ARCHIVE" -C "$ROOT/runtime" --strip-components=1 --wildcards '*/bin/node'
  mv "$ROOT/runtime/bin/node" "$NODE_BIN"
  rmdir "$ROOT/runtime/bin"
  chmod +x "$NODE_BIN"
fi

# The project is served by a Python Function, but Vercel's legacy project
# settings still expect an output directory after a custom build command.
mkdir -p "$ROOT/public"
