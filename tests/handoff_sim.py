"""A small GitHub Actions runner for the workspace hand-off, and a reference model of Jenkins' one workspace.

`simulate(jobs, initial)` runs the jobs of a converted workflow in order, each in a fresh workspace and temp dir:

* the hand-off's download steps: their `if:` (outcomes of earlier downloads) is evaluated; a download succeeds when
  the producer uploaded, and unpacks the artifact's files into the step's `path`;
* the hand-off's run steps and the stages' `sh` steps run with bash as GitHub runs them (`shell: bash` ->
  `bash --noprofile --norc -eo pipefail`, default `bash -e`), in the workspace, with GITHUB_WORKSPACE, GITHUB_OUTPUT,
  RUNNER_TEMP and the step's env;
* a checkout copies `initial` into the workspace, unless its `if:` sees that the merge step restored a workspace;
* the hand-off's upload steps store the listed files (they sit at the workspace root, upload-artifact's root).

Other steps (stage entry, echo, uploads of other artifacts...) do not run. A job in `skipped` does not run at all.
With `prepopulated`, every job's workspace starts with `initial` (act's behaviour).
Returns {job: its workspace tree when its own steps start} - after restore, checkout and recording, just before the
first `sh` step or the hand-on.

`jenkins(scripts, initial)` is the reference: every stage's script in one directory, in declaration order.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from j2gha.convert import workspace

Tree = dict[str, tuple]


def tree(root: Path) -> Tree:
    """{relative path: ("d", mode) | ("f", mode, content) | ("f", mode, content, names) | ("l", target)}; `names`: all
    paths of a hard-linked file. The hand-off's own files are included: a job's own steps must start without them (the
    reference never has them)."""
    out: Tree = {}
    inodes: dict[int, list[str]] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in [*dirnames, *filenames]:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            st = p.lstat()
            mode = oct(stat.S_IMODE(st.st_mode))
            if p.is_symlink():
                out[rel] = ("l", os.readlink(p))
            elif p.is_dir():
                out[rel] = ("d", mode)
            else:
                out[rel] = ("f", mode, p.read_bytes())
                inodes.setdefault(st.st_ino, []).append(rel)
    for names in inodes.values():
        if len(names) > 1:
            for rel in names:
                out[rel] = (*out[rel], tuple(sorted(names)))
    return out


def build(root: Path, spec: dict[str, Any]) -> Path:
    """Make a directory from {path: text | (text, mode) | ("->", target) | ("dir", mode)}."""
    root.mkdir(parents=True, exist_ok=True)
    for path, v in spec.items():
        p = root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(v, tuple) and v[0] == "->":
            p.symlink_to(v[1])
        elif isinstance(v, tuple) and v[0] == "dir":
            p.mkdir(exist_ok=True)
            p.chmod(v[1])
        else:
            text, mode = v if isinstance(v, tuple) else (v, 0o644)
            p.write_text(text)
            p.chmod(mode)
    return root


class StepFailed(AssertionError):
    pass


def _bash(script: str, shell: str | None, cwd: Path, env: dict[str, str], temp: Path) -> subprocess.CompletedProcess:
    f = temp / "j2gha-sim-step.sh"
    f.write_text(script)
    cmd = ["bash", "--noprofile", "--norc", "-eo", "pipefail", str(f)] if shell == "bash" else ["bash", "-e", str(f)]
    return subprocess.run(cmd, cwd=cwd, env={**os.environ, **env}, capture_output=True, text=True)


def _if(expr: str | None, outcomes: dict[str, str]) -> bool:
    if expr in (None, "always()"):
        return True
    if expr == "false":
        return False
    py = re.sub(r"steps\.([\w-]+)\.outcome", lambda m: repr(outcomes.get(m.group(1), "")), expr)
    return bool(eval(py.replace("&&", " and ").replace("||", " or "), {"__builtins__": {}}))  # noqa: S307


def _restored(expr: str | None, outputs: dict[str, dict[str, str]]) -> bool:
    """Does a checkout's `if:` skip it because the merge step restored a workspace?"""
    return f"steps.{workspace.RESTORE_ID}.outputs.restored != 'true'" in (expr or "") and \
        outputs.get(workspace.RESTORE_ID, {}).get("restored") == "true"


