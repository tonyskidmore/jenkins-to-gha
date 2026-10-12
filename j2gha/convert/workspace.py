"""The pipeline workspace hand-off between split jobs (Phase 4, P4.3).

Jenkins runs every stage without an agent of its own in the pipeline agent's one workspace. The converted jobs run on
separate machines, so the workspace is handed on as artifacts. `generator._workspace_handoff` decides which jobs take
part (*producers* change the workspace and hand it on; *consumers* start from it); this module plans what each
consumer restores and generates the steps.

Snapshots and lineage
---------------------
* A producer ends by uploading the snapshot after it, `j2gha-ws-<job>`: its whole workspace as a tar (modes, symlinks
  and empty directories kept).
* A job starts from the snapshot *before* it: that of its nearest producers (`Restore.heads`). With one, that
  producer's snapshot. With several - the branches of a parallel stage, which all started from one snapshot - their
  merge: the first branch's snapshot with each later branch's *own changes* replayed onto it, in job order.
* A producer that can be merged that way (another producer runs concurrently with it, `Plan.mergeable`) records the
  snapshot it starts from - a manifest of every entry's type, mode and content digest or link target - and hands on
  its change list next to its snapshot: the entries it added or changed and those it removed, directories included.
  So no merge needs the snapshot the branches started from, whether it was one producer's, itself a merge (a parallel
  stage straight after another) or the checkout (a parallel first stage).
* A matrix job (`Plan.deltas`) runs up to 256 cells: each cell records the snapshot it starts from and hands on its
  changes only - its change list and a tar of the entries it added or changed (with their parent directories) - as
  `j2gha-ws-<job>.<cell>` (job ids have no dots, so `j2gha-ws-<job>.*` matches no other job's artifact). A consumer
  after the matrix downloads the workspace the matrix started from (its nearest producers: heads of their own) and
  every cell by that pattern, and replays the cells' changes onto it in cell-name order. A matrix with no producer
  before it (it starts from the checkout), after another matrix, or concurrent with another producer is not handed
  on: it stays a consumer, and the generator reports it.
* A producer skipped at job level (a gate said no, a job it needs failed) made no upload: the consumer downloads the
  workspaces it would have started from instead (its own nearest producers, recursively; at most
  MAX_HANDOFF_FALLBACKS beyond the nearest, the rest is reported). At run time the merge step takes the downloaded
  workspaces that no other downloaded one descends from (the `J2GHA_WS_LINEAGE` it is given).
* Transfers: the merge step accounts for every producer it relies on, along the fallback chain actually used. A
  producer whose workspace did not arrive must have been skipped, and then the producers it would have started from
  are accounted for in turn (`J2GHA_WS_FALLBACKS`). The job result of a producer the consumer needs directly is known
  (`J2GHA_WS_RESULTS`): one that ran but whose workspace did not arrive (a failed download, an expired artifact) fails
  the merge instead of being replaced by an older workspace. Any other producer's result is not known to the
  consumer (adding it to `needs` would change the job graph): it is taken as skipped, with a warning. A corrupt archive
  fails the extraction.

Semantics and limits - each unsupported case fails or is reported, none passes silently
---------------------------------------------------------------------------------------
* A path two concurrent branches both change takes the later branch's version (job order; matrix cells: cell-name
  order), and a branch that removes a directory removes what an earlier branch put in it. In Jenkins the result
  depends on timing.
* Changes are found by content, mode, type, link target and hard-link count: a change of timestamps alone (`touch`)
  is not handed on. Hard links are kept: a changed file's change list entry takes every other name of the file along
  (its whole link group as the branch left it, however the group changed - a new name, a removed one, a rename), so
  the merge can link them again. So a branch that renames or adds a name of a file another branch rewrites wins over
  that rewrite.
* The steps run with bash and GNU tar, findutils and coreutils: GitHub's Linux runners and Debian/Ubuntu-based job
  containers. In an image without bash the steps fail (busybox/Alpine images are not supported).
* Merging needs every merged branch's change list: a branch without one (it did not record its starting snapshot)
  fails the merge step.
* Planning checks that producers running concurrently start from the same snapshot (ValueError otherwise): the merge
  replays their changes onto one of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

HANDOFF_DIR = ".j2gha-ws"  # in the workspace: `runner.temp` is a host path that container jobs cannot see
HANDOFF_TAR = ".j2gha-ws.tgz"
HANDOFF_CHANGES = ".j2gha-ws.changes"
MAX_HANDOFF_FALLBACKS = 12  # per job, beyond the nearest workspaces (always downloaded): reported
RESTORE_ID = "j2gha-ws-restore"
STEP_NAMES = ("Restore pipeline workspace", "Record the starting workspace", "Hand on the pipeline workspace")
META = {"kind": "workspace-handoff", "trace": False, "role": "handoff"}


@dataclass
class Restore:
    """What one consumer downloads and how its merge step relates the downloads."""
    heads: list[str]  # the nearest producers: always downloaded (job order)
    direct: list[str] = field(default_factory=list)  # producers it may rely on that are direct needs: result known
    fallback_of: dict[str, list[str]] = field(default_factory=dict)  # producer -> what replaces it if it made none
    fallbacks: list[tuple[str, str]] = field(default_factory=list)  # (producer, `if:` of its download), in order
    lineage: dict[str, list[str]] = field(default_factory=dict)  # downloaded producer -> downloaded ancestors
    dropped: int = 0  # fallbacks over MAX_HANDOFF_FALLBACKS, not generated
    deltas: list[str] = field(default_factory=list)  # downloaded producers that are matrix jobs (their cells' changes)


@dataclass
class Plan:
    restores: dict[str, Restore]  # consumer -> its restore (consumers with no producer before them: absent)
    mergeable: set[str]  # producers that record their starting snapshot and hand on a change list
    handed_on: set[str]  # producers some consumer downloads (the others need no upload)
    deltas: set[str] = field(default_factory=set)  # handed-on matrix jobs: one change set per cell


Slot = tuple[str, list]  # (producer, the slots to fall back on when it made no upload)


def plan(order: list[str], needs: dict[str, list[str]], producers: set[str], consumers: set[str],
         deltas: set[str] | frozenset[str] = frozenset()) -> Plan:
    """`order`: every job, dependencies first; `needs`: each job's direct dependencies. `deltas`: producers that hand
    on only their changes, one change set per matrix cell (see the module docstring); one that cannot (no producer
    before it, a delta or a concurrent producer among them) stays a consumer only and is left out of `Plan.deltas`."""
    pos = {jid: i for i, jid in enumerate(order)}
    producers, deltas = set(producers), set(deltas) & set(producers)
    while True:
        ancestry, before = _lineage(needs, producers, pos)
        bad = {d for d in deltas if not before(d) or any(s[0] in deltas for s in before(d))
               or any(_concurrent(ancestry, d, q) for q in producers)}
        if not bad:
            break
        producers -= bad
        deltas -= bad

    def concurrent(p: str, q: str) -> bool:
        return _concurrent(ancestry, p, q)

    mergeable = {p for p in producers if any(concurrent(p, q) for q in producers)}
    for p in sorted(mergeable, key=pos.__getitem__):
        for q in sorted(producers, key=pos.__getitem__):
            if concurrent(p, q) and [s[0] for s in before(p)] != [s[0] for s in before(q)]:
                raise ValueError(f"workspace hand-off: jobs '{p}' and '{q}' run concurrently but start from different "
                                 "workspaces, which the merge cannot combine")
    restores = {}
    for jid in sorted(consumers, key=pos.__getitem__):
        r = _restore(before(jid), pos, lambda p: ancestry(p) & producers, deltas)
        if r is not None:
            r.direct = [p for p in r.fallback_of if p in needs.get(jid, [])]
            restores[jid] = r
    handed_on = {p for r in restores.values() for p in [*r.heads, *(f for f, _ in r.fallbacks)]}
    return Plan(restores, mergeable, handed_on, deltas & handed_on)


def _concurrent(ancestry: Any, p: str, q: str) -> bool:
    return p != q and p not in ancestry(q) and q not in ancestry(p)


def _lineage(needs: dict[str, list[str]], producers: set[str], pos: dict[str, int]) -> tuple[Any, Any]:
    """(ancestry(job), before(job)): a job's dependencies, transitively, and the snapshot it starts from."""
    ancestors: dict[str, set[str]] = {}

    def ancestry(jid: str) -> set[str]:
        if jid not in ancestors:
            ancestors[jid] = set()
            for n in needs.get(jid, []):
                ancestors[jid] |= {n} | ancestry(n)
        return ancestors[jid]

    after: dict[str, list[Slot]] = {}

    def before(jid: str) -> list[Slot]:
        """The snapshot a job starts from: its nearest producers, each with its own fallbacks."""
        slots = {head: slot for n in needs.get(jid, []) for head, slot in ((s[0], s) for s in state_after(n))}
        heads = [h for h in slots if not any(h in ancestry(o) for o in slots if o != h)]
        return [slots[h] for h in sorted(heads, key=pos.__getitem__)]

    def state_after(jid: str) -> list[Slot]:
        if jid not in after:
            after[jid] = [(jid, before(jid))] if jid in producers else before(jid)
        return after[jid]

    return ancestry, before


