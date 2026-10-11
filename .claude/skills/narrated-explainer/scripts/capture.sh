#!/usr/bin/env bash
# Record REAL command output for terminal scenes. Never hand-edit the result; re-run instead.
#   capture.sh local  OUT SCRIPT
#   capture.sh docker IMAGE OUT SCRIPT [extra docker run flags...]
#   capture.sh redact FILE                     apply $NX_REDACT to an existing capture (in place; a safety net, not a substitute for
#                                              setting NX_REDACT before the first capture)
# SCRIPT is a shell file of lines like:   step 'uv run j2gha analyze 000'
# (use step '...' for every command you want shown; anything else runs silently as setup).
# Redaction: if $NX_REDACT points to a file of `regex=>replacement` lines (sed -E, applied top to bottom, so put
# specific rules such as paths BEFORE general ones such as the owner name; `\1` backreferences and `\t` work), they are
# applied to the recorded output, so owner names, tokens, run ids etc. never reach the video. Keep that file OUT of the
# project directory (e.g. in the work dir): it must contain the very strings you are hiding.
# Safety: the capture runs exactly what SCRIPT says. Do not put commands that spend money, push to remotes or
# need sudo in a script without the user's explicit approval.
set -euo pipefail
[ -n "${NX_REDACT:-}" ] && [ -f "$NX_REDACT" ] && NX_REDACT="$(readlink -f "$NX_REDACT")"   # absolute: the script may cd
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mode="${1:?mode: local|docker}"; shift
redact() {
  if [ -n "${NX_REDACT:-}" ] && [ -f "$NX_REDACT" ]; then
    local args=() line; while IFS= read -r line; do [ -z "$line" ] && continue; args+=(-e "s"$'\001'"${line%%=>*}"$'\001'"${line#*=>}"$'\001'"g"); done < "$NX_REDACT"
    sed -E "${args[@]}"
  else cat; fi
}
case "$mode" in
  redact)
    f="${1:?FILE}"; [ -n "${NX_REDACT:-}" ] && [ -f "$NX_REDACT" ] || { echo "set NX_REDACT to a regex=>replacement file" >&2; exit 2; }
    tmp="$(mktemp)"; redact < "$f" > "$tmp" && mv "$tmp" "$f"; echo "redacted $f"; exit 0 ;;
  local)
    out="${1:?OUT}"; script="${2:?SCRIPT}"
    mkdir -p "$(dirname "$out")"
    bash -c "source '$HERE/step.sh'; source '$script'" 2>&1 | redact > "$out" ;;
  docker)
    image="${1:?IMAGE}"; out="${2:?OUT}"; script="${3:?SCRIPT}"; shift 3
    mkdir -p "$(dirname "$out")"
    # no tty (-i only), stdin carries the script; --rm so nothing is left behind
    cat "$HERE/step.sh" "$script" | docker run --rm -i --init "$@" --entrypoint bash "$image" 2>&1 | redact > "$out" ;;
  *) echo "mode must be local or docker" >&2; exit 2 ;;
esac
echo "wrote $out ($(grep -c '^@@CMD@@' "$out") commands). Per command (index, exit code, ms):"
# a failing command is valid content, but a failure caused by shell quoting is not: read every non-zero line below
awk '/^@@CMD@@ /{c=substr($0,9); n++} /^@@END@@ /{split($2,a,"="); split($3,b,"="); printf "  [%d] rc=%s %sms  %s%s\n", n-1, a[2], b[2], substr(c,1,70), (a[2]!=0?"   <-- non-zero":"")}' "$out"
