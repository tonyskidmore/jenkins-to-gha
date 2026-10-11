# Example 117: local twin of example 017

Derived from [example 017](../017/README.md) (dvsa/recalls-pipeline, `jenkinsfile.groovy` at `356eb91`). The
original is kept verbatim in `examples/017/`; this copy is edited only as far as needed for the pipeline to run to
completion on the harness's Jenkins in full mode. Every edited or inserted line is marked `// j2gha-local:` in the
Jenkinsfile (`# j2gha-local:` inside shell text; the one exception is noted under line 727).

**This twin is cut-down.** The original depends on a private world that no edit replaces: the shared library
`PipelineUtils` (`AWSFunctions`, `RepoFunctions`, `GlobalValues`, the `log` global), an AWS account (STS, S3,
DynamoDB, CloudFront, API Gateway), terraform scaffold, an internal GitLab, the `cvr-app` and front-end repositories
and a Selenium grid. The harness turns the library into stub objects (every property/method is a truthy stub that
prints as `j2gha-stub`); the twin replaces every external call whose *result decides control flow* with a literal
stand-in and every build/deploy command with an `echo` that creates the files later steps read. What survives is the
real control flow: the nested `Init` stages, all 13 `when { expression }` gates, the four-way `parallel` Build with
`failFast`, the six Deploy stages, the Load-data and Tests stages, `wrap([$class: 'BuildUser'])`, `readJSON`,
`writeJSON`, `zip`, `publishHTML` and the `post { always / failure }` blocks (with `slackSend`, stubbed). A green run
shows that this structure executes and converts; it is not evidence about what the library or AWS would have done.

