"""Run a workflow variant with nektos/act (packaged in docker/act) against the host Docker daemon.

No credential is handed to act: the variant's secrets are fakes (runners.variants), and in full mode the source
repository is fetched on the host, anonymously, into the workspace act copies into the job containers.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from ..config import ACT_IMAGE, ACT_RUNNER_IMAGE
from ..trace import parse_traces

# the variant's path in act's workspace (the outputs comparison recognises it as the harness's own file)
WORKFLOW_PATH = ".github/workflows/j2gha.yml"

ACT_CACHE_VOLUME = "j2gha-act-cache"

# act prints its local artifact server's token (a JWT) in debug lines; committed run logs must not carry it
RUNTIME_TOKEN = re.compile(r"(ACTIONS_RUNTIME_TOKEN=)[A-Za-z0-9._-]+")


def log(msg: str) -> None:
    print(f"[act] {msg}", file=sys.stderr, flush=True)


def _git(ws: Path, *args: str) -> None:
    # gc.auto=0: committing a large source tree would start a background `git gc` that packs (and deletes) the loose
    # objects while act copies the workspace into the job ("lstat .git/objects/..: no such file", 009/109 checkout)
    subprocess.run(["git", "-c", "gc.auto=0", *args], cwd=ws, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "j2gha", "GIT_AUTHOR_EMAIL": "j2gha@localhost",
                        "GIT_COMMITTER_NAME": "j2gha", "GIT_COMMITTER_EMAIL": "j2gha@localhost"})


def _in_act_image(path: Path, *command: str) -> None:
    subprocess.run(["docker", "run", "--rm", "-v", f"{path}:{path}", "--entrypoint", command[0], ACT_IMAGE,
                    *command[1:]], capture_output=True, check=False)


def _reset_artifacts(path: Path) -> None:
    """act's artifact server runs as root; artifacts from runs before ownership was handed back need root to remove."""
    if path.exists():
        try:
            shutil.rmtree(path)
        except PermissionError:
            _in_act_image(path, "sh", "-c", f"rm -rf {shlex.quote(str(path))}/*")
            shutil.rmtree(path)
    path.mkdir(parents=True)
    # act's v4 artifact server lists a run's artifacts by reading <path>/<run id> (act's run id is always 1) and
    # panics, resetting the connection, while nothing was uploaded yet: a download by pattern of an allowEmpty stash
    # that stashed nothing must find an empty list there, as on GitHub (review R8-6)
    (path / "1").mkdir()


def _fetch_source(ws: Path, source: dict[str, Any]) -> None:
    """The source repository at the pinned commit (public GitHub repositories: no credentials are used)."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    url = f"https://github.com/{source['repository']}.git"
    for args in (["init", "-q"], ["fetch", "-q", "--depth", "1", url, source.get("sha") or "HEAD"],
                 ["checkout", "-q", "FETCH_HEAD"]):
        subprocess.run(["git", "-c", "credential.helper=", *args], cwd=ws, check=True, capture_output=True, env=env,
                       timeout=600)
    shutil.rmtree(ws / ".git")


def run_act(out_dir: Path, workflow_yaml: str, branch: str, mode: str, source: dict[str, Any] | None = None,
            timeout: int = 1800) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    ws = out_dir / "workspace"
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    if source and source.get("repository"):
        _fetch_source(ws, source)
    (ws / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (ws / WORKFLOW_PATH).write_text(workflow_yaml)
    # act derives github.ref/sha from the git checkout: commit on the scenario branch
    _git(ws, "init", "-q", "-b", branch)
    _git(ws, "add", "-A")
    _git(ws, "commit", "-q", "-m", "j2gha act run")
    artifacts = out_dir / "artifacts"
    _reset_artifacts(artifacts)
    name = f"j2gha-act-{uuid.uuid4().hex[:12]}"
    cmd = ["docker", "run", "--rm", "--name", name, "-v", "/var/run/docker.sock:/var/run/docker.sock",
           "-v", f"{ws}:{ws}", "-v", f"{artifacts}:{artifacts}", "-w", str(ws),
           "-v", f"{ACT_CACHE_VOLUME}:/root/.cache/act", ACT_IMAGE,
           "push", "-W", WORKFLOW_PATH,
           "-P", f"ubuntu-latest={ACT_RUNNER_IMAGE}", "-P", f"ubuntu-24.04={ACT_RUNNER_IMAGE}",
           "-P", f"ubuntu-22.04={ACT_RUNNER_IMAGE}", "-P", f"ubuntu-24.04-arm={ACT_RUNNER_IMAGE}",
           "--pull=false", "--rm", "--json", "--container-architecture", "linux/amd64",
           # a SHA-pinned action's cached copy is current (one left on a tag may be stale); re-fetching races between
           # parallel jobs
           # ("remove .../actions-upload-artifact@<sha>/.gitignore: no such file or directory")
           "--action-offline-mode",
           # job containers must not get the host Docker socket: full-mode runs execute third-party build scripts
           "--container-daemon-socket", "-",
           "--artifact-server-path", str(artifacts)]
    env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_TOKEN", "GH_TOKEN")}
    started = time.time()
    log(f"running act ({mode}) in {ws}")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        rc, stdout, stderr = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        rc, stdout, stderr = 124, (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
        # killing the docker client leaves act running: stop it (SIGTERM lets act remove its job containers)
        subprocess.run(["docker", "stop", "-t", "60", name], capture_output=True, timeout=120)
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=60)
    stdout = RUNTIME_TOKEN.sub(r"\1***", stdout)
    (out_dir / "act.jsonl").write_text(stdout)
    (out_dir / "act.stderr.log").write_text(stderr)
    _in_act_image(artifacts, "chown", "-R", f"{os.getuid()}:{os.getgid()}", str(artifacts))  # written as root
    msgs: list[str] = []
    jobs: dict[str, dict[str, Any]] = {}
    failed_steps: list[str] = []
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            msgs.append(line)
            continue
        msg = str(ev.get("msg", ""))
        msgs.append(msg)
        jid = ev.get("jobID") or ev.get("job")
        if jid and ev.get("matrix"):
            jid = f"{jid} {json.dumps(ev['matrix'], sort_keys=True)}"
        if jid and ev.get("jobResult"):
            jobs[jid] = {"result": ev["jobResult"]}
        if ev.get("stepResult") == "failure" and ev.get("stage") == "Main":
            failed_steps.append(str(ev.get("step", "")))
    traces = parse_traces("\n".join(msgs))
    result = "success" if rc == 0 else ("timeout" if rc == 124 else "failure")
    record = {"tier": "act", "mode": mode, "result": result, "exit_code": rc, "seconds": round(time.time() - started, 1),
              "jobs": jobs, "traces": traces, "failed_steps": failed_steps,
              "error_tail": stderr.strip().splitlines()[-8:] if rc else None}
    log(f"act {mode} -> {result} ({len(traces)} trace events, {len(jobs)} job results) in {record['seconds']}s")
    return record
