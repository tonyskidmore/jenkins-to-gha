# Example 109: local twin of example 009

Derived from [example 009](../009/README.md) (TheHPXProject/hpx, `.jenkins/lsu/Jenkinsfile` at `0aa9f24`). The
original is kept verbatim in `examples/009/`; this copy is edited only as far as needed for the pipeline to run to
completion in the harness. Every edit is marked `// j2gha-local:` / `# j2gha-local:` in the Jenkinsfile.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 72 | `.jenkins/lsu/entry.sh` | a shell snippet that writes `jenkins-hpx-<configuration>-<build_type>.out` and `build/<configuration>-<build_type>/Testing/Temporary/LastTest.log` | `entry.sh` submits a Slurm job on the LSU cluster (`sbatch`), needs gcc 12-15, clang 16-20, CUDA, ROCm and GPUs, and posts a commit status to GitHub with a real token. The snippet produces the files the `post` section archives, so the matrix-to-archive path is exercised with real files | yes: the 26-cell matrix, `dir()`, the `#!/bin/bash -l` shebang, the `credentials()` environment, `milestone`, and both `post always` archives are unchanged |

What this twin tests that the original cannot: `archiveArtifacts` in the pipeline `post` of files written by matrix
cells. Jenkins runs every cell in the one workspace, so the post archives 26 `.out` files and 26 `LastTest.log`
files; the converted workflow's post job must receive those files from the cells (the workspace hand-off does not
hand matrix cells' changes on, a documented limit: `docs/mechanism.md`, *Approximated by design*). A *differs* verdict
here is the expected, real finding until that limit is lifted.

The snippet reads `GIT_COMMIT`, as the original `entry.sh` does (`GIT_COMMIT: unbound variable` was the converted
side's failure in the full-mode sweep): the converted workflow must export it even though the Jenkinsfile never
mentions it.

Scenario: `uv run j2gha run 109 --tier jenkins,act --mode full` (default branch `master`). The Jenkins run clones
hpx twice (about 45 s each) and runs 26 cells; the converted run restores the checked-out workspace in every cell.

Result (2026-10-09, Jenkins full vs act full): Jenkins **SUCCESS**, 52 files archived (26 `.out`, 26
`LastTest.log`); act **failure**, verdict *differs*. Under act, 25 of the 26 cells restored the workspace and one
failed its restore step in 69 ms with act's bare `<nil>` error while all 26 jobs copied the download-artifact action
into their containers at once (an act concurrency fault, not a conversion result); the merge in the post job then
refused, as designed, because a cell that ran had no workspace to hand on, and both post archives found no files.
The self-hosted tier is the evidence for this twin.

Self-hosted tier (2026-10-09, run 37984389813): **differs**, exactly the documented limit. All 27 jobs (checkout
and the 26 cells) succeeded; the post job's two `archiveArtifacts` steps failed with no files, because matrix cells'
workspace changes are not handed on to the pipeline `post` (Jenkins archived 52 files, the converted run 0). This is
the first reproducible case of that limit on real GitHub. Cost: one 37 MB workspace archive restored by every cell,
2,503 s of hand-off steps summed over jobs, 161 s on the critical path of a 1,001 s run.

act, three attempts: each one lost a job to act's bare `<nil>` error on a `docker cp` into a job container (once a
cell's restore, twice the checkout job's own workspace copy of the 37 MB hpx tree); the host workspace was clean
each time. act is not a usable tier for this twin; the self-hosted and hosted tiers are.
