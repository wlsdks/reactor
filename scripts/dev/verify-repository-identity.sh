#!/usr/bin/env bash

set -euo pipefail

readonly EXPECTED_ORIGIN="https://github.com/wlsdks/reactor.git"

if ! repository_root="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  echo "Repository identity mismatch: current directory is not a Git checkout." >&2
  exit 1
fi

if ! origin_url="$(git -C "$repository_root" remote get-url origin 2>/dev/null)"; then
  echo "Repository identity mismatch: origin is not configured." >&2
  exit 1
fi

if [[ "$origin_url" != "$EXPECTED_ORIGIN" ]]; then
  echo "Repository identity mismatch: refusing to operate on unapproved origin." >&2
  exit 1
fi

printf 'Verified repository: %s\n' "wlsdks/reactor"
