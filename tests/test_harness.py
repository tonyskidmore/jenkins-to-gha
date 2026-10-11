from datetime import datetime, timezone

import pytest

from j2gha.analysis.analyze import analyse
from j2gha.crawl.scoring import MAX, score_candidate
from j2gha.jenkins.localize import localize, repairs_from_errors
from j2gha.trace import compare, parse_traces


def test_parse_and_compare_traces():
    jenkins_log = "\n".join([
        "[2026-10-03T06:12:10.147Z] J2GHA-TRACE {\"stage\":\"Build\",\"step\":\"sh\"}",
        "J2GHA-TRACE {\"stage\":\"Build\",\"step\":\"junit\"}",
        "noise",
    ])
    gha_log = "\n".join([
        "Run printf '%s %s\\n' J2GHA-TRACE '{\"stage\":\"Build\",\"step\":\"sh\"}'",  # echoed command: ignored
        "J2GHA-TRACE {\"stage\":\"Build\",\"step\":\"sh\"}",
    ])
    ref, cand = parse_traces(jenkins_log), parse_traces(gha_log)
    assert [t["step"] for t in ref] == ["sh", "junit"]
    assert len(cand) == 1
    c = compare(ref, cand)
    assert not c["equivalent"] and c["similarity_pct"] == 50.0
    assert compare(ref, ref)["equivalent"]


def test_localize_trace_mode(declarative):
    text, ast = declarative
    a = analyse(text, ast)
    loc = localize(text, ast, a, "trace")
    original_lines = len(text.splitlines())
    # the localisation block is appended so Jenkins error line numbers match the original file
    assert loc.script.splitlines()[0] == text.splitlines()[0]
    assert len(loc.script.splitlines()) > original_lines
    assert "agent any" in loc.script and "label 'linux'" not in loc.script.split("j2gha localisation block")[0]
    assert "triggers removed" in loc.script
    assert "def sh(Object... a)" in loc.script and "j2ghaTrace('sh')" in loc.script
    assert "@groovy.transform.Field def scm" in loc.script


def test_localize_scripted_imports_and_library(scripted):
    text, ast = scripted
    a = analyse(text, ast)
    loc = localize(text, ast, a, "trace")
    assert "@Library removed" in loc.script
    assert "import com.example.Config removed" in loc.script
    assert "class Config extends J2ghaAny" in loc.script
    assert "node('built-in')" in loc.script


def test_localize_removes_options_valued_from_stubbed_classes(library_options):
    # PipelineDefaults is stubbed (J2ghaAny), which the gitLabConnection describable cannot coerce to a String
    text, ast = library_options
    a = analyse(text, ast)
    loc = localize(text, ast, a, "trace")
    body = loc.script.split("j2gha localisation block")[0]
    assert "gitLabConnection(" not in body and "/* j2gha: options gitLabConnection removed */" in body
    assert "timeout(time: 1, unit: 'HOURS')" in body
    assert any("'gitLabConnection' removed (value from stubbed PipelineDefaults)" in c for c in loc.changes)
    assert "class PipelineDefaults extends J2ghaAny" in loc.script


def test_localize_removes_parameters_valued_from_stubbed_library_calls(library_options):
    # billingProjects() is a shared-library global (a bare call the catalog does not know, listed by the analysis
    # as neither step nor symbol because it sits inside choice()'s arguments): stubbed, it returns a J2ghaAny that
    # ChoiceParameterDefinition cannot coerce (021 failed before any stage). The String default is left to the
    # stringify-args repair, and a Groovy call (join) is not a stub.
    text, ast = library_options
    a = analyse(text, ast)
    assert not any(u["name"] == "billingProjects" for u in a["unknown_steps"]) and "billingProjects" not in a["dsl_symbols"]
    loc = localize(text, ast, a, "full")
    body = loc.script.split("// ---- j2gha localisation block")[0]
    assert "billingProjects()" not in body and "/* j2gha: parameters choice removed */" in body
    assert "defaultBranch()" in body and "choices: ['low', 'high'].join('\\n')" in body and "name: 'REGION'" in body
    assert any("'choice' removed (value from stubbed billingProjects())" in c for c in loc.changes)
    assert len(body.rstrip("\n").splitlines()) == len(text.rstrip("\n").splitlines())  # line numbers unchanged
    # a step the repair loop stubbed at run time (No such DSL method) counts too, and the rule is per entry
    loc = localize(text, ast, a, "full", extra_stubs=["defaultBranch"])
    assert "def defaultBranch(Object... a)" in loc.script and "defaultBranch()" in loc.script.split("j2gha localisation block")[0]



