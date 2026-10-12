import json

from j2gha import config, stages


def test_summary_marks_twins(monkeypatch, tmp_path):
    for i, src in (("001", {}), ("101", {"derived_from": {"example": "001", "note": "see LOCAL.md"}})):
        (tmp_path / i).mkdir()
        (tmp_path / i / "source.json").write_text(json.dumps({"repository": {"full_name": "o/r"}, **src}))
    monkeypatch.setattr(config, "EXAMPLES_DIR", tmp_path)
    monkeypatch.setattr(config, "list_example_ids", lambda: ["001", "101"])
    rows = {line.split(" |")[0]: line for line in stages.summarize_examples().read_text().splitlines()
            if line.startswith("| [")}
    assert rows["| [101](101/README.md)<br>twin of [001](001/README.md)"]
    assert "| [001](001/README.md)" in rows
