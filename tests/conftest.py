import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> tuple[str, dict]:
    text = (FIXTURES / f"Jenkinsfile.{name}").read_text()
    ast = json.loads((FIXTURES / f"{name}.ast.json").read_text())
    return text, ast


@pytest.fixture
def declarative():
    return load("declarative")


@pytest.fixture
def scripted():
    return load("scripted")


@pytest.fixture
def library_options():
    return load("library-options")


@pytest.fixture
def script_vars():
    return load("script-vars")


@pytest.fixture
def library_classes():
    return load("library-classes")


@pytest.fixture
def library_template():
    return load("library-template")


@pytest.fixture
def script_dispatch():
    return load("script-dispatch")


@pytest.fixture
def semantics():
    return load("semantics")