def _restore(slots: list[Slot], pos: dict[str, int], ancestors: Any,
             deltas: set[str] | frozenset[str] = frozenset()) -> Restore | None:
    if not slots:
        return None
    # a delta's changes are replayed onto the workspace its job started from: those producers are heads too
    expanded: dict[str, Slot] = {}
    for slot in slots:
        if slot[0] in deltas:
            expanded.update((b[0], b) for b in slot[1])
        expanded[slot[0]] = slot
    slots = sorted(expanded.values(), key=lambda sl: pos[sl[0]])
    heads = [s[0] for s in slots]
    when: dict[str, list[list[str]]] = {}  # fallback producer -> the chains of producers that must all have failed
    queue = [(slot, [slot[0]]) for slot in slots]
    discovered: list[str] = []
    while queue:
        (_, fallback), chain = queue.pop(0)
        for c in (s[0] for s in fallback):
            if c not in heads:
                when.setdefault(c, []).append(chain)
                if c not in discovered:
                    discovered.append(c)
        queue += [(s, [*chain, s[0]]) for s in fallback]
    fallback_of: dict[str, list[str]] = {}  # every producer the job may rely on, dropped fallbacks included
    todo = list(slots)
    while todo:
        p, fallback = todo.pop(0)
        if p not in fallback_of:
            fallback_of[p] = [s[0] for s in fallback]
            todo += fallback
    kept = discovered[:MAX_HANDOFF_FALLBACKS]
    scheduled = set(heads) | set(kept)

    def downloaded_if(p: str) -> str:
        # a fallback's `if:` reads the outcome of downloads before it: chains through dropped fallbacks are left out
        return " || ".join("(" + " && ".join(f"steps.j2gha-ws-{q}.outcome != 'success'" for q in c) + ")"
                           for c in when[p] if set(c) <= scheduled) or "false"

    conds = {p: downloaded_if(p) for p in kept}
    # a delta's base is downloaded whenever the delta is: a pattern download that finds no cell still succeeds, so its
    # outcome cannot decide whether the base is needed
    for d in [p for p in kept if p in deltas]:
        for b in fallback_of[d]:
            if b in conds:
                conds[b] = f"({conds[b]}) || ({conds[d]})"
    fallbacks = [(p, conds[p]) for p in kept]
    lineage = {p: sorted(ancestors(p) & scheduled, key=pos.__getitem__) for p in sorted(scheduled, key=pos.__getitem__)}
    return Restore(heads, fallbacks=fallbacks, lineage=lineage, dropped=len(discovered) - len(kept),
                   fallback_of=dict(sorted(fallback_of.items(), key=lambda kv: pos[kv[0]])),
                   deltas=[p for p in sorted(scheduled, key=pos.__getitem__) if p in deltas])


