# Example 106: local twin of example 006

Derived from [example 006](../006/README.md) (fabiojose/platform-as-code-example, `Jenkinsfile` at `ee4cfb0`). The
original is kept verbatim in `examples/006/`; this copy is edited only as far as needed for the pipeline to run to
completion on the harness's Jenkins. Every edit is marked `// j2gha-local:` in the Jenkinsfile.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 64 | `curl -u $NEXUS_USERNAME:$NEXUS_PASSWORD --upload-file <pack> <publish_url>` | behind `echo` | no Nexus; `env.NEXUS_URL` is unset on the controller, so the URL began with `null` | `withCredentials(usernamePassword)` and the Groovy string concatenation of `packname`/`publish_url` |
| 79, 93, 139 | `bash $FOLLOW "artifact" <publish_url> <job id>` | behind `echo` | no Rundeck, and the managed script `rundeck-follow` (`configFileProvider`) is stubbed, so `$FOLLOW` is empty | the three deploy stages, their `when { expression }` gates, `withCredentials` and `configFileProvider` |
| 113 | `cd test && npm test` | `cd test && echo npm test` | the cucumber step definitions log in to an OpenShift cluster (`oc login`) | the stage's own `agent { label }` (a separate job), `npm install` of the test package, the `cucumber` report step |

Unchanged: the `script {}` block that computes `target`, `version`, `packname` and `publish_url` as Groovy
variables (lines 8-36), every `sed` and the `tar` in *Build*, the `input` in *Approval* inside `timeout`, and the four
`post` conditions with `rocketSend`.

**Expected result: Jenkins SUCCESS, converted run FAILURE, verdict *differs*.** The Groovy variables set in
`script {}` are reported as manual items by the converter and are never defined on the converted side, so *Build*'s
`tar ... -f ${packname}` fails there (`tar: option requires an argument -- 'f'`). This twin exists so that full mode
has a successful Jenkins reference for a pipeline whose conversion is known to be incomplete: the *differs* verdict
is the correct, reproducible statement of that gap, where the original 006 only compared two failures.

Scenario: `uv run j2gha run 106 --tier jenkins,act --mode full` (branch `master`, so `target = 'pro'` and every
stage, including the input gate, runs on Jenkins).

Result (2026-10-09, Jenkins full vs act full): Jenkins **SUCCESS** through every stage including the input gate
(the harness approves it); act **failure** at *Build*, verdict **differs**, as expected: the converted `tar` step has
no `${packname}`. This is the reproducible statement of the Groovy-variable gap described above.
