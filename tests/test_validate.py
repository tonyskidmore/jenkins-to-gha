"""Static validators fail closed: a scanner that did not run, or output that cannot be read, is never 'clean'."""

import json
import subprocess

import pytest

from j2gha.validate import static


def _proc(rc: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


@pytest.fixture
def fake_run(monkeypatch):
    results: dict[str, subprocess.CompletedProcess] = {}

    def run(cmd, **_kw):
        tool = "zizmor" if any("zizmor" in str(c) for c in cmd) else "actionlint"
        return results[tool]
    monkeypatch.setattr(static.subprocess, "run", run)
    return results


@pytest.mark.parametrize("proc", [
    _proc(125, stderr="docker: Error response from daemon"),  # docker could not start the scanner
    _proc(1, stderr="fatal: no such file"),  # --no-exit-codes: any non-zero exit is a scanner failure
    _proc(0, stdout="not json"),
    _proc(0, stdout="{}"),  # wrong schema
    _proc(0, stdout='{"a": 1}'),
    _proc(0, stdout=""),
])
def test_zizmor_failures_are_errors(fake_run, tmp_path, proc):
    fake_run["zizmor"] = proc
    r = static.run_zizmor(tmp_path)
    assert r["ok"] is False and r["error"] and r["findings"] == []


@pytest.mark.parametrize("proc", [
    _proc(125, stderr="docker: pull access denied"),
    _proc(1, stdout="not json"),
    _proc(1, stdout=""),  # exit 1 means findings were reported - none is a failed run
    _proc(0, stdout='{"x": 1}'),
])
def test_actionlint_failures_are_errors(fake_run, tmp_path, proc):
    fake_run["actionlint"] = proc
    r = static.run_actionlint(tmp_path)
    assert r["ok"] is False and r["error"]


def test_clean_runs_and_findings(fake_run, tmp_path):
    fake_run["actionlint"] = _proc(0, stdout="[]")
    fake_run["zizmor"] = _proc(0, stdout="[]")
    assert static.run_actionlint(tmp_path)["ok"] and static.run_zizmor(tmp_path)["ok"]
    fake_run["actionlint"] = _proc(1, stdout=json.dumps([{"line": 3, "column": 1, "kind": "shellcheck",
                                                           "message": "SC2086"}]))
    r = static.run_actionlint(tmp_path)
    assert r["ok"] and r["shellcheck"] == 1 and not r.get("error")  # shellcheck findings are not structural


def _example(tmp_path):
    d = tmp_path / "001"
    (d / "gha").mkdir(parents=True)
    (d / "gha" / "workflow.yml").write_text("name: x\non: push\npermissions: {contents: read}\njobs:\n"
                                            "  a:\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n"
                                            "    steps:\n    - run: 'true'\n")
    (d / "README.md").write_text("# x\n")
    return d


def test_aggregate_separates_structure_security_and_tool_errors(fake_run, tmp_path):
    d = _example(tmp_path)
    fake_run["actionlint"] = _proc(0, stdout="[]")
    high = [{"ident": "unpinned-images", "desc": "x", "determinations": {"severity": "High", "confidence": "High"},
             "locations": []}]
    fake_run["zizmor"] = _proc(0, stdout=json.dumps(high))
    v = static.validate_example(d)
    # security findings are advisory but visible; the structural result gates
    assert v["ok"] and v["structural_ok"] and not v["security_ok"] and v["tools_ok"]
    assert "⚠️" in (d / "README.md").read_text()
    fake_run["zizmor"] = _proc(125, stderr="docker: Error")
    v = static.validate_example(d)
    assert not v["ok"] and not v["tools_ok"] and v["zizmor"]["error"]
    assert "tool error" in (d / "README.md").read_text()