# ----------------------------------------------------------------------------------------------- generated steps
_MANIFEST = r"""# one line per path or value: backslashes and newlines escaped (`printf %b` reverses it)
esc() { sed -z 's/\\/\\\\/g; s/\n/\\n/g' | tr '\0' '\n'; }
# the workspace's entries, the hand-off's own files left out: lines alternating path and "type mode digest"
# (digest: hard-link count and content sha256 of a file - a new or removed link changes every name of the file, so a
# branch's change list carries the whole group - or the target of a symbolic link)
manifest() {
  local tmp="$RUNNER_TEMP/j2gha-ws-manifest" i
  local -a recs=() out=()
  local -A sum=()
  (cd "$GITHUB_WORKSPACE" && find . -mindepth 1 \( -path ./.j2gha-ws -o -path ./.j2gha-ws.tgz \
    -o -path ./.j2gha-ws.changes \) -prune -o -type f -print0) > "$tmp.files"
  (cd "$GITHUB_WORKSPACE" && xargs -0 -r sha256sum -z -- < "$tmp.files") | esc > "$tmp.sums"
  mapfile -t recs < "$tmp.sums"
  for i in "${recs[@]}"; do sum["${i#*  }"]=${i%%  *}; done
  (cd "$GITHUB_WORKSPACE" && find . -mindepth 1 \( -path ./.j2gha-ws -o -path ./.j2gha-ws.tgz \
    -o -path ./.j2gha-ws.changes \) -prune -o -type f -printf '%p\0f %m %n \0' -o -printf '%p\0%y %m %l\0') |
    esc > "$tmp.entries"
  mapfile -t recs < "$tmp.entries"
  for ((i = 0; i < ${#recs[@]}; i += 2)); do out+=("${recs[i]}" "${recs[i + 1]}${sum[${recs[i]}]-}"); done
  if [ "${#out[@]}" -gt 0 ]; then printf '%s\n' "${out[@]}"; fi
  rm -f "$tmp.files" "$tmp.sums" "$tmp.entries"
}
"""