Line numbers are the twin's; the original's line is in brackets where it differs.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 10-11 | `gitlab = globalValuesFactory.GITLAB_REPOS()`, `github = ...GITHUB_REPOS()` | literal maps `[cvr_terraform: [url, name: 'cvr-terraform']]`, `[cvr_app: [.., name: 'cvr-app'], front_end: [.., name: 'cvr-front-end']]` | `GlobalValues` is a library stub, so `github.cvr_app.name` was a stub object and `dir()`/`fileExists()` cannot take one (the harness would otherwise GString-wrap each call, one auto-repair per site); the urls are never fetched because `checkoutGitRepo` is a stub | yes: every `dir(github.cvr_app.name)` and `fileExists(...)` site is untouched |
| 13-20 (ins.) | `APP_BRANCH`, `TF_BRANCH`, `ACTION`, `ENVIRONMENT`, `CLEAN_WORKSPACE`, `SELENIUM_HUB_ADDRESS`, `SKIP_TESTS`, `FORCE_RELOAD_DATA` read as bare globals | `String ACTION = 'apply'`, `ENVIRONMENT = 'int'`, `CLEAN_WORKSPACE = 'true'`, `SKIP_TESTS = 'false'`, `FORCE_RELOAD_DATA = 'false'`, branches `master`, a `.invalid` Selenium hub | job-configuration parameters (H2: `--param` cannot set them); as stubs they read `j2gha-stub`, so `params.action == 'apply'` was false and every gated stage was skipped. `apply` opens the gates, `int` is a monitored environment (the failure post would `slackSend`), `'true'` runs the post-always clean-up branch, `'false'` keeps the Tests stage and skips the table deletion | yes: the `params` map (line 21) and every read of it are untouched |
| 87 (79) | `npm run build:${directory} && mv cvr-${directory}.zip ...` | `echo npm run build:${directory} > cvr-${directory}.zip && mv ...` | no `package.json` (the clone is a stub); the echoed build writes the package the `mv`, the `fileExists` and the upload stand-ins in Deploy expect | yes: `buildPackage()` with `returnStatus`, the `mv`, the three Build stages that call it |
| 97-98 (89) | `String getOutputOrFail(Map output, ...)` / `if(output.status)` | parameter untyped (`def output`); `output = [status: 0, stdout: 'abc1234', stderr: '']` inserted before the test | `RepoFunctions.getRevision()` returns a library stub, which Groovy will not pass to a `Map` parameter and whose truthy `.status` would fail the build; one literal here serves the five call sites | yes: the status check, `failure()` on error, all five `getRevision` calls (stub, harmless) |
| 155 (146) | `if (domainOutput.status \|\| !domainOutput.stdout)` | `domainOutput = [status: 0, stdout: 'None']` inserted before | `awsCli` is a stub; `None` is what `aws cloudfront list-distributions` prints for no match, so neither custom domain exists and the deepest branch (API gateway lookup) is taken | yes: `isDomainInCloudfront()` and the three-level `if/else` in *Deploy: Terraform CVR* |
| 206 (196) | `if (output.status)` after `awsCli("aws sts get-caller-identity ...")` | `output = [status: 0, stdout: '123456789012']` inserted before | the stub's truthy `.status` is where the original run stopped (*Failure while retrieving AWS account ID*); a literal account id feeds `projectBucketPrefix` and the bucket names | yes: the check, the `wrap([$class: 'BuildUser'])` before it, the `date` `sh`, the manifest version |
| 226 (215-226) | `if (getAwsFunctions().terraformScaffold(project, ..., "deployment-bucket", bucketPrefix, params.action))` | `if (sh(returnStatus: true, script: "echo terraform scaffold ... deployment-bucket ${params.action}"))`, the original call kept in the trailing comment | no terraform, no AWS; the library call returns a truthy stub, which would be "failed". The echoed command's exit status keeps the check meaningful | the `if/else if (params.action != 'destroy')` structure, yes; the 12-line call collapses to one line |
| 403 (ins.) | `assetsVersion = readFile("assets.version")` | `sh 'echo 1.0.0 > assets.version'` inserted before | full mode reads files for real; the file came from the (stubbed) clone of `cvr-app` | yes: `readFile`, the `!assetsVersion` check, the nested `dir()` |
| 421 (ins.) | `if(fileExists("${github.front_end.name}/dist/assets"))` | `sh "mkdir -p .../dist/assets && echo 'stand-in asset' > .../app.js"` inserted before | the compiled assets came from the (stubbed) clone of the front-end repository; with the directory present the `zip` step, `isNewVersion['assets']` and the assets upload stage run | yes: `fileExists`, `getRevision`, the new/reused-assets branch, `zip(dir:, zipFile:)` |
| 500, 519, 538 (498, 517, 536) | `if(getAwsFunctions().copyFilesToS3(s3DeploymentBucket, '', <artifact>))` | `if(sh(returnStatus: true, script: "echo aws s3 cp <artifact> s3://${s3DeploymentBucket}/"))` | no AWS; the library wrapped `aws s3 cp` and returned its status, so the echoed command stands in and its status still decides | yes: the three upload stages, their `when` gates on `isNewVersion[...]`, the `fileExists(<artifact>)` checks |
| 556 (554-565) | `if (getAwsFunctions().terraformScaffold(project, ..., tfLambdaParams, ..., "cvr", ...))` | as line 226, with `${tfLambdaParams}` echoed | as line 226 | as line 226; `tfLambdaParams` (built from the manifest) is still computed and shown |
| 575 (584) | `if (output.status \|\| !output.stdout \|\| output.stdout.trim() == 'None')` | `output = [status: 0, stdout: 'abc123']` inserted before | the API gateway id query is an `awsCli` stub; the literal yields `recallsApiGwUrl = https://abc123.execute-api.<region>.amazonaws.com/int` | yes: the three-way check and `failure()` |
| 603, 607 (611, 615) | `copyFilesToS3(s3AssetsBucket, 'assets', ".../dist/assets/", "--recursive")`, `copyFilesToS3(s3DeploymentBucket, 'assets/', <zip>)` | echoed `aws s3 cp`, as line 500 | as line 500 | yes: the `isNewVersion['assets']` branch, `fileExists`, both checks; the `unzip` branch (line 617) is untouched and not reached |
| 635, 640 (643, 648) | `copyFilesToS3(s3AssetsBucket, 'documents' / 'errorpages', ".", "--recursive")` | echoed `aws s3 cp`, as line 500 | as line 500 | yes: both `dir("${github.cvr_app.name}/...")` blocks |
| 661 (669) | `copyFilesToS3(s3DeploymentBucket, "manifests/", <manifest json>)` | echoed `aws s3 cp`, as line 500 | as line 500 | yes: `writeJSON` of the manifest and the `fileExists` check before it |
| 686 (694) | `npm run build:${databaseTestLoaderModuleName}` | `echo npm run build:...` | no `package.json`, no DynamoDB | yes: the stage, its `when` on `shouldLoadDbData`, the `returnStatus` check |
| 694 (702) | `AWS_REGION=... ENVIRONMENT=... npm run loadDevData` | `... echo npm run loadDevData` | as above; the env prefix stays | yes |
| 711 (719) | `sh "curl ${recallsApiGwUrl}${warmupPath} --output /dev/null"` | `sh "echo curl ..."` | the gateway URL is a stand-in and the harness allows network only to GitHub and public registries | yes: the warm-up step and the URL assembled in Deploy |
| 726-727 (734) | `./gradlew clean build \` ... (continuation lines) | a `mkdir -p ./build/reports/tests/selenium && echo '<html>...' > .../index.html  # j2gha-local` line inserted, then `echo ./gradlew clean build \` | no Gradle and no Selenium grid; the echo prints the whole command (Groovy joins the `\`-continued lines) and exits 0, and the stand-in report is what `publishHTML` (`allowMissing: false`) expects. The `echo ./gradlew` line cannot carry a trailing marker because it ends in a shell continuation; the marker is on the line before it | yes: the `returnStatus` capture, `publishHTML`, the `archiveArtifacts` + `failure()` path on a non-zero status (not taken) |

