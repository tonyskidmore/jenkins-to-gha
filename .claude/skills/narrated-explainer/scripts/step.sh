# Source this, then call:  step "<command line>"
# Prints a marker, runs the command with eval (stderr merged into stdout), records exit code and milliseconds.
# Capture format (parsed by make-timeline.mjs):
#   @@CMD@@ <command>
#   <output lines>
#   @@END@@ rc=<n> ms=<n>
step() {
  local t0 t1 rc
  printf '\n@@CMD@@ %s\n' "$1"
  t0=$(date +%s%N); eval "$1" 2>&1; rc=$?; t1=$(date +%s%N)
  printf '@@END@@ rc=%s ms=%s\n' "$rc" "$(( (t1 - t0) / 1000000 ))"
}
