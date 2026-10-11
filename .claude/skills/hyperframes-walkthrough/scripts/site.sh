#!/usr/bin/env bash
# hfw stage|lint|snapshot|render --project P --work W [--at t1,t2,...] [--out NAME] [--resolution 4k]
# --resolution 4k renders 3840x2160 (Chrome at 2x pixel density: sharp text; YouTube encodes 4K uploads far better).
# The HyperFrames site is assembled in W/site/: the project's index.html, compositions/ and optional assets/ are copied
# over it on every call, while W/site/assets/clips/ and W/site/assets/audio/ hold the generated media (hfw clips, hfw audio).
set -euo pipefail
cmd="$1"; shift
HFW_HOME="${HFW_HOME:-${XDG_CACHE_HOME:-$HOME/.cache}/hyperframes-walkthrough}"
HF="$HFW_HOME/node_modules/.bin/hyperframes"
[ -x "$HF" ] || { echo "hyperframes CLI missing: run hfw setup" >&2; exit 1; }
project=""; work=""; at=""; outname="walkthrough.mp4"; resolution=""
while [ $# -gt 0 ]; do
  case "$1" in
    --project) project="$2"; shift 2 ;; --work) work="$2"; shift 2 ;;
    --at) at="$2"; shift 2 ;; --out) outname="$2"; shift 2 ;; --resolution) resolution="$2"; shift 2 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
done
[ -n "$project" ] && [ -n "$work" ] || { echo "usage: hfw $cmd --project P --work W" >&2; exit 2; }
[ -f "$project/index.html" ] || { echo "$project/index.html not found" >&2; exit 1; }
site="$work/site"
mkdir -p "$site/assets" "$work/out"
rm -rf "$site/compositions"
cp "$project/index.html" "$site/"
cp -r "$project/compositions" "$site/"
[ -d "$project/assets" ] && cp -r "$project/assets/." "$site/assets/"
missing=0
for ref in $(grep -rhoE 'src="\./assets/[^"]+"' "$site/index.html" "$site/compositions" | sed -E 's/src="\.\/(.*)"/\1/' | sort -u); do
  [ -e "$site/$ref" ] || { echo "MISSING: $ref (hfw clips / hfw audio)"; missing=1; }
done
case "$cmd" in
  stage) echo "staged $site"; [ "$missing" = 0 ] ;;
  lint) "$HF" lint "$site" ;;
  snapshot)
    [ -n "$at" ] || { echo "snapshot needs --at t1,t2,..." >&2; exit 2; }
    rm -rf "$work/out/snapshots"
    "$HF" snapshot "$site" -o "$work/out/snapshots" --at "$at" --no-end --describe false >/dev/null
    ls "$work/out/snapshots"/frame-*.png
    n=$(ls "$work/out/snapshots"/frame-*.png | wc -l)
    ffmpeg -v error -y -pattern_type glob -i "$work/out/snapshots/frame-*.png" -vf "scale=960:-2,tile=2x$(( (n + 1) / 2 ))" "$work/out/snapshots/sheet.png"
    echo "$work/out/snapshots/sheet.png" ;;
  render)
    [ "$missing" = 0 ] || exit 1
    "$HF" lint "$site" | tail -3
    "$HF" render "$site" -o "$work/out/$outname" --video-frame-format png ${resolution:+--resolution "$resolution"}
    ffprobe -v error -show_entries format=duration,size -of compact "$work/out/$outname" ;;
esac
