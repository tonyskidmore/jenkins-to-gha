"""Phase 4 acceptance end to end: the workspace hand-off (P4.3) and archived-file identity (P4.1), Jenkins vs act.

990 - the hand-off. Later stages read files that are never stashed. Jenkins runs the pipeline in one workspace; the
converted workflow only succeeds, with the same test results and archived files, if the hand-off
* merges a parallel *first* stage onto the checkout (one branch edits a checked-out file, the other leaves it alone),
* merges a parallel stage that follows another onto the merged workspace its branches started from (one branch
  changes a file an earlier branch made, the other leaves it alone),
* replays a later branch's directory removal and mode changes, and
* hands the final workspace to the post job (its JUnit report).
Converted without the hand-off, the same pipeline must differ (negative control).

991 - archived-file identity. Matrix cells archive `<cell>/app.txt`; the converted cells upload the same file name
in separate artifacts. Same outputs when converted correctly; when both cells archive one cell's file (a mutated
model), the copy must not stand in for the other cell's file. Both cells also report a JUnit case of the same name:
Jenkins keeps one per cell, as the converted cells' two reports do.

Each test is independent: module fixtures build the example and record its Jenkins reference once. Needs the harness
images and network access (990 checks out github.com/octocat/Hello-World). A few minutes:
``uv run --group dev pytest -m e2e tests/test_handoff_e2e.py``. The converted side runs under act; with
``J2GHA_E2E_TIERS=act,selfhosted`` every test also runs on real GitHub Actions through the harness's local JIT
runners (0 billable minutes; needs `gh` auth for the harness repository).
"""

import json
import os

import pytest

from j2gha import config, stages
from j2gha.analysis.ast import docker_image_exists
from j2gha.runners import execute

pytestmark = pytest.mark.e2e

HANDOFF = """pipeline {
    agent any
    stages {
        stage('Prepare') {
            parallel {
                stage('Edit') {
                    steps {
                        sh '''
                            grep -q 'Hello World' README
                            echo edited >> README
                            mkdir -p gen old keep
                            echo one > gen/data.txt
                            echo obsolete > old/file.txt
                            echo 'echo tool' > tool.sh
                        '''
                    }
                }
                stage('Reports') {
                    steps {
                        sh '''
                            mkdir -p reports
                            echo '<testsuite name="t"><testcase classname="unit.App" name="test_built"/></testsuite>' > reports/junit.xml
                        '''
                    }
                }
            }
        }
        stage('Refine') {
            parallel {
                stage('Change') {
                    steps {
                        sh '''
                            grep -q edited README
                            echo two > gen/data.txt
                        '''
                    }
                }
                stage('Tidy') {
                    steps {
                        sh '''
                            grep -q edited README
                            test -f reports/junit.xml
                            rm -r old
                            chmod 700 keep
                            chmod +x tool.sh
                            echo extra > extra.txt
                        '''
                    }
                }
            }
        }
        stage('Package') {
            steps {
                sh '''
                    grep -q edited README
                    grep -qx two gen/data.txt
                    test ! -e old
                    test "$(stat -c %a keep)" = 700
                    test -x tool.sh
                    test -f extra.txt
                    tar -czf package.tgz README gen extra.txt
                '''
                archiveArtifacts artifacts: 'package.tgz, gen/data.txt'
            }
        }
    }
    post {
        always {
            junit 'reports/junit.xml'
        }
    }
}
"""

MATRIX = """pipeline {
    agent any
    options { skipDefaultCheckout() }
    stages {
        stage('Build') {
            matrix {
                axes {
                    axis {
                        name 'FLAVOUR'
                        values 'alpha', 'beta'
                    }
                }
                stages {
                    stage('Package') {
                        steps {
                            sh 'mkdir -p "$FLAVOUR" && echo "$FLAVOUR" > "$FLAVOUR/app.txt"'
                            archiveArtifacts artifacts: "${env.FLAVOUR}/app.txt"
                            sh '''
                                mkdir -p reports
                                echo '<testsuite name="t"><testcase classname="unit.App" name="test_same"/></testsuite>' > reports/junit.xml
                            '''
                            junit 'reports/junit.xml'
                        }
                    }
                }
            }
        }
    }
}
"""

# octocat/Hello-World at its only commit: a public repository GitHub keeps for exactly this
SOURCE = {"repository": {"full_name": "octocat/Hello-World", "default_branch": "master"},
          "file_last_commit_sha": "7fd1a60b01f91b314f59955a4e4d4e80d8edf11d"}

EXAMPLES: dict[str, object] = {}
TIERS = os.environ.get("J2GHA_E2E_TIERS", "act").split(",")
tiers = pytest.mark.parametrize("tier", TIERS)


@pytest.fixture(scope="module", autouse=True)
def example_dirs():
    for image in (config.JENKINS_IMAGE, config.ACT_IMAGE):
        if not docker_image_exists(image):
            pytest.skip(f"{image} not built (`uv run j2gha docker build`)")
    mp = pytest.MonkeyPatch()
    mp.setattr(stages, "example_dir", lambda i: EXAMPLES[i])
    yield
    mp.undo()


