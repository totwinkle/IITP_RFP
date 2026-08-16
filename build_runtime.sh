#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# The project is served by a Python Function, but Vercel's legacy project
# settings still expect an output directory after a custom build command.
mkdir -p "$ROOT/public"
