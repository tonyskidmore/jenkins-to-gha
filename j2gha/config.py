"""Paths and shared settings for the harness."""

from __future__ import annotations

import os
from pathlib import Path


def _find_root() -> Path:
    env = os.environ.get("J2GHA_ROOT")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "j2gha").is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent


ROOT = _find_root()
EXAMPLES_DIR = ROOT / "examples"
CACHE_DIR = ROOT / ".cache"
STATE_DIR = ROOT / ".j2gha"
DOCKER_DIR = ROOT / "docker"

# Docker images built/used by the harness.
JENKINS_IMAGE = os.environ.get("J2GHA_JENKINS_IMAGE", "j2gha/jenkins:local")
# Build-time base, pinned by digest like docker/jenkins/Dockerfile's default (keep the two equal). The other images are
# built locally from docker/<name>/Dockerfile (each pins its own base by digest and records it in the j2gha.base-image
# label); j2gha.runners.images.image_provenance() records what a run used.
JENKINS_BASE_IMAGE = os.environ.get(
    "J2GHA_JENKINS_BASE",
    "jenkins/jenkins:lts-jdk21@sha256:a660310e39ade10631f774bacd5219de767dfd08947ea5c32a739b5e5bb382c1")
ACT_IMAGE = os.environ.get("J2GHA_ACT_IMAGE", "j2gha/act:local")
# Job containers for act and the JIT self-hosted runners: catthehacker/ubuntu:act-latest and
# ghcr.io/actions/actions-runner plus the toolchain the Jenkins image has (maven, node, make, python, xvfb ...).
ACT_RUNNER_IMAGE = os.environ.get("J2GHA_ACT_RUNNER_IMAGE", "j2gha/act-runner:local")
RUNNER_IMAGE = os.environ.get("J2GHA_RUNNER_IMAGE", "j2gha/runner:local")  # JIT self-hosted runners
ACTIONLINT_IMAGE = os.environ.get("J2GHA_ACTIONLINT_IMAGE", "rhysd/actionlint:latest")
ZIZMOR_IMAGE = os.environ.get("J2GHA_ZIZMOR_IMAGE", "ghcr.io/zizmorcore/zizmor:latest")

JENKINS_CONTAINER = "j2gha-jenkins"
JENKINS_PORT = int(os.environ.get("J2GHA_JENKINS_PORT", "18080"))
JENKINS_USER = "admin"
JENKINS_PASSWORD = os.environ.get("J2GHA_JENKINS_PASSWORD", "j2gha-local-only")


def offline() -> bool:
    """J2GHA_OFFLINE: the harness itself makes no GitHub API calls (cached responses still serve) and fetches no source
    repository or docs. Docker image pulls and act's first download of each public action are not covered."""
    return os.environ.get("J2GHA_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


def pipelines_dir() -> Path | None:
    """J2GHA_PIPELINES_DIR: where your own pipelines live, outside the clone, so neither a pipeline nor anything the
    stages write next to it is in this (public) repository's working tree. None when unset."""
    env = os.environ.get("J2GHA_PIPELINES_DIR")
    return Path(env).expanduser().resolve() if env else None


def example_dir(example_id: str | int) -> Path:
    """A pipeline's directory: in J2GHA_PIPELINES_DIR when set, unless only the corpus has the id (`003`, `000`)."""
    i = normalise_id(example_id)
    own = pipelines_dir()
    if own is not None and ((own / i).is_dir() or not (EXAMPLES_DIR / i).is_dir()):
        return own / i
    return EXAMPLES_DIR / i


def display_dir(d: Path) -> str:
    """How generated files name a pipeline's directory: relative to the clone, never an absolute local path."""
    d = d.resolve()
    try:
        return str(d.relative_to(ROOT.resolve()))
    except ValueError:
        return d.name


def is_corpus(d: Path) -> bool:
    """A public corpus example: a crawled original or twin (cited in source.json) or the walkthrough."""
    d = d.resolve()
    return d.parent == EXAMPLES_DIR.resolve() and ((d / "source.json").exists() or is_walkthrough(d))


def normalise_id(example_id: str | int) -> str:
    text = str(example_id).strip().strip("/")
    text = text.split("/")[-1]
    if text.isdigit():
        return f"{int(text):03d}"
    return text


# A hand-written walkthrough example (examples/000) carries this marker in its README: harness stages write their
# results to RESULTS.md instead, and `all`, the crawler and the corpus summary skip it.
WALKTHROUGH_MARKER = "<!-- j2gha:walkthrough -->"


def is_walkthrough(d: Path) -> bool:
    readme = d / "README.md"
    return readme.exists() and WALKTHROUGH_MARKER in readme.read_text()


def list_example_ids() -> list[str]:
    if not EXAMPLES_DIR.exists():
        return []
    return sorted(p.name for p in EXAMPLES_DIR.iterdir() if p.is_dir() and p.name.isdigit() and not is_walkthrough(p))


def list_pipeline_ids() -> list[str]:
    """What `all` means on the command line: every pipeline in J2GHA_PIPELINES_DIR when set, else the corpus."""
    own = pipelines_dir()
    if own is None:
        return list_example_ids()
    if not own.is_dir():
        return []
    return sorted(p.name for p in own.iterdir() if (p / "Jenkinsfile").is_file() and not is_walkthrough(p))