def simulate(jobs: dict[str, Any], initial: Path, skipped: set[str] | frozenset[str] = frozenset(), *,
             prepopulated: bool = False, lost: set[str] | frozenset[str] = frozenset(),
             corrupt: set[str] | frozenset[str] = frozenset(), incomplete: set[str] | frozenset[str] = frozenset(),
             logs: dict[str, list[str]] | None = None) -> dict[str, Tree]:
    """`prepopulated`: every job's workspace starts as a copy of `initial` (act copies the repository into each
    job; GitHub's runners start empty). Transfer faults, by producer job (every download of its workspace) or by
    `"<consumer>:<producer>"` (that one download): `lost` - the download fails although the job ran; `corrupt` - the
    archive arrives truncated; `incomplete` - the archive arrives without its change list."""
    artifacts: dict[str, dict[str, bytes]] = {}
    starts: dict[str, Tree] = {}
    base = Path(tempfile.mkdtemp(prefix="j2gha-sim-"))
    try:
        for jid, job in jobs.items():
            if jid in skipped:
                continue
            ws, temp = base / jid / "ws", base / jid / "temp"
            if prepopulated:
                shutil.copytree(initial, ws, symlinks=True)
            else:
                ws.mkdir(parents=True)
            temp.mkdir()
            outcomes: dict[str, str] = {}
            outputs: dict[str, dict[str, str]] = {}
            for st in job["steps"]:
                meta = st.get("_j2gha") or {}
                uses = str(st.get("uses", ""))
                handoff = meta.get("role") == "handoff"
                if jid not in starts and (meta.get("kind") == "sh" or (handoff and "Hand on" in st["name"])):
                    starts[jid] = tree(ws)
                if handoff and uses.startswith("actions/download-artifact"):
                    if not _if(st.get("if"), outcomes):
                        outcomes[st["id"]] = "skipped"
                        continue
                    name = st["with"]["name"]
                    keys = {name.removeprefix("j2gha-ws-"), f"{jid}:{name.removeprefix('j2gha-ws-')}"}
                    files = None if keys & set(lost) else artifacts.get(name)
                    if files is not None and keys & set(corrupt):
                        files = {k: v[:len(v) // 2] if k.endswith(".tgz") else v for k, v in files.items()}
                    if files is not None and keys & set(incomplete):
                        files = {k: v for k, v in files.items() if not k.endswith(".changes")}
                    outcomes[st["id"]] = "success" if files is not None else "failure"
                    for name, data in (files or {}).items():
                        (ws / st["with"]["path"]).mkdir(parents=True, exist_ok=True)
                        (ws / st["with"]["path"] / name).write_bytes(data)
                elif handoff and uses.startswith("actions/upload-artifact"):
                    files = {line: (ws / line).read_bytes() for line in st["with"]["path"].splitlines()
                             if (ws / line).is_file()}
                    if not files:
                        raise StepFailed(f"{jid}: {st['name']}: no files found")
                    artifacts[st["with"]["name"]] = files
                elif uses.startswith("actions/checkout"):
                    # act treats a checkout of the repository it copied in as done
                    if not _restored(st.get("if"), outputs) and not prepopulated:
                        shutil.copytree(initial, ws, symlinks=True, dirs_exist_ok=True)
                elif "run" in st and (handoff or meta.get("kind") == "sh"):
                    if handoff and not _if(st.get("if"), outcomes):
                        continue
                    out = temp / "github-output"
                    out.write_text("")
                    env = {**{k: _needs(str(v), jobs, skipped) for k, v in (st.get("env") or {}).items()},
                           "GITHUB_WORKSPACE": str(ws), "GITHUB_OUTPUT": str(out), "RUNNER_TEMP": str(temp)}
                    p = _bash(st["run"], st.get("shell"), ws, env, temp)
                    if logs is not None:
                        logs.setdefault(jid, []).append(p.stdout + p.stderr)
                    if p.returncode:
                        raise StepFailed(f"{jid}: {st['name']} failed ({p.returncode}):\n{p.stdout}{p.stderr}")
                    if "id" in st:
                        outputs[st["id"]] = dict(line.split("=", 1) for line in out.read_text().splitlines()
                                                 if "=" in line)
            starts.setdefault(jid, tree(ws))
    finally:
        _remove(base)
    return starts


def _needs(value: str, jobs: dict[str, Any], skipped: set[str] | frozenset[str]) -> str:
    """`${{ needs.<job>.result }}`: success for a job that ran (a failing step stops the simulation), skipped."""
    return re.sub(r"\$\{\{ needs\.([\w-]+)\.result \}\}",
                  lambda m: "skipped" if m.group(1) in skipped else "success" if m.group(1) in jobs else "", value)


def jenkins(scripts: list[str], initial: Path) -> Tree:
    """Jenkins' one workspace: every stage's script, in declaration order, from the checkout."""
    base = Path(tempfile.mkdtemp(prefix="j2gha-ref-"))
    try:
        ws = base / "ws"
        shutil.copytree(initial, ws, symlinks=True)
        for script in scripts:
            p = subprocess.run(["bash", "-e", "-c", script], cwd=ws, capture_output=True, text=True)
            assert p.returncode == 0, p.stderr
        return tree(ws)
    finally:
        _remove(base)


def _remove(path: Path) -> None:
    for dirpath, dirnames, _ in os.walk(path):
        for name in dirnames:
            d = Path(dirpath) / name
            if not d.is_symlink():
                d.chmod(0o755)
    shutil.rmtree(path, ignore_errors=True)