RECORD_SCRIPT = _MANIFEST + r"""manifest > "$RUNNER_TEMP/j2gha-ws-start"
"""

HANDON_SCRIPT = r"""tar --exclude=./.j2gha-ws --exclude=./.j2gha-ws.tgz --exclude=./.j2gha-ws.changes \
  -czf "$RUNNER_TEMP/j2gha-ws.tgz" -C "$GITHUB_WORKSPACE" .
mv "$RUNNER_TEMP/j2gha-ws.tgz" "$GITHUB_WORKSPACE/.j2gha-ws.tgz"
"""

# a mergeable producer also hands on its own changes - what a merge replays when it ran concurrently with another:
# lines "C<path>" (added or changed) and "D<path>" (removed), paths escaped
_CHANGES = r"""if [ -f "$RUNNER_TEMP/j2gha-ws-start" ]; then
  declare -A was=() now=()
  changes=()
  mapfile -t recs < "$RUNNER_TEMP/j2gha-ws-start"
  for ((i = 0; i < ${#recs[@]}; i += 2)); do was[${recs[i]}]=${recs[i + 1]}; done
  manifest > "$RUNNER_TEMP/j2gha-ws-end"
  mapfile -t recs < "$RUNNER_TEMP/j2gha-ws-end"
  for ((i = 0; i < ${#recs[@]}; i += 2)); do now[${recs[i]}]=${recs[i + 1]}; done
  declare -A changed=() inode=() group=()
  for p in "${!now[@]}"; do
    if [ "${was[$p]-}" != "${now[$p]}" ]; then changed[$p]=1; fi
  done
  # a changed file with other names takes all of them along (a rename keeps the link count): the merge relinks them
  (cd "$GITHUB_WORKSPACE" && find . -mindepth 1 \( -path ./.j2gha-ws -o -path ./.j2gha-ws.tgz \
    -o -path ./.j2gha-ws.changes \) -prune -o -type f -links +1 -printf '%D:%i\0%p\0') | esc > "$RUNNER_TEMP/j2gha-ws-links"
  mapfile -t recs < "$RUNNER_TEMP/j2gha-ws-links"
  for ((i = 0; i < ${#recs[@]}; i += 2)); do
    inode[${recs[i + 1]}]=${recs[i]}
    group[${recs[i]}]+="${recs[i + 1]}"$'\n'
  done
  for p in "${!changed[@]}"; do
    if [ -n "${inode[$p]-}" ]; then
      while IFS= read -r q; do
        if [ -n "$q" ]; then changed[$q]=1; fi
      done <<< "${group[${inode[$p]}]}"
    fi
  done
  for p in "${!changed[@]}"; do changes+=("C$p"); done
  for p in "${!was[@]}"; do
    if [ -z "${now[$p]-}" ]; then changes+=("D$p"); fi
  done
  : > "$GITHUB_WORKSPACE/.j2gha-ws.changes"
  if [ "${#changes[@]}" -gt 0 ]; then printf '%s\n' "${changes[@]}" > "$GITHUB_WORKSPACE/.j2gha-ws.changes"; fi
else
  echo "::warning::the workspace this job started from was not recorded: its workspace cannot be merged"
fi
"""
HANDON_CHANGES_SCRIPT = _MANIFEST + _CHANGES + HANDON_SCRIPT

