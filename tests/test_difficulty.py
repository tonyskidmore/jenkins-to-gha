"""The difficulty score: an unknown step counts once beyond coverage, an opaque library is not a hard gate, and the
score is also given as if every unknown step were mapped."""

from j2gha.analysis.analyze import analyse, band, complexity, convertibility, coverage
from j2gha.render import difficulty_section
from j2gha.stages import difficulty_breakdown


def _case(unknown: int, libraries: list[str], findings: list[dict] | None = None) -> tuple[dict, dict]:
    steps = {"sh": {"category": "direct", "count": 6, "lines": [1]}}
    steps.update({f"libStep{i}": {"category": "unknown", "count": 1, "lines": [i]} for i in range(unknown)})
    inv = {"metrics": {"unknown_steps": unknown}, "steps": steps, "agents": []}
    result = {"dialect": "declarative", "libraries": libraries, "findings": findings or [],
              "unknown_steps": [{"name": n} for n, e in steps.items() if e["category"] == "unknown"]}
    result["coverage"] = coverage(inv)
    return result, inv


def test_an_unknown_step_counts_once_beyond_coverage():
    with_lib = complexity(*_case(2, ["corp-lib"]))["dimensions"]
    assert with_lib["plugin_coupling"] == 0 and with_lib["library_opacity"] == 9 + 2 * 2  # a library step, probably
    without = complexity(*_case(2, []))["dimensions"]
    assert without["plugin_coupling"] == 3 * 2 and without["library_opacity"] == 0  # a plugin step, probably
    assert complexity(*_case(3, []))["dimensions"]["library_opacity"] == 4  # perhaps an implicit global library
    assert with_lib["step_mapping"] == without["step_mapping"] > 0  # coverage counts them as before


def test_the_score_if_every_unknown_step_were_mapped():
    cx = complexity(*_case(4, ["corp-lib"]))
    assert cx["unknown_steps"] == ["libStep0", "libStep1", "libStep2", "libStep3"]
    mapped = cx["if_unknown_mapped"]
    assert mapped["score"] < cx["score"] and mapped["classification"] == band(mapped["score"])
    assert "if_unknown_mapped" not in complexity(*_case(0, ["corp-lib"]))
    gated = complexity(*_case(4, ["corp-lib"], [{"id": "DynamicParallel", "gate": True}]))
    assert gated["score"] >= 46 and gated["if_unknown_mapped"]["score"] >= 46  # a real gate still holds


def test_unknown_steps_make_convertibility_partial():
    result, inv = _case(1, [])
    result["complexity"] = complexity(result, inv)
    assert result["complexity"]["score"] <= 45 and not result["complexity"]["hard_gates"]
    assert convertibility(result) == "partial"
    result, inv = _case(0, [])
    result["complexity"] = complexity(result, inv)
    assert convertibility(result) == "automatic"


def test_shared_library_is_a_finding_not_a_gate(scripted):
    text, ast = scripted
    a = analyse(text, ast)
    shared = next(f for f in a["findings"] if f["id"] == "SharedLibrary")
    assert shared["severity"] == "high" and not shared.get("gate")
    assert "SharedLibrary" not in a["complexity"]["hard_gates"]
    assert {"DynamicParallel", "ExternalGroovyLoad"} <= set(a["complexity"]["hard_gates"])


def test_bands():
    assert [band(s) for s in (0, 20, 21, 45, 46, 70, 71, 100)] == [
        "straightforward", "straightforward", "assisted", "assisted", "significant-redesign", "significant-redesign",
        "rebuild-around-intent", "rebuild-around-intent"]


def test_the_breakdown_names_dimensions_gates_and_unknown_steps():
    cx = complexity(*_case(6, ["corp-lib"]))
    dims, unknown = difficulty_breakdown(cx)
    assert dims.startswith("structure 0, mapping ") and dims.endswith("hard gates: none")
    assert unknown.startswith("6 unknown step(s) (libStep0, libStep1, libStep2, libStep3, libStep4, ... (+1)): ")
    assert unknown.endswith("if they were mapped")
    section = "\n".join(difficulty_section(cx))
    assert "## Difficulty breakdown" in section and "| library opacity | 15 | 15 |" in section
    assert f"the difficulty would be **{cx['if_unknown_mapped']['score']}/100" in section
    assert len(difficulty_breakdown(complexity(*_case(0, [])))) == 1  # no unknown steps: no second line
