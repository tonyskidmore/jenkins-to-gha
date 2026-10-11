#!/usr/bin/env bash
# hfw init --project P [--from DIR]
# Start a walkthrough project by copying the reference project (the examples/000 60 s walkthrough, assets/reference/)
# or another project (--from). Refuses to overwrite an existing project.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project=""; from="$HERE/../assets/reference"
while [ $# -gt 0 ]; do
  case "$1" in --project) project="$2"; shift 2 ;; --from) from="$2"; shift 2 ;; *) echo "unknown option $1" >&2; exit 2 ;; esac
done
[ -n "$project" ] || { echo "usage: hfw init --project P [--from DIR]" >&2; exit 2; }
[ -e "$project" ] && { echo "$project already exists; edit it, or pick another path" >&2; exit 1; }
mkdir -p "$project"
cp -r "$from/." "$project/"
rm -f "$project"/*.published.json
echo "created $project from $(cd "$from" && pwd)"
ls "$project"
