from j2gha.analysis.analyze import analyse
from j2gha.analysis.declarative import build_ir


def test_declarative_ir_structure(declarative):
    _, ast = declarative
    ir = build_ir(ast)
    assert ir.dialect == "declarative"
    assert [s.name for s in ir.stages] == ["Build", "Test", "Matrix", "Deploy"]
    test = ir.stages[1]
    assert [b.name for b in test.parallel] == ["Unit", "Integration"]
    assert test.parallel[1].agent.kind == "docker" and test.parallel[1].agent.image == "node:20"
    matrix = ir.stages[2].matrix
    assert matrix.axes == {"OS": ["linux", "windows"], "JDK": ["17", "21"]}
    assert matrix.excludes == [{"OS": {"values": ["windows"]}, "JDK": {"notValues": ["21"]}}]
    assert ir.environment["REGISTRY_CREDS"].kind == "credentials"
    assert ir.environment["SHORT_SHA"].kind == "shell"
    assert ir.options["timeout"]["minutes"] == 30
    assert [p.name for p in ir.parameters] == ["DEPLOY", "TARGET"]
    assert "helper" in ir.method_defs
    deploy_when = ir.stages[3].when.conditions[0]
    assert deploy_when.kind == "allOf" and [c.kind for c in deploy_when.children] == ["branch", "expression"]


def test_declarative_analysis(declarative):
    text, ast = declarative
    a = analyse(text, ast)
    assert a["dialect"] == "declarative"
    for style in ("declarative", "parallel", "matrix", "docker-agent", "credentials", "parameters-triggers",
                  "artifacts-tests", "when-post"):
        assert style in a["styles"], style
    assert a["metrics"]["matrix_cells"] == 4
    assert a["metrics"]["parallel_branches"] == 2
    assert {c["id"] for c in a["credentials"]} >= {"registry", "deployer"}
    assert 0 <= a["complexity"]["score"] <= 100
    assert a["convertibility"] in ("automatic", "partial")
    # mail(to:) is a step, and symbols in arguments are not counted as steps
    assert "mail" in a["steps"]


def test_scripted_hard_gates(scripted):
    text, ast = scripted
    a = analyse(text, ast)
    assert a["dialect"] == "scripted"
    ids = {f["id"] for f in a["findings"]}
    assert {"DynamicParallel", "ExternalGroovyLoad", "SharedLibrary"} <= ids
    assert a["complexity"]["score"] >= 46
    assert a["complexity"]["classification"] in ("significant-redesign", "rebuild-around-intent")
    assert a["libraries"] == ["platform-lib@v2"]


def test_catalog_docker_global_is_not_every_step_named_docker_something():
    # the docker-workflow global is looked up by its qualified form; a shared-library step whose name merely starts
    # with "docker" is unknown (021's dockerLogin was reported as the docker.script policy step and, unlike on
    # Jenkins where the runtime stub traces it, not traced on the converted side)
    from j2gha.analysis import catalog

    assert catalog.categorise("docker.image") == "policy" and catalog.categorise("docker.foo.inside") == "policy"
    assert catalog.lookup("docker.withRegistry")["gha"] == "docker/login-action"
    assert catalog.categorise("docker") == catalog.categorise("docker.script")
    assert catalog.categorise("dockerLogin") == "unknown" and catalog.categorise("dockerLoginH2OECR") == "unknown"
    assert catalog.categorise("dockerNode") == "policy"  # its own catalog entry
