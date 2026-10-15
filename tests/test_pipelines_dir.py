"""Your own pipelines outside the clone: J2GHA_PIPELINES_DIR, `j2gha add`, and the remote tiers' refusal to push them
to a repository that is not private."""

from pathlib import Path

import pytest

from j2gha import cli, config, stages
from j2gha.runners import execute


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    ex = tmp_path / "clone" / "examples"
    for i in ("000", "001"):
        (ex / i).mkdir(parents=True)
        (ex / i / "Jenkinsfile").write_text("pipeline {}")
    (ex / "001" / "source.json").write_text("{}")
    (ex / "000" / "README.md").write_text(config.WALKTHROUGH_MARKER)
    monkeypatch.setattr(config, "EXAMPLES_DIR", ex)
    monkeypatch.setattr(config, "ROOT", ex.parent)
    return ex


@pytest.fixture
def own(tmp_path, monkeypatch):
    d = tmp_path / "mine"
    (d / "app").mkdir(parents=True)
    (d / "app" / "Jenkinsfile").write_text("pipeline { agent any }")
    monkeypatch.setenv("J2GHA_PIPELINES_DIR", str(d))
    return d


def test_pipelines_dir_holds_your_pipelines_and_the_corpus_stays_reachable(corpus, own):
    assert config.example_dir("app") == own / "app"
    assert config.example_dir("1") == corpus / "001"  # only the corpus has it
    assert config.example_dir("new") == own / "new"  # neither has it: it belongs in the pipelines directory
    assert config.list_pipeline_ids() == ["app"]  # `all`
    assert config.display_dir(own / "app") == "app"  # generated files never name the local path
    assert config.display_dir(corpus / "001") == "examples/001"


def test_without_a_pipelines_dir_all_is_the_corpus(corpus):
    assert config.pipelines_dir() is None
    assert config.list_pipeline_ids() == ["001"]
    assert config.example_dir("app") == corpus / "app"


def test_corpus_examples_are_the_cited_ones_and_the_walkthrough(corpus, own):
    (corpus / "named").mkdir()
    assert config.is_corpus(corpus / "001") and config.is_corpus(corpus / "000")
    assert not config.is_corpus(corpus / "named")  # your pipeline, put in examples/ by hand
    assert not config.is_corpus(own / "app")


def test_add_copies_any_jenkinsfile_in_under_a_safe_name(corpus, own, tmp_path):
    src = tmp_path / "src" / "payments"
    src.mkdir(parents=True)
    (src / "Jenkinsfile.deploy").write_text("pipeline { agent none }")
    d = stages.add_pipeline(src / "Jenkinsfile.deploy")
    assert d == own / "payments-jenkinsfile-deploy"
    assert (d / "Jenkinsfile").read_text() == "pipeline { agent none }"
    (src / "Jenkinsfile").write_text("a")
    assert stages.add_pipeline(src) == own / "payments"  # a directory: its Jenkinsfile
    assert stages.pipeline_name(Path("/x/42/Jenkinsfile")) == "p-42"  # never a corpus id
    stages.add_pipeline(src)  # the same content again is fine
    (src / "Jenkinsfile").write_text("b")
    with pytest.raises(ValueError, match="--force"):
        stages.add_pipeline(src)
    assert (stages.add_pipeline(src, force=True) / "Jenkinsfile").read_text() == "b"
    for bad in ("007", "-x", "a/b", "a b"):
        with pytest.raises(ValueError, match="pipeline name"):
            stages.add_pipeline(src, name=bad)
    with pytest.raises(ValueError, match="no such file"):
        stages.add_pipeline(tmp_path / "missing")


def test_add_without_a_pipelines_dir_warns_that_examples_is_public(corpus, tmp_path, capsys):
    f = tmp_path / "Jenkinsfile"
    f.write_text("pipeline {}")
    assert stages.add_pipeline(f, name="mine") == corpus / "mine"
    assert "J2GHA_PIPELINES_DIR" in capsys.readouterr().err


def test_cli_add_option_and_a_clear_error_for_a_missing_jenkinsfile(corpus, own, tmp_path, monkeypatch):
    f = tmp_path / "ci.groovy"
    f.write_text("pipeline {}")
    other = tmp_path / "other"
    assert cli.main(["add", str(f), "--name", "ci", "--pipelines-dir", str(other)]) == 0
    assert (other / "ci" / "Jenkinsfile").is_file()  # the option overrides J2GHA_PIPELINES_DIR
    with pytest.raises(SystemExit, match="no Jenkinsfile for nope"):
        cli.main(["convert", "nope"])
    seen = {}
    monkeypatch.setattr(stages, "convert_examples", lambda ids: seen.setdefault("ids", ids))
    assert cli.main(["convert"]) == 0
    assert seen["ids"] == ["ci"]  # `all`: every pipeline in the pipelines directory
    with pytest.raises(SystemExit, match="no pipelines in"):
        cli.main(["analyze", "--pipelines-dir", str(tmp_path / "empty")])