def make(tmp_path_factory, eid, jenkinsfile, source=None):
    """An example directory, analysed, with its Jenkins full-mode reference."""
    d = tmp_path_factory.mktemp(eid) / eid
    d.mkdir()
    (d / "Jenkinsfile").write_text(jenkinsfile)
    (d / "README.md").write_text(f"# Acceptance pipeline {eid}\n")
    if source:
        (d / "source.json").write_text(json.dumps({"id": eid, **source}))
    EXAMPLES[eid] = d
    stages.analyze_examples([eid])
    ref = execute.run_example(d, ["jenkins"], mode="full")["records"]["jenkins"]
    assert ref["result"] == "SUCCESS", ref.get("error_tail")
    return d, ref


@pytest.fixture(scope="module")
def handoff(tmp_path_factory):
    return make(tmp_path_factory, "990", HANDOFF, SOURCE)


@pytest.fixture(scope="module")
def matrix(tmp_path_factory):
    return make(tmp_path_factory, "991", MATRIX)


def gha_run(d, monkeypatch, tier, handoff_on=True, edited=False):
    if handoff_on:
        monkeypatch.delenv("J2GHA_WORKSPACE_HANDOFF", raising=False)
    else:
        monkeypatch.setenv("J2GHA_WORKSPACE_HANDOFF", "0")
    return execute.run_example(d, [tier], mode="full", allow_edited_model=edited)["records"][tier]


# ------------------------------------------------------------------------------------------------ 990: hand-off
@tiers
def test_unstashed_files_reach_later_jobs_through_the_handoff(handoff, monkeypatch, tier):
    d, ref = handoff
    stages.convert_examples(["990"])
    act = gha_run(d, monkeypatch, tier)
    assert act["result"] == "success", act.get("failed_steps")
    comparison = act["comparison"]
    assert comparison["verdict"] == "equivalent", comparison
    outputs = comparison["outputs"]
    assert outputs["tests"]["status"] == "same" and outputs["tests"]["jenkins"]["cases"] == 1
    assert outputs["archived"]["status"] == "same" and outputs["archived"]["jenkins"] == 2
    assert outputs["archived"]["copies"] == 0


@tiers
def test_without_the_handoff_the_same_pipeline_differs(handoff, monkeypatch, tier):
    d, ref = handoff
    monkeypatch.setenv("J2GHA_WORKSPACE_HANDOFF", "0")
    stages.convert_examples(["990"])  # a real conversion (not an edited model), only without the hand-off
    act = gha_run(d, monkeypatch, tier, handoff_on=False)
    assert act["result"] == "failure" and act["comparison"]["verdict"] == "differs", act["comparison"]


# -------------------------------------------------------------------------------------- 991: archived identity
@tiers
def test_matrix_cells_archive_their_own_files(matrix, monkeypatch, tier):
    d, ref = matrix
    assert sorted(f["path"] for f in ref["outputs"]["archived"]) == ["alpha/app.txt", "beta/app.txt"]
    stages.convert_examples(["991"])
    act = gha_run(d, monkeypatch, tier)
    archived = act["comparison"]["outputs"]["archived"]
    assert act["comparison"]["verdict"] == "equivalent", act["comparison"]
    assert archived["status"] == "same" and archived["copies"] == 0 and archived["content_same"] == 2
    tests = act["comparison"]["outputs"]["tests"]
    assert tests["status"] == "same" and tests["jenkins"]["cases"] == 2  # one per cell on both sides


@tiers
def test_a_copy_of_one_cells_file_does_not_stand_in_for_another_cells(matrix, monkeypatch, tier):
    """Follow-up finding 1 end to end: both converted cells build and archive alpha/app.txt. Same result, same
    traces - only the archived files tell, and they must: beta/app.txt is missing, the second alpha copy is a copy."""
    d, ref = matrix
    stages.convert_examples(["991"])
    path = d / "gha" / "workflow.model.json"
    model = json.loads(path.read_text())
    (job,) = model["jobs"].values()
    job["env"]["FLAVOUR"] = "alpha"  # every cell now builds alpha (the matrix still runs two cells)
    for st in job["steps"]:
        if (st.get("_j2gha") or {}).get("kind") == "archiveArtifacts":
            st["with"]["path"] = st["with"]["path"].replace("${{ matrix.FLAVOUR }}", "alpha")
    path.write_text(json.dumps(model, indent=2))
    act = gha_run(d, monkeypatch, tier, edited=True)
    assert act["result"] == "success", act.get("failed_steps")
    archived = act["comparison"]["outputs"]["archived"]
    assert act["comparison"]["verdict"] == "differs", act["comparison"]
    assert archived["missing"] == ["beta/app.txt"] and archived["copies"] == 1 and archived["extra"] == []
