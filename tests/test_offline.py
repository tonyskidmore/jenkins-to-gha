"""J2GHA_OFFLINE: no GitHub API calls (cached responses still serve), no source or docs fetch; the tiers that need
the network are refused, the local ones still run."""

import pytest

from j2gha import cli, config, stages
from j2gha.github import GitHub, OfflineError
from j2gha.runners import execute


def test_offline_github_serves_the_cache_and_makes_no_requests(tmp_path, monkeypatch):
    gh = GitHub(token="t")
    gh.cache_dir = tmp_path
    url = "https://api.github.com/repos/actions/checkout/commits/v4"
    gh._write_cache(gh._cache_path(url, None), {"sha": "a" * 40})
    monkeypatch.setattr(gh.session, "request", lambda *a, **k: pytest.fail("no request may leave the machine"))
    monkeypatch.setenv("J2GHA_OFFLINE", "1")
    assert config.offline()
    assert gh.request("GET", "/repos/actions/checkout/commits/v4") == {"sha": "a" * 40}  # cached: still served
    with pytest.raises(OfflineError, match="J2GHA_OFFLINE"):
        gh.request("GET", "/repos/actions/setup-node/commits/v4")
    with pytest.raises(OfflineError):
        gh.request("POST", "/repos/o/r/git/blobs", json_body={})


def test_unpinned_actions_are_the_ones_still_on_a_tag():
    wf = {"jobs": {"a": {"steps": [{"uses": "actions/checkout@" + "b" * 40}, {"uses": "actions/setup-node@v4"},
                                   {"uses": "./local"}, {"uses": "docker://alpine:3"}, {"run": "echo"}]}}}
    assert stages._unpinned_actions(wf) == {"actions/setup-node@v4"}


@pytest.fixture
def pipelines(tmp_path, monkeypatch):
    ex = tmp_path / "examples"
    for i, source in (("001", '{"repository": {"full_name": "o/r"}}'), ("002", None)):
        (ex / i).mkdir(parents=True)
        (ex / i / "Jenkinsfile").write_text("pipeline {}")
        if source:
            (ex / i / "source.json").write_text(source)
    (ex / "002" / "source.json").write_text("{}")  # cited, but no source repository to fetch
    monkeypatch.setattr(config, "EXAMPLES_DIR", ex)
    return ex


def test_offline_refuses_the_tiers_that_need_the_network(pipelines, monkeypatch):
    monkeypatch.setenv("J2GHA_OFFLINE", "1")
    refused = stages._refused_tiers(pipelines / "001", ["jenkins", "act", "selfhosted"], "trace")
    assert set(refused) == {"selfhosted"} and "OFFLINE" in refused["selfhosted"]  # even for a corpus example
    full = stages._refused_tiers(pipelines / "001", ["jenkins", "act"], "full")
    assert set(full) == {"jenkins", "act"} and "source repository" in full["act"]
    assert stages._refused_tiers(pipelines / "002", ["jenkins", "act"], "full") == {}  # nothing to fetch
    monkeypatch.delenv("J2GHA_OFFLINE")
    assert stages._refused_tiers(pipelines / "001", ["jenkins", "act", "selfhosted"], "full") == {}


def test_offline_run_keeps_the_local_tiers(pipelines, monkeypatch):
    seen = []
    monkeypatch.setattr(execute, "run_example",
                        lambda d, tiers, **kw: seen.append((d.name, tiers)) or {"statuses": {}, "verdicts": {}})
    assert cli.main(["run", "001", "--tier", "jenkins,act,hosted", "--offline", "--yes"]) == stages.EXIT_REFUSED
    assert seen == [("001", ["jenkins", "act"])]


def test_offline_docs_fetch_is_refused(monkeypatch):
    monkeypatch.setenv("J2GHA_OFFLINE", "1")
    with pytest.raises(SystemExit, match="J2GHA_OFFLINE"):
        cli.main(["docs", "fetch", "gha"])


@pytest.mark.parametrize("argv", [["crawl", "--count", "1"], ["budget"], ["environments"]])
def test_offline_github_commands_say_why_they_stop(monkeypatch, argv):
    monkeypatch.setenv("J2GHA_OFFLINE", "1")
    with pytest.raises(SystemExit, match="J2GHA_OFFLINE is set"):
        cli.main(argv)