def test_localize_promotes_script_var_read_before_stubbed_setter(script_vars):
    # `def buildType` after pipeline {} is out of scope there; customizePublishingInfo() (stubbed) would set it
    text, ast = script_vars
    a = analyse(text, ast)
    assert localize(text, ast, a, "trace").script.splitlines()[23] == "def buildType"  # only once Jenkins reports it
    loc = localize(text, ast, a, "trace", remove=[("stub-property", "buildType"), ("stub-property", "libName")])
    lines = loc.script.splitlines()
    assert lines[23] == "@groovy.transform.Field def buildType = new J2ghaAny()"  # same line as the original
    assert lines[24] == "def libName = 'node'"  # has an initialiser: left alone
    assert "def buildType = new J2ghaAny()" not in "\n".join(lines[25:])  # no duplicate in the appended block
    assert any("'buildType' unset when read" in c for c in loc.changes)


def test_localize_promotes_script_tuple_declaration_in_place(script_vars):
    # def (retries, delay) = [0, 5] after pipeline {}: Jenkins reports one unset name per build, and an appended
    # @Field for it would not compile ("The current scope already contains a variable", 021's timeouts), so the
    # whole tuple is promoted on its own line, keeping the literal initialisers
    text, ast = script_vars
    a = analyse(text, ast)
    assert "def (retries, delay) = [0, 5]" in localize(text, ast, a, "full").script  # untouched until reported
    loc = localize(text, ast, a, "full", remove=[("stub-property", "delay")])
    lines = loc.script.splitlines()
    assert lines[27] == "@groovy.transform.Field def retries = 0; @groovy.transform.Field def delay = 5"
    block = loc.script.split("// ---- j2gha localisation block")[1]
    assert "def delay" not in block and "def retries" not in block
    assert any("script variables retries, delay unset when read" in c for c in loc.changes)
    assert len(loc.script.split("// ---- j2gha localisation block")[0].rstrip("\n").splitlines()) == len(text.rstrip("\n").splitlines())


@pytest.mark.parametrize("mode", ["trace", "full"])
def test_localize_keeps_original_line_numbers(script_vars, mode):
    # Jenkins error lines must match the Jenkinsfile: the quote-env repair is keyed on them
    text, ast = script_vars
    a = analyse(text, ast)
    loc = localize(text, ast, a, mode, remove=[("fill-stage", "Init"), ("quote-env", 8), ("stub-property", "buildType")])
    assert len(loc.changes) == 4
    body = loc.script.split("// ---- j2gha localisation block")[0].rstrip("\n").splitlines()
    orig = text.rstrip("\n").splitlines()
    assert len(body) == len(orig)
    edited = {n for n, (b, o) in enumerate(zip(body, orig, strict=True), 1) if b != o}
    assert edited == {2, 3, 4, 5, 6, 8, 13, 24}  # agent{} block, env value, stage close, promoted decl
    assert body[1] == "  agent any" and body[7] == '    BUILD_NO = "${currentBuild.number}"'


def test_repairs_from_errors():
    removes, stubs = repairs_from_errors(
        'Invalid option type "gitLabConnection"\n'
        "No such DSL method 'fooBar' found among steps\n"
        'Expected one of "steps", "stages", or "parallel" for stage "Init"\n'
        "No such property: Artifactory for class: WorkflowScript")
    assert ("options", "gitLabConnection") in removes
    assert ("fill-stage", "Init") in removes
    assert ("stub-property", "Artifactory") in removes
    assert stubs == ["fooBar"]


