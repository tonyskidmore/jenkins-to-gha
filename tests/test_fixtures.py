"""Reproducibility checks: saved AST fixtures vs the current dumper, and the image provenance of run records.

The saved Groovy AST fixtures must be what the current dumper produces.

Most tests read ``tests/fixtures/<name>.ast.json`` instead of running the dumper, so a dumper change that is not
followed by regenerating the fixtures would leave the suite testing an AST the harness no longer produces.

- ``test_dumper_hash_matches_fixtures`` (cheap, runs in CI): the dumper's sha256 recorded with the fixtures.
- ``test_fixtures_match_current_dumper`` (``docker`` marker; needs ``j2gha/jenkins:local``): re-dumps every
  ``Jenkinsfile.<name>`` that has a ``<name>.ast.json`` and compares.

Regenerate both after changing the dumper: ``uv run python tests/test_fixtures.py``.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
DUMPER = ROOT / "docker" / "jenkins" / "groovy" / "ast_dump.groovy"
RECORD = FIXTURES / "DUMPER.sha256"
REGENERATE = ("regenerate the AST fixtures with the current dumper and record its hash: "
              "`uv run python tests/test_fixtures.py` (dump_sources({name: text}) for every Jenkinsfile.<name>, "
              "see .github/instructions/tests.instructions.md; needs the j2gha/jenkins:local image), then review the fixture diff")


def fixture_pairs() -> dict[str, Path]:
    """name -> Jenkinsfile.<name>, for every fixture that has a saved AST (new pairs are picked up automatically)."""
    return {p.name.split(".", 1)[1]: p for p in sorted(FIXTURES.glob("Jenkinsfile.*"))
            if (FIXTURES / f"{p.name.split('.', 1)[1]}.ast.json").exists()}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded_hashes() -> dict[str, str]:
    """``sha256sum`` format (``<hex>  <repo-relative path>``), so ``sha256sum -c`` works from the repo root."""
    out = {}
    for line in RECORD.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            digest, rel = line.split(maxsplit=1)
            out[rel.lstrip("*")] = digest
    return out


def test_dumper_hash_matches_fixtures():
    rel = DUMPER.relative_to(ROOT).as_posix()
    recorded = recorded_hashes().get(rel)
    assert recorded is not None, f"{RECORD.relative_to(ROOT)} has no entry for {rel}: {REGENERATE}"
    assert recorded == sha256(DUMPER), (f"{rel} changed since the AST fixtures were generated "
                                        f"(recorded {recorded[:12]}, now {sha256(DUMPER)[:12]}): {REGENERATE}")


def _first_difference(a, b, path="$"):
    if type(a) is not type(b):
        return f"{path}: {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f"{path}.{k}: only in {'saved' if k in a else 'fresh'} AST"
            d = _first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            d = _first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return None if len(a) == len(b) else f"{path}: {len(a)} items saved, {len(b)} fresh"
    return None if a == b else f"{path}: saved {a!r} != fresh {b!r}"


@pytest.mark.docker
def test_fixtures_match_current_dumper():
    from j2gha.analysis.ast import docker_image_exists, dump_sources
    from j2gha.config import JENKINS_IMAGE

    if not docker_image_exists(JENKINS_IMAGE):
        pytest.skip(f"{JENKINS_IMAGE} not built (`uv run j2gha docker build --only jenkins`)")
    pairs = fixture_pairs()
    assert pairs, "no AST fixture pairs found"
    fresh = dump_sources({name: p.read_text() for name, p in pairs.items()})
    stale = {}
    for name in pairs:
        saved = json.loads((FIXTURES / f"{name}.ast.json").read_text())
        diff = _first_difference(saved, fresh.get(name))
        if diff:
            stale[name] = diff
    assert not stale, f"AST fixtures differ from the current dumper: {stale}; {REGENERATE}"


# --------------------------------------------------------------------------- image provenance
def _fake_docker(images: dict, history: dict | None = None, calls: list | None = None):
    """subprocess.run stand-in: ``docker image inspect REF`` / ``docker image history ... REF`` from dicts."""

    def run(cmd, **_kw):
        if calls is not None:
            calls.append(cmd)
        if images is None:
            raise FileNotFoundError("docker")
        ref = cmd[-1]
        if cmd[1:3] == ["image", "inspect"]:
            if ref not in images:
                return subprocess.CompletedProcess(cmd, 1, "[]", f"Error: No such image: {ref}")
            return subprocess.CompletedProcess(cmd, 0, json.dumps([images[ref]]), "")
        if cmd[1:3] == ["image", "history"]:
            return subprocess.CompletedProcess(cmd, 0, (history or {}).get(ref, ""), "")
        raise AssertionError(f"unexpected command {cmd}")
    return run


def test_image_provenance_records_ids_digests_and_versions(monkeypatch):
    from j2gha.runners import images as im

    inspected = {
        im.JENKINS_IMAGE: {"Id": "sha256:jj", "RepoDigests": [], "Created": "2026-10-03T12:39:34Z",
                           "Config": {"Env": ["PATH=/bin", "JENKINS_VERSION=2.580.1"],
                                      "Labels": {"j2gha.base-image": "jenkins/jenkins:lts-jdk21@sha256:aa",
                                                 "org.opencontainers.image.version": "2.580.1", "other": "x"}}},
        im.ACT_IMAGE: {"Id": "sha256:aa", "RepoDigests": None, "Config": {"Env": None, "Labels": None}},
        im.ACT_RUNNER_IMAGE: {"Id": "sha256:rr", "RepoDigests": ["b@sha256:2", "a@sha256:1"],
                              "Config": {"Labels": {"org.opencontainers.image.version": "20260815"}}},
    }
    history = {im.ACT_IMAGE: "ENTRYPOINT [\"act\"]\nRUN |1 ACT_VERSION=0.2.89 /bin/sh -c apk add ...\n"}
    calls: list = []
    monkeypatch.setattr(im.subprocess, "run", _fake_docker(inspected, history, calls))
    prov = im.image_provenance()
    assert set(prov) == {"jenkins", "act", "act_runner", "jit_runner"}
    j = prov["jenkins"]
    assert j["present"] and j["id"] == "sha256:jj" and j["jenkins_version"] == "2.580.1"
    assert j["labels"] == {"j2gha.base-image": "jenkins/jenkins:lts-jdk21@sha256:aa",
                           "org.opencontainers.image.version": "2.580.1"}  # only provenance labels kept
    assert prov["act"]["act_version"] == "0.2.89" and prov["act"]["repo_digests"] == []  # history fallback
    assert prov["act_runner"]["repo_digests"] == ["a@sha256:1", "b@sha256:2"]
    missing = prov["jit_runner"]
    assert missing == {"ref": im.RUNNER_IMAGE, "present": False, "error": f"Error: No such image: {im.RUNNER_IMAGE}"}
    assert all(c[:3] == ["docker", "image", "inspect"] or c[:3] == ["docker", "image", "history"] for c in calls)

    # a label (images built from the current docker/act/Dockerfile) wins without reading the history
    inspected[im.ACT_IMAGE]["Config"]["Labels"] = {"j2gha.act-version": "0.2.90"}
    calls.clear()
    assert im.image_provenance()["act"]["act_version"] == "0.2.90"
    assert not any(c[2] == "history" for c in calls)


def test_image_provenance_never_raises(monkeypatch):
    from j2gha.runners import images as im

    monkeypatch.setattr(im.subprocess, "run", _fake_docker(None))  # no docker binary
    prov = im.image_provenance()
    assert all(r["present"] is False and r["error"] == "docker unavailable" for r in prov.values())

    sparse = _fake_docker({im.JENKINS_IMAGE: {}})  # no Config/Id at all

    def garbled(cmd, **kw):
        return sparse(cmd, **kw) if cmd[-1] == im.JENKINS_IMAGE else subprocess.CompletedProcess(cmd, 0, "not json", "")

    monkeypatch.setattr(im.subprocess, "run", garbled)
    prov = im.image_provenance()
    assert prov["act"]["present"] is False and prov["act"]["error"].startswith("JSONDecodeError")
    assert prov["jenkins"]["present"] is True and prov["jenkins"]["jenkins_version"] is None


def regenerate() -> None:
    sys.path.insert(0, str(ROOT))
    from j2gha.analysis.ast import dump_sources

    pairs = fixture_pairs()
    fresh = dump_sources({name: p.read_text() for name, p in pairs.items()})
    for name, ast in fresh.items():
        (FIXTURES / f"{name}.ast.json").write_text(json.dumps(ast))
    RECORD.write_text(f"{sha256(DUMPER)}  {DUMPER.relative_to(ROOT).as_posix()}\n")
    print(f"regenerated {len(fresh)} AST fixtures and {RECORD.name} in {FIXTURES}", file=sys.stderr)


if __name__ == "__main__":
    regenerate()