# a matrix cell hands on its changes only: the change list and a tar of the entries it added or changed, with their
# parent directories (a merge replays them onto the workspace the matrix started from, which it downloads anyway)
HANDON_DELTA_SCRIPT = _MANIFEST + _CHANGES + r"""if [ ! -f "$GITHUB_WORKSPACE/.j2gha-ws.changes" ]; then
  echo "::error::the workspace this matrix cell started from was not recorded: its changes cannot be handed on"
  exit 1
fi
declare -A member=()
mapfile -t recs < "$GITHUB_WORKSPACE/.j2gha-ws.changes"
for rec in "${recs[@]}"; do
  if [ "${rec:0:1}" != C ]; then continue; fi
  printf -v p '%b' "${rec:1}"
  member[$p]=1
  while p=${p%/*}; [ "$p" != . ]; do member[$p]=1; done
done
: > "$RUNNER_TEMP/j2gha-ws-members"
if [ "${#member[@]}" -gt 0 ]; then printf '%s\0' "${!member[@]}" | LC_ALL=C sort -z > "$RUNNER_TEMP/j2gha-ws-members"; fi
tar -czf "$RUNNER_TEMP/j2gha-ws.tgz" -C "$GITHUB_WORKSPACE" --null --no-unquote --no-recursion \
  -T "$RUNNER_TEMP/j2gha-ws-members"
mv "$RUNNER_TEMP/j2gha-ws.tgz" "$GITHUB_WORKSPACE/.j2gha-ws.tgz"
"""

