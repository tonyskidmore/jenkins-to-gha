"""Build/pull the Docker images used by the harness, and record which images a run used."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import Any

from ..config import ACT_IMAGE, ACT_RUNNER_IMAGE, DOCKER_DIR, JENKINS_IMAGE, RUNNER_IMAGE
from ..jenkins.controller import build_image as build_jenkins
from ..validate.static import ACTIONLINT_PINNED, ZIZMOR_PINNED

# Labels worth keeping in a run record (the j2gha.* ones are set by docker/*/Dockerfile).
_LABELS = ("j2gha.base-image", "j2gha.act-version", "org.opencontainers.image.version",
           "org.opencontainers.image.revision", "org.opencontainers.image.source")


def _run(*cmd: str) -> None:
    print("+ " + " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)


#: ``docker build --only`` choices: the harness-built images (``docker/<name>/Dockerfile``).
BUILD_TARGETS = ("jenkins", "act", "act-runner", "runner")


def build_all(only: str | None = None) -> None:
    """Build the harness images (all of them, or just ``only``) and pull the pinned lint images.

    ``act`` is the act CLI image; ``act-runner`` and ``runner`` are the job containers act and the JIT self-hosted
    runners use. Both are built here rather than pulled so they carry the same toolchain as the Jenkins image.
    """
    if only in (None, "jenkins"):
        build_jenkins()
    if only in (None, "act"):
        _run("docker", "build", "-t", ACT_IMAGE, str(DOCKER_DIR / "act"))
    if only in (None, "act-runner"):
        _run("docker", "build", "-t", ACT_RUNNER_IMAGE, str(DOCKER_DIR / "act-runner"))
    if only in (None, "runner"):
        _run("docker", "build", "-t", RUNNER_IMAGE, str(DOCKER_DIR / "runner"))
    if only is None:
        for img in (ACTIONLINT_PINNED, ZIZMOR_PINNED):
            _run("docker", "pull", img)


def _docker(*args: str, timeout: int = 15) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None


def _inspect(ref: str) -> dict[str, Any]:
    """Identity of a local image from its metadata only (no container start, no registry access)."""
    rec: dict[str, Any] = {"ref": ref, "present": False}
    p = _docker("image", "inspect", ref)
    if p is None or p.returncode != 0:
        rec["error"] = "docker unavailable" if p is None else ((p.stderr or "").strip()[-200:] or f"exit {p.returncode}")
        return rec
    info = json.loads(p.stdout)[0]
    config = info.get("Config") or {}
    labels = config.get("Labels") or {}
    env = dict(e.split("=", 1) for e in config.get("Env") or [] if "=" in e)
    rec.update(present=True, id=info.get("Id"), repo_digests=sorted(info.get("RepoDigests") or []),
               created=info.get("Created"), labels={k: labels[k] for k in _LABELS if k in labels})
    rec["_env"] = env
    return rec


def _act_version(rec: dict[str, Any]) -> str | None:
    """j2gha.act-version label; images built before the label existed carry ACT_VERSION in their build history."""
    if rec["labels"].get("j2gha.act-version"):
        return rec["labels"]["j2gha.act-version"]
    p = _docker("image", "history", "--no-trunc", "--format", "{{.CreatedBy}}", rec["ref"])
    m = re.search(r"\bACT_VERSION=([\w.+-]+)", p.stdout) if p is not None and p.returncode == 0 else None
    return m.group(1) if m else None


def image_provenance() -> dict[str, Any]:
    """Which images a run used: id, repo digests and version labels of the Jenkins, act, act-runner and JIT runner
    images as configured (``docker image inspect`` only, so it is fast and works offline). Best-effort: it never
    raises; a missing image or Docker daemon is reported as ``present: false`` with an ``error``.

    Locally built images (the ``j2gha/*:local`` defaults) have no repo digest: their ``id`` plus ``j2gha.base-image``
    (the digest-pinned base) and the committed Dockerfile/plugins.txt identify them. For a pulled image substituted
    through the ``J2GHA_*_IMAGE`` variables (whose tags float), the ``id``/``repo_digests`` recorded here are what
    make a result reproducible (pull ``<repo>@<digest>``).
    """
    out: dict[str, Any] = {}
    for role, ref in (("jenkins", JENKINS_IMAGE), ("act", ACT_IMAGE), ("act_runner", ACT_RUNNER_IMAGE),
                      ("jit_runner", RUNNER_IMAGE)):
        try:
            rec = _inspect(ref)
            env = rec.pop("_env", {})
            if rec["present"] and role == "jenkins":
                rec["jenkins_version"] = env.get("JENKINS_VERSION") or rec["labels"].get(
                    "org.opencontainers.image.version")
            elif rec["present"] and role == "act":
                rec["act_version"] = _act_version(rec)
        except Exception as e:  # noqa: BLE001 - provenance must never break a run
            rec = {"ref": ref, "present": False, "error": f"{type(e).__name__}: {e}"[:200]}
        out[role] = rec
    return out
