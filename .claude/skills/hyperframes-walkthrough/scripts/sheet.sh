#!/usr/bin/env bash
# hfw sheet SOURCE OUT.png t1,t2,... [--cols N] [--width PX]
# Labelled contact sheet at the given times. SOURCE is a video (clip or render) or a capture dir (W/capture/<name>, the
# nearest frame at or before each source time). Use it to find cut points in a raw capture and to check a render.
set -euo pipefail
src="${1:?SOURCE}"; out="${2:?OUT.png}"; times="${3:?t1,t2,...}"; shift 3
cols=4; width=640
while [ $# -gt 0 ]; do case "$1" in --cols) cols="$2"; shift 2 ;; --width) width="$2"; shift 2 ;; *) echo "unknown $1" >&2; exit 2 ;; esac; done
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
i=0
for t in ${times//,/ }; do
  f="$tmp/$(printf %03d $i).png"
  if [ -d "$src" ]; then
    file="$(node -e '
      const tl = require(process.argv[1] + "/timeline.json"); const t = +process.argv[2];
      let best = tl.frames[0]; for (const f of tl.frames) if (f.t <= t) best = f; console.log(best.file);' "$(cd "$src" && pwd)" "$t")"
    ffmpeg -v error -y -i "$src/frames/$file" -vf "scale=$width:-2,drawtext=text='$t':x=8:y=8:fontsize=26:fontcolor=red:box=1:boxcolor=white@0.7" "$f"
  else
    ffmpeg -v error -y -ss "$t" -i "$src" -frames:v 1 -vf "scale=$width:-2,drawtext=text='$t':x=8:y=8:fontsize=26:fontcolor=red:box=1:boxcolor=white@0.7" "$f"
  fi
  i=$((i+1))
done
rows=$(( (i + cols - 1) / cols ))
ffmpeg -v error -y -pattern_type glob -i "$tmp/*.png" -vf "tile=${cols}x${rows}" "$out"
echo "$out ($i frames)"