Not edited, and why:

- `repoFunctionsFactory.checkoutGitRepo(...)` (9 calls): the stub is truthy, so `if (!checkoutGitRepo(...)) failure(...)` passes; nothing is cloned, which is why the lines above create the files a clone would have provided.
- `isDbTablePresent()`: `response.status == 0` is false on a stub, so every table counts as missing, `shouldLoadDbData` is true and *Load test data to DB* runs: the fresh-environment path, with no edit.
- `manifestsListing` (line 267): `!stub.status` is false, so the *No manifests present* branch runs, `readJSON(text: "{}")` starts an empty manifest and every `isNewVersion[...]` is true, which is what makes all three Build and Upload stages run.
- `log.info`/`log.fatal`, `globalValuesFactory.AWS_REGION` (appears as `j2gha-stub` in bucket names and the gateway URL), `SSH_DEPLOY_GIT_CREDS_ID`: library globals, left to the harness's stubs.
- `readJSON`, `writeJSON`, `zip`, `publishHTML` run for real (`pipeline-utility-steps`, `htmlpublisher`); `wrap`, `slackSend` are harness stubs; `buildDiscarder` is removed by the localiser.
- `archiveArtifacts` (line 749) is only reached when the Selenium stand-in fails, so a green run archives nothing; the outputs comparison is therefore empty on both sides. Adding an archive step was not done (it would be an addition, not a localisation).

What this twin tests: a Declarative pipeline whose whole control flow is driven by `script {}` Groovy state
(`isNewVersion`, `shouldLoadDbData`, `manifestContent`) and job-configuration parameters: 13 `when { expression }`
gates, nested stages with `failFast`, a four-way `parallel` with per-stage agents, `post` on a pipeline with
`agent none`, and the plugin steps `readJSON`/`writeJSON`/`zip`/`publishHTML`/`wrap`. On the Jenkins side the
expected auto-repairs are `stub-property log` and `untype-decl` (the `Map output`/`Map domainOutput` declarations
receive a stub before the stand-in literal replaces it); both are known mechanisms.

**Expected result: Jenkins SUCCESS; converted run success; verdict *same outcome*, but hollow.** The converter takes
the script-level `Map params` for Jenkins' `params` global and emits every `params.action == 'apply'` gate as
`env.action == 'apply'`, and no `action` variable exists in the workflow (there is no `parameters {}` directive), so
on GitHub Actions *Init: Check DB data completion*, the whole Build fan-out, the Upload stages, *Load test data to
DB* and *Tests* are skipped at their stage-entry step, and the `isNewVersion[...]`/`shouldLoadDbData` gates are
`vars.J2GHA_WHEN_L*` variables that are unset. What runs on the converted side is the unconditional residue of
*Init: TF deployment bucket*, *Init: Verify environment* and *Deploy: Terraform CVR* (manual-migration warnings,
`date`, `mkdir`), which succeeds. A *same outcome* verdict here therefore says only that neither side failed; the
Jenkins reference ran about twenty real `sh` steps through every stage, the converted side ran none of them. This is
the reproducible statement of two gaps: Groovy variables set in `script {}` are not carried into the converted
workflow (as for 106), and a script variable named `params` shadows the real `params` on Jenkins but is mapped as
if it were the real one by the converter. If Jenkins fails instead, the first suspects are the `zip` step on
absolute paths and the artifact paths that cross the `@2`/`@3` workspaces the concurrent Build stages get on one
controller (same filesystem, so they should resolve).

Scenario: `uv run j2gha run 117 --tier jenkins,act --mode full --branch master`. None of the 13 `when` expressions
reads the branch (they read `params.action`, `params.skip_tests`, `isNewVersion[...]` and `shouldLoadDbData`), so any
branch gives the same path; `master` is the repository's default branch and carries the cited commit, which
`checkout scm` fetches on both sides.

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **success**, verdict **equivalent**. Same outcome, but hollow on the converted side: the converter takes the script-level `Map params` for Jenkins' `params` global and gates every stage on `env.action`, which nothing sets, so all gated jobs are skipped there while Jenkins runs about 20 real `sh` steps through every stage.

Self-hosted tier (2026-10-10): **equivalent** (same as act).