def test_scoring_is_bounded(declarative):
    text, ast = declarative
    a = analyse(text, ast)
    cand = {"repo": {"pushed_at": "2026-09-01T00:00:00Z", "stargazers_count": 1234, "archived": False},
            "analysis": a, "text": text, "file_last_commit_date": "2025-12-01T00:00:00Z"}
    s = score_candidate(cand, {}, set(), now=datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert 0 <= s["total"] <= 10
    assert abs(sum(p["points"] for p in s["parts"].values()) - s["total"]) < 0.06
    for k, p in s["parts"].items():
        assert 0 <= p["points"] <= MAX[k]
    assert s["summary"].startswith(f"Scored {s['total']}/10")


def test_walkthrough_results_go_to_results_md(tmp_path, monkeypatch):
    from j2gha import config
    from j2gha.readme import update_section

    walk, corpus = tmp_path / "000", tmp_path / "001"
    walk.mkdir()
    corpus.mkdir()
    guide = f"# Walkthrough\n{config.WALKTHROUGH_MARKER}\n"
    (walk / "README.md").write_text(guide)
    update_section(walk / "README.md", "analysis", "### Analysis\n\nfirst")
    update_section(walk / "README.md", "analysis", "### Analysis\n\nsecond")
    assert (walk / "README.md").read_text() == guide
    results = (walk / "RESULTS.md").read_text()
    assert "second" in results and "first" not in results and results.count("j2gha:analysis:start") == 1
    update_section(corpus / "README.md", "analysis", "x")
    assert "j2gha:analysis:start" in (corpus / "README.md").read_text()
    monkeypatch.setattr(config, "EXAMPLES_DIR", tmp_path)
    assert config.list_example_ids() == ["001"]


def test_owner_crawl_discovers_pipeline_files():
    from j2gha.crawl.crawler import _drop_near_duplicates, owner_candidates
    from j2gha.crawl.styles import is_pipeline_path

    assert is_pipeline_path("Jenkinsfile") and is_pipeline_path("ci/Jenkinsfile.release")
    assert is_pipeline_path("jenkinsfiles/jenkinsfile-publish") and is_pipeline_path("jenkinsfile.groovy")
    assert is_pipeline_path("vars/buildApp.groovy") and is_pipeline_path("ops/mobile_build.groovy")
    assert not is_pipeline_path("src/org/acme/Utils.groovy") and not is_pipeline_path("lib/src/main/A.groovy")
    assert not is_pipeline_path("node_modules/x/Jenkinsfile") and not is_pipeline_path("README.md")

    class FakeGitHub:
        def owner_repos(self, owner):
            return [{"full_name": f"{owner}/old", "default_branch": "main", "pushed_at": "2020-01-01T00:00:00Z"},
                    {"full_name": f"{owner}/new", "default_branch": "master", "pushed_at": "2026-01-01T00:00:00Z"},
                    {"full_name": f"{owner}/fork", "default_branch": "main", "fork": True}]

        def tree(self, full_name, ref):
            assert not full_name.endswith("/fork")
            return {"tree": [{"path": "Jenkinsfile", "type": "blob", "sha": f"{full_name}-1"},
                             {"path": "src/a/B.groovy", "type": "blob", "sha": "x"},
                             {"path": "Jenkinsfile", "type": "tree", "sha": "y"}]}

    cands = owner_candidates(FakeGitHub(), ["acme"])
    assert [c["full_name"] for c in sorted(cands.values(), key=lambda c: c["rank"])] == ["acme/new", "acme/old"]
    assert cands["acme/new::Jenkinsfile"]["html_url"] == "https://github.com/acme/new/blob/master/Jenkinsfile"
    assert cands["acme/new::Jenkinsfile"]["found_by"] == ["owner:acme"]

    base = "node { stage('build') { sh 'make SERVICE=results' } }\n" * 4
    kept = _drop_near_duplicates([{"key": "a", "text": base}, {"key": "b", "text": base.replace("results", "journal")},
                                  {"key": "c", "text": "pipeline { agent any; stages { stage('x') { steps { echo 1 } } } }"}],
                                 [])
    assert [c["key"] for c in kept] == ["a", "c"]


def test_localize_repairs_stub_values(library_classes):
    text, ast = library_classes
    console = "\n".join([
        "[2026-10-03T15:02:52.487Z] hudson.remoting.ProxyException: org.codehaus.groovy.runtime.typehandling."
        "GroovyCastException: Cannot cast object 'j2gha-stub' with class 'J2ghaAny' to class 'java.util.Map'",
        "[2026-10-03T15:02:52.487Z] \tat org.codehaus.groovy.runtime.ScriptBytecodeAdapter.castToType(x.java:616)",
        "[2026-10-03T15:02:52.487Z] \tat WorkflowScript.run(WorkflowScript:7)",
        "[2026-10-03T15:04:35.461Z] java.lang.ClassCastException: org.jenkinsci.plugins.workflow.support.steps."
        "PushdStep.path expects class java.lang.String but received class J2ghaAny",
        "[2026-10-03T15:04:35.461Z] \tat WorkflowScript.run(WorkflowScript:14)",
    ])
    removes, _ = repairs_from_errors(console)
    assert removes == [("stringify-args", 14), ("untype-decl", 7)]
    loc = localize(text, ast, analyse(text, ast), "trace", remove=removes)
    body = loc.script.split("// ---- j2gha localisation block")[0].splitlines()
    assert body[6] == "def repos = settings.repos()"
    assert body[7] == "def targets = settings.targets()"  # typed from the same stubbed object
    assert body[13].strip() == 'dir("${Settings.WORKDIR}") {'
    assert body[18].strip() == 'dir("${Settings.WORKDIR}") { sh \'make test\' }'  # same step and argument
    assert len(body) - 1 == len(text.splitlines())  # line numbers unchanged
    # a real type mismatch (qualified class) is the pipeline's own bug, not a stub to repair
    assert repairs_from_errors(console.replace("class J2ghaAny", "class java.lang.Integer")
                               .replace("with class 'J2ghaAny'", "with class 'java.lang.Integer'")) == ([], [])


def test_localize_stubs_sibling_job_parameters(library_classes):
    text, ast = library_classes
    loc = localize(text, ast, analyse(text, ast), "trace", remove=[("stub-property", "APP_BRANCH")])
    assert "@groovy.transform.Field def APP_BRANCH = new J2ghaAny()" in loc.script
    assert "@groovy.transform.Field def TARGET_ENV = new J2ghaAny()" in loc.script  # same literal, not defined
    assert "def BUILD_NUMBER" not in loc.script  # Jenkins' own environment variable
    assert "def REGION" not in loc.script  # set through env. before use


def test_library_template_directives_are_not_steps(library_template):
    # pipeline {} inside def call() is the Declarative root, not script code calling unknown steps
    text, ast = library_template
    a = analyse(text, ast)
    assert a["dialect"] == "library-template"
    assert [u["name"] for u in a["unknown_steps"]] == ["deployApp"]
    loc = localize(text, ast, a, "trace")
    block = loc.script.split("j2gha localisation block")[1]
    assert "def deployApp(" in block
    assert not any(f"def {d}(" in block for d in ("pipeline", "agent", "stages", "steps", "post", "always"))
    assert loc.script.rstrip().endswith("end of j2gha localisation block ----")
    assert "call(new J2ghaConfig())" in loc.script


def test_library_template_trace_localisation(library_template):
    from j2gha.analysis.declarative import build_ir
    from j2gha.jenkins.run import param_defaults

    text, ast = library_template
    a = analyse(text, ast)
    # Declarative builds parameters/options when pipeline {} runs, so Jenkins reports the pipeline line (5)
    console = ("java.lang.ClassCastException: class hudson.model.StringParameterDefinition.setDefaultValue() expects "
               "class java.lang.String but received class J2ghaAny\n\tat WorkflowScript.call(WorkflowScript:5)\n")
    removes, _ = repairs_from_errors(console)
    assert removes == [("stringify-args", 5)]
    loc = localize(text, ast, a, "trace", remove=removes)
    body, block = loc.script.split("j2gha localisation block")[:2]
    assert "string(name: 'BRANCH', defaultValue: \"${settings.branch}\")" in body
    assert "/* j2gha: lock removed */" in body and "timestamps()" in body
    assert "lock('db') {" in body and "def lock(Object... a)" in block  # step-level lock runs its body only
    assert "boolean isEmpty() { false }" in block and "class J2ghaConfig" in block
    # literal defaults and first choices are sent; settings.branch is left for Jenkins to evaluate
    assert param_defaults(build_ir(ast).parameters) == {"DEPLOY": "false", "REGION": "eu"}


def test_full_mode_removes_options_that_crash_the_job_and_stubs_wrappers(library_template):
    # full mode: buildDiscarder/lock options are removed (a stub-valued or stringified logRotator crashed examples
    # 003 and 005 before any stage), and podTemplate/wrap bodies run on the built-in node as in trace mode
    text, ast = library_template
    a = analyse(text, ast)
    loc = localize(text, ast, a, "full")
    body, block = loc.script.split("j2gha localisation block")[:2]
    assert "/* j2gha: lock removed */" in body
    assert "buildDiscarder(" not in body or "/* j2gha: buildDiscarder removed */" in body
    for w in ("podTemplate", "wrap", "withDockerContainer"):
        assert f"def {w}(Object... a)" in block, w


def test_compare_inconclusive_when_jenkins_stops_on_own_error():
    def ev(*pairs):
        return [{"stage": s, "step": st} for s, st in pairs]

    ref = ev(("Init", "checkout"), ("Build", "sh"), ("Deploy", "sh"), ("Deploy", "error"),
             ("Declarative: Post Actions", "echo"))
    cand = ev(("Init", "checkout"), ("Build", "sh"), ("Deploy", "sh"), ("Deploy", "sh"), ("Publish", "sh"),
              ("Declarative: Post Actions", "echo"))
    c = compare(ref, cand, reference_result="FAILURE")
    assert c["verdict"] == "inconclusive" and not c["equivalent"]
    assert c["inconclusive"]["stage"] == "Deploy"
    assert c["inconclusive"]["stages_before"] == ["Init", "Build"] and c["inconclusive"]["stages_before_equivalent"]
    # the candidate failed the same way, or Jenkins did not fail: a real difference
    same_error = ev(("Init", "checkout"), ("Build", "sh"), ("Deploy", "error"))
    assert compare(ref, same_error, reference_result="FAILURE")["verdict"] == "differs"
    assert compare(ref, cand, reference_result="SUCCESS")["verdict"] == "differs"
    assert compare(ref, ref, reference_result="FAILURE")["verdict"] == "equivalent"


def test_localize_runs_blocks_passed_to_stub_objects(library_classes):
    # settings = new Settings() (stubbed class): settings.inStage('Deploy') { sh } must still run its block
    text, ast = library_classes
    loc = localize(text, ast, analyse(text, ast), "trace")
    body, block = loc.script.split("j2gha localisation block")[:2]
    assert "j2ghaBody('Deploy') {" in body and "def j2ghaBody(Object... a)" in block
    assert "tools.log('building')" in body  # no block: left to the stub
    line = next(i for i, x in enumerate(text.splitlines()) if "inStage" in x)
    assert loc.script.splitlines()[line] == "j2ghaBody('Deploy') {"  # same line as the original call


def test_convert_refreshes_stale_analysis_and_cleans_report_only(tmp_path, monkeypatch, declarative):
    """convert never reuses an AST/analysis of another Jenkinsfile version, and a pipeline that becomes
    report-only loses its earlier generated workflow (no later stage can run stale output)."""
    import json as _json

    from j2gha import stages
    from j2gha.provenance import sha256_text

    text, ast = declarative
    d = tmp_path / "901"
    (d / "analysis").mkdir(parents=True)
    (d / "gha").mkdir()
    (d / "Jenkinsfile").write_text(text)
    (d / "README.md").write_text("# 901\n")
    (d / "analysis" / "groovy-ast.json").write_text(_json.dumps({**ast, "source_sha256": "old"}))
    analysed = []

    def fake_analyze(ids, use_jenkins=True):
        analysed.append(ids)
        a = {"source_sha256": sha256_text(text), "convertibility": "report-only", "dialect": "library-call"}
        (d / "analysis" / "analysis.json").write_text(_json.dumps(a))
    monkeypatch.setattr(stages, "analyze_examples", fake_analyze)
    monkeypatch.setattr(stages, "example_dir", lambda i: d)
    dumped = []
    monkeypatch.setattr("j2gha.analysis.ast.dump_source", lambda t: dumped.append(t) or dict(ast))
    for f in stages.GHA_OUTPUTS:
        (d / "gha" / f).write_text("{}")
    import j2gha.convert.generator as gen
    monkeypatch.setattr(gen, "github_resolver", lambda: (lambda repo, ref: None))
    stages.convert_examples(["901"])
    assert analysed == [["901"]]  # analysis.json missing -> re-analysed
    assert dumped == [text]  # the saved AST was parsed from another text -> re-parsed
    assert not any((d / "gha" / f).exists() for f in stages.GHA_OUTPUTS)


def test_provisioning_fakes_aws_credentials_for_map_form_bindings():
    from j2gha.jenkins.localize import FAKE_PASSWORD, FAKE_USER, provisioning_script

    script = provisioning_script([{"id": "jenkins-iam", "type": "aws", "lines": [19]}], [], "")
    assert "AWSCredentialsImpl(CredentialsScope.GLOBAL, \"jenkins-iam\"" in script
    assert FAKE_USER in script and FAKE_PASSWORD in script


def test_full_mode_without_docker_stubs_the_docker_global_but_runs_its_blocks():
    # docker.image(x).inside {} runs real `docker inspect`/`docker pull` sh steps before its wrapper (108): without
    # --docker the global is a stub whose blocks still run; with --docker it is left alone
    from conftest import load

    text, ast = load("scripted-wrappers")
    a = analyse(text, ast)
    loc = localize(text, ast, a, "full")
    assert "@groovy.transform.Field def docker = new J2ghaAny()" in loc.script
    assert any("docker.image('node:20').inside(...) {} on a stub runs its block" in c for c in loc.changes)
    assert "j2ghaBody {" in loc.script or "j2ghaBody(" in loc.script
    kept = localize(text, ast, a, "full", docker=True)
    assert "@groovy.transform.Field def docker" not in kept.script

