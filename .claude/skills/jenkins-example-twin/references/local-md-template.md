# LOCAL.md template

`examples/1NN/LOCAL.md` is the twin's contract: a reader must be able to see every edit, why it was needed, what
the twin still exercises, how to run it and what each tier showed. Keep the sections and their order; the
"Result" lines at the end are appended by `scripts/twin_results.py`.

```markdown
# Example 1NN: local twin of example 0NN

Derived from [example 0NN](../0NN/README.md) (<owner>/<repo>, `<path>` at `<short sha>`). The original is kept
verbatim in `examples/0NN/`; this copy is edited only as far as needed for the pipeline to run to completion in
the harness. Every edit is marked `// j2gha-local:` (Groovy) or `# j2gha-local:` (shell) in the Jenkinsfile.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 79 | `sh 'mvn -version'` | `sh 'python3 --version'` | no Maven on the act runner image | a real `sh` step |
| 87 | (none) | `sh 'printf ... > deploy.sh'` inserted before `chmod 777 deploy.sh` | the repository has no `deploy.sh` | the original chmod and `./deploy.sh` run unchanged |

Unchanged: <the directives, wrappers, stages, post blocks and library calls left as they were, so the reader
knows what the twin still tests>.

**What this twin tests:** <the one or two things the original could not show: a matrix whose cells' files the
post archives, a stash allowEmpty pair, a real build with JUnit output...>.

**Expected on the converted side:** <equivalent, or differs and the precise reason: a documented converter gap
(name it), a manual item, a tool only Jenkins has>. A *differs* that states a converter gap is a good outcome;
a hollow *equivalent* (every substantive step stubbed on both sides) must be called hollow.

Scenario: `uv run j2gha run 1NN --tier jenkins,act --mode full [--branch B] [--param NAME=VALUE]` (<why these
values: which `when` gates they open, which branch the cited commit is on>).
```

Rules for the table:

- One row per edited or inserted line, original line numbers, the exact original text (or `(none)` for an
  insertion), the exact edit, the reason, and what feature survives. A reader should be able to reconstruct
  the diff from the table.
- "Why" names the real obstacle (no daemon, private registry, library stubbed, job-configuration variable the
  harness cannot set, timing-dependent test...), not "to make it pass".
- If an edit removes a feature the example was chosen for (its library-template resolution, its Docker agents),
  say so in the row and again in the "Unchanged" paragraph: the corpus table still cites the original for that
  feature; the twin is the executable reference.