def test_gaps_reads_your_pipelines_from_the_pipelines_dir(corpus, own, monkeypatch):
    from j2gha import improve
    got = {}
    monkeypatch.setattr(improve, "gaps", lambda ids, **kw: got.update(ids=ids, **kw) or [])
    monkeypatch.setattr(improve, "format_gaps", lambda rows, limit: "")
    assert cli.main(["gaps"]) == 0
    assert got["ids"] == ["app"] and got["examples_dir"] == own


class FakeGitHub:
    repos: dict = {}
    calls: list = []

    def request(self, method, path, use_cache=True):
        self.calls.append((method, path, use_cache))
        return self.repos[path]


def test_remote_tiers_push_your_pipelines_only_to_a_private_j2gha_repo(corpus, own, monkeypatch):
    monkeypatch.setattr("j2gha.github.GitHub", FakeGitHub)
    FakeGitHub.repos = {"/repos/me/pub": {"private": False, "visibility": "public"},
                        "/repos/me/priv": {"private": True, "visibility": "private"},
                        "/repos/org/inner": {"private": True, "visibility": "internal"}}
    FakeGitHub.calls = []
    monkeypatch.delenv("J2GHA_REPO", raising=False)
    assert "set J2GHA_REPO" in stages.remote_refusal(own / "app")  # default target: the clone's (public) origin
    assert "set J2GHA_REPO" in stages.remote_refusal(corpus / "named")  # your pipeline, put in examples/ by hand
    assert stages.remote_refusal(corpus / "001") is None and stages.remote_refusal(corpus / "000") is None
    assert FakeGitHub.calls == []  # corpus examples need no lookup
    monkeypatch.setenv("J2GHA_REPO", "me/pub")
    assert "is public" in stages.remote_refusal(own / "app")
    for repo in ("me/priv", "org/inner"):
        monkeypatch.setenv("J2GHA_REPO", repo)
        assert stages.remote_refusal(own / "app") is None
    assert all(use_cache is False for _, _, use_cache in FakeGitHub.calls)  # visibility is never read from a cache


def test_a_refused_remote_tier_still_runs_the_local_ones(corpus, own, monkeypatch):
    monkeypatch.delenv("J2GHA_REPO", raising=False)
    seen = []
    monkeypatch.setattr(execute, "run_example",
                        lambda d, tiers, **kw: seen.append((d.name, tiers)) or {"statuses": {}, "verdicts": {}})
    assert stages.run_examples(["app"], ["jenkins", "selfhosted"]) == stages.EXIT_REFUSED
    assert seen == [("app", ["jenkins"])]
    seen.clear()
    assert stages.run_examples(["app"], ["hosted"]) == stages.EXIT_REFUSED and seen == []
    assert stages.run_examples(["001"], ["jenkins", "hosted"]) == stages.EXIT_OK  # corpus: unchanged
    assert seen == [("001", ["jenkins", "hosted"])]


def test_summary_indexes_the_pipelines_dir(corpus, own, monkeypatch):
    import json
    (own / "app" / "analysis").mkdir()
    (own / "app" / "analysis" / "analysis.json").write_text(json.dumps(
        {"dialect": "declarative", "complexity": {"score": 52, "classification": "significant-redesign",
                                                  "hard_gates": ["SharedLibrary"]}}))
    (own / "app" / "gha").mkdir()
    (own / "app" / "gha" / "conversion.json").write_text(json.dumps({"automation_pct": 59.0, "counts": {"manual": 46}}))
    (own / "bare").mkdir()
    (own / "bare" / "Jenkinsfile").write_text("pipeline {}")
    monkeypatch.setattr(stages, "summarize_examples", lambda: pytest.fail("the corpus index is not rewritten"))
    assert cli.main(["summary"]) == 0
    text = (own / "README.md").read_text()
    assert "| [app](app/README.md) | `declarative` | 52 significant-redesign | SharedLibrary | 59.0% (46 manual) |" in text
    assert "| [bare](bare/README.md) | `-` | - " in text
