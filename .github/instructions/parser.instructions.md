---
description: "Parsing Jenkinsfiles, the IR, the step catalog and the analysis (findings, coverage, difficulty score)"
applyTo: "j2gha/analysis/**,j2gha/ir.py,j2gha/rules/steps.yaml,docker/jenkins/groovy/**"
paths:
  - "j2gha/analysis/**"
  - "j2gha/ir.py"
  - "j2gha/rules/steps.yaml"
  - "docker/jenkins/groovy/**"
---
# Parse, IR and assess

- **Parse** (`j2gha/analysis/ast.py`, `docker/jenkins/groovy/ast_dump.groovy`)
  - Uses the Groovy 2.4.21 CONVERSION-phase AST from the jar inside `jenkins.war`, so parsing matches Jenkins.
  - `dump_sources()` mounts the repository's dumper over the image's copy, so dumper edits need no image rebuild.
- **IR** (`j2gha/ir.py`, `j2gha/analysis/declarative.py`)
  - Declarative is interpreted directive by directive; scripted gets a best-effort model.
  - Elements keep their `line`.
  - Helper methods are kept in `Pipeline.method_defs` for inlining.
- **Assess** (`j2gha/analysis/analyze.py`, `j2gha/rules/steps.yaml`)
  - Produces findings, hard gates, weighted coverage and the 0-100 difficulty score.
  - An unknown step counts once beyond coverage: in library opacity when a library is loaded, else in plugin coupling.
    `SharedLibrary` is a finding, not a gate. With unknown steps, `complexity.if_unknown_mapped` gives the score as if
    they were mapped.
  - Bump `ANALYSIS_VERSION` when the meaning of the analysis output changes, then regenerate the corpus offline
    (see the corpus rules). `scoreboard --check` compares coverage, not difficulty: keep coverage stable unless that
    is the point of the change.
  - Jenkins' `/pipeline-model-converter/toJson` is only a validity cross-check: it has no line numbers, drops
    `@Library` and truncates one-line `script{}` blocks.
- **Groovy 2.4 quirks**
  - GString end columns run to end of line; `ast._cut_gstring` fixes this.
  - `a + b` string concatenation becomes `{"t":"concat"}`.
  - `stage('a'){..} stage('b'){..}` on one line is a command chain (`ast.unchain`).
  - Calls inside another call's *arguments* are DSL symbols, not steps (`CallCtx.in_args`).
- **After changing the dumper**, regenerate the AST fixtures (see the tests rules).

Reference: [docs/architecture.md](../../docs/architecture.md), [docs/scoring.md](../../docs/scoring.md),
[docs/extending.md](../../docs/extending.md).