RESTORE_SCRIPT = r"""ws="$GITHUB_WORKSPACE"
d="$ws/.j2gha-ws"
# the downloaded producers a producer descends from
ancestors() {
  local line
  while IFS= read -r line; do
    if [ "${line%%:*}" = "$1" ]; then printf '%s\n' "${line#*:}"; fi
  done <<< "$J2GHA_WS_LINEAGE"
}
isdelta() { case " $J2GHA_WS_DELTAS " in *" $1 "*) return 0 ;; esac; return 1; }
# the cells of a matrix producer that arrived (one directory per artifact, in name order)
cells() { local c; for c in "$d/$1"/*/; do if [ -f "$c.j2gha-ws.changes" ]; then basename "$c"; fi; done; }
present() {
  if isdelta "$1"; then [ -n "$(cells "$1")" ]; else [ -f "$d/$1/.j2gha-ws.tgz" ]; fi
}
# read-only directories (a Go module cache) need write permission to be removed
remove() { rm -rf -- "$@" 2>/dev/null || { chmod -R u+w -- "$@"; rm -rf -- "$@"; }; }
isdir() { [ -d "$1" ] && [ ! -L "$1" ]; }
# replay a branch's own changes (its change list) onto the workspace
replay() {
  local src="$d/$1" t="$d/.replay" rec p a
  local -a recs=() gone=()
  local -A want=() locked=() removed=()
  if [ ! -f "$src/.j2gha-ws.changes" ]; then
    echo "::error::the workspace of job '$1' has no change list (the workspace it started from was not recorded): it cannot be merged"
    exit 1
  fi
  mapfile -t recs < "$src/.j2gha-ws.changes"
  for rec in "${recs[@]}"; do
    printf -v p '%b' "${rec:1}"
    if [ "${rec:0:1}" = D ]; then
      removed[$p]=1
      continue
    fi
    want[$p]=1
    # a parent directory an earlier branch removed or replaced is taken from this branch too
    a=$p
    while a=${a%/*}; [ "$a" != . ]; do
      if isdir "$ws/$a"; then break; fi
      want[$a]=1
    done
  done
  # a removed directory takes its contents with it: only the top-most removed entries are removed
  for p in "${!removed[@]}"; do
    a=$p
    while a=${a%/*}; [ "$a" != . ] && [ -z "${removed[$a]-}" ]; do :; done
    if [ "$a" = . ]; then gone+=("$p"); fi
  done
  # only the entries to copy come out of the branch's workspace (parents first)
  mkdir -p "$t"
  printf '%s\0' "${!want[@]}" | LC_ALL=C sort -z > "$d/.want"
  if [ "${#want[@]}" -gt 0 ]; then tar -xzpf "$src/.j2gha-ws.tgz" -C "$t" --null --no-unquote --no-recursion -T "$d/.want"; fi
  # read-only directories (a Go module cache) are opened for the changes; their modes are put back afterwards
  for p in "${gone[@]}" "${!want[@]}"; do
    a=${p%/*}
    if [ "$a" != . ] && isdir "$ws/$a" && [ ! -w "$ws/$a" ] && [ -z "${locked[$a]-}" ]; then
      locked[$a]=$(stat -c %a "$ws/$a")
      chmod u+w "$ws/$a"
    fi
  done
  for p in "${gone[@]}"; do remove "$ws/$p"; done
  # clear what is in the way of an entry's type: a file or link where the branch has a directory, or the reverse
  for p in "${!want[@]}"; do
    if isdir "$t/$p"; then
      if [ -L "$ws/$p" ] || { [ -e "$ws/$p" ] && [ ! -d "$ws/$p" ]; }; then rm -f -- "$ws/$p"; fi
      if isdir "$ws/$p" && [ ! -w "$ws/$p" ]; then chmod u+w "$ws/$p"; fi  # tar sets the branch's mode
    elif isdir "$ws/$p"; then
      remove "$ws/$p"
    fi
  done
  if [ "${#want[@]}" -gt 0 ]; then
    # tar sets directory modes after their contents
    tar -C "$t" --null --no-unquote --no-recursion -T "$d/.want" -cf - | tar -xpf - -C "$ws"
  fi
  for a in "${!locked[@]}"; do
    if [ -z "${want[$a]-}" ] && isdir "$ws/$a"; then chmod "${locked[$a]}" "$ws/$a"; fi
  done
  remove "$t"
}
# every producer the restore relies on is accounted for: its workspace arrived, or its job was skipped and the
# producers it would have started from are accounted for in turn (the fallback chain actually used)
declare -A result=() fallback=() seen=()
for r in $J2GHA_WS_RESULTS; do result[${r%%=*}]=${r#*=}; done
while IFS= read -r line; do
  if [ -n "$line" ]; then fallback[${line%%:*}]=${line#*:}; fi
done <<< "$J2GHA_WS_FALLBACKS"
account() {
  local p=$1 f
  if [ -n "${seen[$p]-}" ] || present "$p"; then return 0; fi
  seen[$p]=1
  case "${result[$p]-}" in
    success|failure)
      echo "::error::job '$p' ran (${result[$p]}) but its workspace did not arrive: restoring an older one would lose its changes"
      exit 1 ;;
    skipped|cancelled) ;;
    *) echo "::warning::the workspace of job '$p' did not arrive and its result is not known here (not a job this one needs): taken as skipped - if it ran, its changes are missing" ;;
  esac
  for f in ${fallback[$p]-}; do account "$f"; done
}
for p in $J2GHA_WS_HEADS; do account "$p"; done
# the workspaces to merge: those downloaded that no other downloaded one descends from
frontier=()
for p in $J2GHA_WS_ORDER; do
  present "$p" || continue
  covered=false
  for q in $J2GHA_WS_ORDER; do
    # a matrix hands on its cells' changes, not a workspace: it does not stand in for the producers before it
    if [ "$q" != "$p" ] && ! isdelta "$q" && present "$q"; then
      case " $(ancestors "$q") " in *" $p "*) covered=true ;; esac
    fi
  done
  if [ "$covered" = false ]; then frontier+=("$p"); fi
done
restored=false
if [ "${#frontier[@]}" -gt 0 ]; then
  # the restored workspace replaces what the job started with (act copies the repository into every job)
  shopt -s dotglob nullglob
  for e in "$ws"/*; do
    if [ "$e" != "$d" ]; then remove "$e"; fi
  done
  shopt -u dotglob nullglob
  if isdelta "${frontier[0]}"; then
    echo "::error::no workspace arrived for the changes of matrix job '${frontier[0]}' to be applied to"
    exit 1
  fi
  tar -xzpf "$d/${frontier[0]}/.j2gha-ws.tgz" -C "$ws"
  for f in "${frontier[@]:1}"; do
    if isdelta "$f"; then
      while IFS= read -r c; do replay "$f/$c"; done < <(cells "$f")
    else
      replay "$f"
    fi
  done
  restored=true
fi
remove "$d"
echo "restored=$restored" >> "$GITHUB_OUTPUT"
"""


