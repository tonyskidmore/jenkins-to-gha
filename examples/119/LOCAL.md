# Example 119: local twin of example 019

Derived from [example 019](../019/README.md) (dvsa/dvsa-mobile-pipeline, `ops/mobile_build.groovy` at `1827396`).
The original is kept verbatim in `examples/019/`; this copy is edited only as far as needed for the pipeline to run
to completion in the harness. Every edit is marked `// j2gha-local:` in the Jenkinsfile.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 168 | `stash name: "build", includes: "build/**"` | `..., allowEmpty: true` | the stage before it calls `MobileCoreFunctions.build()` from the shared library `MobilePipelineSharedLibrary`, which the harness stubs (it runs Xcode/fastlane on a macOS agent), so `build/` is empty and Jenkins fails the stash with *No files included in stash 'build'*. With `allowEmpty` the stash and the later `unstash "build"` on the master node succeed, as the first stash (`allowEmpty: true` at line 73) already does | yes: both stashes, the unstash across nodes, the parallel checkout, the `node('master')`/`node('mac')` topology |

Everything substantive in this pipeline is a shared-library call (`GitFunctions`, `CommonFunctions`,
`MobileCoreFunctions`), stubbed on the Jenkins side and emitted as *manual migration* placeholders on the converted
side, so a green run here shows only that the node/parallel/stash topology converts; it is not evidence about the
library's work. The library is public (`github.com/dvsa/dvsa-mobile-pipeline-libs`); a later twin could inline its
npm stages against a public Cordova app.

What this twin tests: `stash allowEmpty: true` followed by `unstash`, on both sides. In the full-mode sweep the
converted side failed at the unstash (`Artifact not found for name: stash-target_location`) because the upload of an
empty stash creates no artifact; the converter now marks such an unstash `continue-on-error`.

Scenario: `uv run j2gha run 119 --tier jenkins,act --mode full`.

Result (2026-10-09, Jenkins full vs act full): **equivalent**, both SUCCESS; the empty stash and its unstash passed
on both sides. No tests or archives on either side.

Self-hosted tier (2026-10-09, run 37983197226): **differs**. The `stash allowEmpty` / `unstash` pair passed on
real GitHub too (the download step tolerated the missing artifact), but the job then failed at *Build: dir*:
`mac_workspace` (from `pwd()`, a manual item) and `target_location` (a job-configuration parameter, also manual) are
empty on the converted side, so `dir("${mac_workspace}/${target_location}/platforms/ios")` becomes
`mkdir -p /platforms/ios`, which the non-root runner user cannot create. Under act the job container runs as root,
so the same step passed there. The verdict is right: the pipeline's directory layout depends on values the converter
reports as manual.
