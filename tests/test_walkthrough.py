"""Example 000 (the walkthrough) as an acceptance test: three parameter scenarios, trace and full mode, Jenkins vs act.
Full mode compares the archived files and test results too (j2gha.outputs).

End to end (disposable Jenkins controller + act, a few minutes), so it only runs on request:
``uv run --group dev pytest -m e2e tests/test_walkthrough.py``. Needs the harness images (`j2gha docker build`).
The scenario switches are the pipeline's own parameters: ``DEPLOY_ENV=none`` skips the deployment and a
``-SNAPSHOT`` ``RELEASE_VERSION`` skips publishing.
"""

import json

import pytest

from j2gha import config
from j2gha.analysis.ast import docker_image_exists
from j2gha.runners import execute
from j2gha.stages import analyze_examples, convert_examples

pytestmark = pytest.mark.e2e

SCENARIOS = {
    "release": {},
    "snapshot-no-deploy": {"RELEASE_VERSION": "1.4.0-SNAPSHOT", "DEPLOY_ENV": "none"},
    "no-integration-tests": {"RUN_INTEGRATION_TESTS": "false"},
}
# stages the Jenkins side must (not) run per scenario: the scenario really took another branch of the pipeline
EXPECT_STAGES = {
    "release": {"Integration tests", "Publish", "Deploy"},
    "snapshot-no-deploy": {"Integration tests"},
    "no-integration-tests": {"Publish", "Deploy"},
}
ALL_BRANCH_STAGES = {"Integration tests", "Publish", "Deploy"}
# full mode: what Jenkins archives and how many test cases it records per scenario (unit 5, integration 1, 3 matrix
# cells x 5), which the converted run must reproduce
RELEASE_FILES = {"build/lint/reports/lint.txt", "dist/inventory-service-1.4.0.tar.gz",
                 "dist/inventory-service-1.4.0.tar.gz.sha256", "dist/BUILD_INFO.txt", "deploy/staging.json"}
EXPECT_OUTPUTS = {
    "release": (RELEASE_FILES, 21),
    "snapshot-no-deploy": ({"build/lint/reports/lint.txt"}, 21),
    "no-integration-tests": (RELEASE_FILES, 20),
}


@pytest.fixture(scope="module")
def example():
    for image in (config.JENKINS_IMAGE, config.ACT_IMAGE):
        if not docker_image_exists(image):
            pytest.skip(f"{image} not built (`uv run j2gha docker build`)")
    d = config.EXAMPLES_DIR / "000"
    analyze_examples(["000"])
    convert_examples(["000"])
    return d


@pytest.mark.parametrize("mode", ["trace", "full"])
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_walkthrough_scenarios_are_equivalent_on_act(example, scenario, mode):
    res = execute.run_example(example, ["jenkins", "act"], mode=mode, params=SCENARIOS[scenario] or None)
    assert res["statuses"] == {"jenkins": "ran", "act": "ran"}
    assert res["verdicts"] == {"act": "equivalent"}, res["records"]["act"]["comparison"]
    jenkins, act = res["records"]["jenkins"], res["records"]["act"]
    # two runs that fail alike would also be "equivalent": both must have succeeded
    assert jenkins["result"] == "SUCCESS" and act["result"] == "success", (jenkins["result"], act["result"])
    if mode == "trace":
        stages = {t["stage"] for t in jenkins.get("traces", [])}
        assert stages & ALL_BRANCH_STAGES == EXPECT_STAGES[scenario], stages
    else:  # the outputs were compared, not just the outcome
        files, cases = EXPECT_OUTPUTS[scenario]
        assert {f["path"] for f in jenkins["outputs"]["archived"]} == files
        assert len(jenkins["outputs"]["tests"]) == cases
        outputs = act["comparison"]["outputs"]
        assert outputs["verdict"] == "same" and outputs["tests"]["status"] == "same", outputs
        assert outputs["archived"]["status"] == "same", outputs
    recorded = json.loads((example / "runs" / f"jenkins-{mode}" / "result.json").read_text())["scenario"]
    assert recorded.get("params") == (SCENARIOS[scenario] or None)
    assert len([a for a in jenkins["attempts"] if a.get("phase") == "register"]) == 0, "no extra default build"


def test_a_sabotaged_conversion_is_caught_and_not_counted(example):
    """Part 8 of the walkthrough: Deploy runs only when DEPLOY_ENV *is* none."""
    model = example / "gha" / "workflow.model.json"
    original = model.read_text()
    try:
        model.write_text(original.replace("env.DEPLOY_ENV != 'none'", "env.DEPLOY_ENV == 'none'"))
        assert model.read_text() != original
        refused = execute.run_example(example, ["act"], mode="trace")
        assert refused["statuses"] == {"act": "infra"}, "an edited model is refused unless asked for"
        res = execute.run_example(example, ["jenkins", "act"], mode="trace", allow_edited_model=True)
        comparison = res["records"]["act"]["comparison"]
        assert res["records"]["act"]["result"] == "success"  # it still goes green...
        assert comparison["verdict"] == "differs"  # ...and the comparison catches it
        assert any(r["stage"] == "Deploy" and r["status"] == "missing-stage" for r in comparison["stages"])
        assert execute.stale_reason(example, res["records"]["act"], "act") is not None
    finally:
        model.write_text(original)
        execute.run_example(example, ["act"], mode="trace")  # leave a real, clean record behind


def test_a_dropped_test_report_is_caught_in_full_mode(example):
    """The outcome alone cannot catch a conversion that stops uploading a test report: both runs still succeed."""
    model = example / "gha" / "workflow.model.json"
    original = model.read_text()
    try:
        m = json.loads(original)
        steps = m["jobs"]["quality-unit-tests"]["steps"]
        m["jobs"]["quality-unit-tests"]["steps"] = [s for s in steps if s["_j2gha"].get("kind") != "junit-upload"]
        assert len(m["jobs"]["quality-unit-tests"]["steps"]) == len(steps) - 1
        model.write_text(json.dumps(m, indent=2) + "\n")
        res = execute.run_example(example, ["jenkins", "act"], mode="full", allow_edited_model=True)
        jenkins, act = res["records"]["jenkins"], res["records"]["act"]
        assert jenkins["result"] == "SUCCESS" and act["result"] == "success"  # both green...
        comparison = act["comparison"]
        assert comparison["verdict"] == "differs", comparison  # ...but the tests differ
        assert comparison["outputs"]["tests"]["status"] == "differs"
        assert comparison["outputs"]["tests"]["gha"]["cases"] == 16  # the 5 unit tests are gone
    finally:
        model.write_text(original)
        execute.run_example(example, ["act"], mode="full")  # leave a real, clean record behind
