#!/usr/bin/env bash
# Join chapter videos (made by the same pipeline, so same codecs and size) into one movie, losslessly.
#   concat.sh OUT.mp4 chapter1.mp4 chapter2.mp4 ...
# Refuses if the chapters differ in codec, size or frame rate (re-render the odd one out instead).
set -euo pipefail
out="${1:?OUT.mp4}"; shift
[ "$#" -ge 2 ] || { echo "give at least two chapter videos" >&2; exit 2; }
sig() { ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of csv=p=0 "$1"; echo "$(ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels -of csv=p=0 "$1")"; }
ref="$(sig "$1")"
for f in "$@"; do [ -f "$f" ] || { echo "missing $f" >&2; exit 1; }; [ "$(sig "$f")" = "$ref" ] || { echo "stream mismatch in $f" >&2; exit 1; }; done
list="$(mktemp)"; for f in "$@"; do printf "file '%s'\n" "$(readlink -f "$f")" >> "$list"; done
ffmpeg -y -v error -f concat -safe 0 -i "$list" -c copy "$out"; rm -f "$list"
echo "wrote $out ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$out" | cut -d. -f1) s from $# chapters)"
