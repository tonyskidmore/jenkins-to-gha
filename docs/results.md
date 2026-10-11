# Results on the corpus (2026-10-07)

A snapshot of 20 real-world examples (`001`-`020`) spanning all 17 styles, plus the hand-written
[walkthrough](../examples/000/README.md). The corpus has grown since (16 twins added), so the live table in
[examples/README.md](../examples/README.md) covers more; to repeat this set, run `uv run j2gha pipeline 1-20`.

| Stage | Outcome |
|---|---|
| Analysis | 20/20 parsed with Jenkins' Groovy. Declarative ones were validated against Jenkins 2.580.1. Difficulty ranges from 5 to 67. |
| Conversion | 20/20 converted, at 12-87% estimated automation (report items weighted by status: an effort estimate, not a measure of correctness). Every manual item has a source line. |
| Static validation | 20/20 pass actionlint structurally and the j2gha policy, with every scanner run (a scanner that cannot run fails validation). Shellcheck findings in the *original* scripts are reported as SAST. zizmor is clean for 18/20 after SHA-pinning and `persist-credentials: false`; 001 keeps High `unpinned-images` findings inherited from tag-only Jenkins docker-agent images (⚠️ in the summary), and 015 has informational `use-trusted-publishing` findings for its token-based `npm publish`. |
| Jenkins execution (trace) | 18/20 run to completion after automatic localisation. 017 and 018 stop on their own `error()`, in branches decided by values that trace mode stubs. |
| act vs Jenkins (trace) | **15/20 equivalent**: 003, 004, 005, 006, 007, 009 (26-cell matrix), 010, 011, 012, 013, 014 (8-cell matrix), 015, 016, 019, 020. **2 inconclusive** (017, 018). 001, 002 and 008 differ: they fan out stages over runtime-built collections. |
| Real GitHub Actions, self-hosted JIT runners (trace) | **4/4 equivalent** (004, 012, 013, 014), 0 billable minutes. |
| Walkthrough [000](../examples/000/README.md) | Equivalent on act in trace and full mode for three scenarios (default, snapshot without deploy, integration tests off); full mode also compares the 20-21 JUnit test cases and the archived files. Earlier full-mode runs on real GitHub (self-hosted, both release scenarios) were equivalent on the outcome. Two deliberately broken conversions are caught: a wrong `when` (trace) and a dropped test report (full; both runs still succeed). These runs are an acceptance test: `pytest -m e2e tests/test_walkthrough.py`. |
| Full mode (real commands, 006; recorded before the output comparison) | Jenkins built the original repository and failed at `Publish` (no Nexus endpoint locally). The converted workflow failed one stage earlier, at `Build`: `packname` is built by string concatenation in `script{}`, which the converter flags *approximated* and does not propagate. The harness pinpoints the divergence (act gets no credential: the public source is fetched on the host). |

These are trace (control-flow) results, recorded against the current Jenkinsfile, conversion and scenario; runs of
an earlier version are marked stale and not counted. Trace equivalence shows the same stages run the same kinds of
steps in the same order for the scenario that was run - not that the commands or artifacts are equivalent, and not
that the conversion is correct: the harness finds differences, it cannot prove their absence (see
[What the verdicts establish](mechanism.md#what-the-verdicts-establish)).

The analysis predicted where conversion would struggle. The three examples that still differ all carry the
`DynamicParallel` hard gate (stages generated from runtime collections), and the two inconclusive ones branch on
values that trace mode stubs; see the limitations in
[architecture.md](architecture.md#known-limitations-and-where-to-extend).