def restore_steps(r: Restore, download: str) -> list[dict[str, Any]]:
    """The downloads (nearest workspaces first, then fallbacks after every download they test) and the merge."""
    steps: list[dict[str, Any]] = []
    for p, cond in [*((h, None) for h in r.heads), *r.fallbacks]:
        step: dict[str, Any] = {"name": f"Restore pipeline workspace ({p})", "id": f"j2gha-ws-{p}"}
        if cond is not None:
            step["if"] = cond
        # a matrix job's cells: one artifact each, `j2gha-ws-<job>.<cell>` (job ids have no dots)
        src = {"pattern": f"j2gha-ws-{p}.*"} if p in r.deltas else {"name": f"j2gha-ws-{p}"}
        step.update({"uses": download, "continue-on-error": True,  # a skipped producer uploaded nothing
                     "with": {**src, "path": f"{HANDOFF_DIR}/{p}"}, "_j2gha": dict(META)})
        steps.append(step)
    lineage = "\n".join(f"{p}: {' '.join(a)}".rstrip() for p, a in r.lineage.items())
    env = {"J2GHA_WS_ORDER": " ".join(r.lineage), "J2GHA_WS_LINEAGE": lineage, "J2GHA_WS_HEADS": " ".join(r.heads),
           "J2GHA_WS_RESULTS": " ".join(f"{h}=${{{{ needs.{h}.result }}}}" for h in r.direct),
           "J2GHA_WS_DELTAS": " ".join(r.deltas),
           "J2GHA_WS_FALLBACKS": "\n".join(f"{p}: {' '.join(f)}".rstrip() for p, f in r.fallback_of.items())}
    steps.append({"name": "Restore pipeline workspace (merge)", "id": RESTORE_ID, "if": "always()", "shell": "bash",
                  "env": env, "run": RESTORE_SCRIPT, "_j2gha": dict(META)})
    return steps


def record_step() -> dict[str, Any]:
    """Records the snapshot a mergeable producer starts from (after its restore or checkout)."""
    return {"name": "Record the starting workspace", "if": "always()", "shell": "bash", "run": RECORD_SCRIPT,
            "_j2gha": dict(META)}


def handon_steps(jid: str, mergeable: bool, upload: str, cell: str | None = None) -> list[dict[str, Any]]:
    """`cell` (a matrix job): the cell's suffix in its artifact name, `j2gha-ws-<job>.<cell>`; the cell hands on its
    changes only."""
    script = HANDON_DELTA_SCRIPT if cell is not None else HANDON_CHANGES_SCRIPT if mergeable else HANDON_SCRIPT
    archive = {"name": "Hand on the pipeline workspace (archive)", "if": "always()", "shell": "bash",
               "run": script, "_j2gha": dict(META)}
    path = f"{HANDOFF_TAR}\n{HANDOFF_CHANGES}" if mergeable or cell is not None else HANDOFF_TAR
    name = f"j2gha-ws-{jid}" + (f".{cell}" if cell is not None else "")
    return [archive,
            {"name": "Hand on the pipeline workspace (upload)", "if": "always()", "uses": upload,
             "with": {"name": name, "path": path, "retention-days": 1, "compression-level": 0,
                      "if-no-files-found": "error", "include-hidden-files": True},
             "_j2gha": dict(META)}]
