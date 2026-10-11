# Example 118: local twin of example 018

Derived from [example 018](../018/README.md) (dvsa/olcs-ci, `pipelines/app_release_package/Jenkinsfile` at
`e7e9913`). The original is kept verbatim in `examples/018/`; this copy is edited only as far as needed for the
pipeline to run to completion on the harness's Jenkins in full mode. Every edited or inserted line is marked
`// j2gha-local:` in the Jenkinsfile.

**This twin is cut-down.** The original works against DVSA-private infrastructure: ten repositories and the
`app-version` repository on an internal GitLab (`git@repo.shd.ci.nonprod.dvsa.aws:`, unreachable), S3 buckets listed
with `s3cmd`, and eleven downstream Jenkins jobs (`Build_*`, `Check App Release Tags`). The twin keeps the pipeline's
own work real: the Groovy `for` loops, the `checkout` steps (pointed at local stand-in repositories), the `git
describe` tag arithmetic, `readFile`/`grep` parsing, the `build job:` calls (harness stubs returning SUCCESS), the
hiera manifest `writeFile`, and the `git commit`/`git push` of the release-candidate branch (to the local stand-in).
Only the GitLab host, the S3 listings and the job-configuration parameters are replaced. The cited repository itself
(olcs-ci) is never checked out by this pipeline, which is as in the original.

Line numbers are the twin's; the original's line is in brackets where it differs.

| Line | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 9-14 (ins.) | `params.VERSION`, `params.DRYRUN`, `params.olcs_transxchange_version`, `params.olcs_auth_version` read from the job configuration | `properties([parameters([booleanParam DRYRUN=false, string VERSION='1.0.0', string olcs_transxchange_version='2.0.0', string olcs_auth_version='3.0.0'])])` | the original's parameters lived in the job configuration, which the harness cannot reproduce and `--param` cannot set (H2); with them undefined the trace run died on `MISSING: openam-null`. Declaring the same four parameters in `properties()` is the Jenkinsfile's own way of holding job configuration: the harness defines them on the job (so `--param` works), the converter emits them as `workflow_dispatch` inputs, and every `params.X` read stays as written. This is the twin's one structural addition, chosen over a shadowing `def params = [...]` literal because it carries the values to both sides | yes: every `params.X` read |
| 20 (14) | `def GitRepo = 'git@repo.shd.ci.nonprod.dvsa.aws:'` | `"file://${env.WORKSPACE}/.gitlab/"` | the internal GitLab is unreachable (`Could not resolve hostname`); local repositories under the workspace stand in | yes: `GitRepo + repos[i][1] + '.git'` and the ten `checkout([$class: 'GitSCM', ...credentialsId: 'OLCS-Jenkins'...])` steps are untouched |
| 65 (ins.) | (inside `dir(repos[i][0])`, before `checkout`) | `sh "git init -q -b master ${WORKSPACE}/.gitlab/${repos[i][1]}.git && ... two empty commits a day apart, tagged v1.0.0 and v1.0.1"` | creates the repository the checkout then clones; two dated tags so `git describe --abbrev=0 --tags` (current tag) and the ldif special case `git describe ... \`git rev-list --tags --skip=1 --max-count=1\`` (previous tag) work unchanged, and the two address repositories carry the same tag so the `equalsIgnoreCase` branch in *Get App Release Tags* is the normal one | yes: the loop, `checkout`, both `git describe` commands, `readFile('result')`, `repos[i] += version` |
| 123 (116) | `s3cmd ls s3://<bucket> > result` | `echo "2018-03-29 13:20  1024  s3://<bucket><artefact>v1.0.0.tar.gz" > result` | no `s3cmd`, no AWS; a listing in the `s3cmd ls` format holding only the previous release, so the `grep` for `<artefact>v1.0.1.tar.gz` finds nothing, the current tag is "Creating" and `build job: Build_*` is called for all ten | yes: `sh "${cmd}"`, the `grep ... \|\| true` command, `readFile`, `file.contains(...)`, the `DRYRUN` branch, the ten `build job:` calls with their parameters |
| 155 (148) | `s3cmd ls s3://<bucket>openam/ > result` | `echo "... s3://<bucket>openam/openam-${params.olcs_auth_version}.tar.gz" > result` | as above; this listing holds the requested openam package, so the "Exists" branch is taken and the `error('Missing package')` is not | yes: the whole check, including the `error()` path (not taken) |
| 174 (167) | `s3cmd ls s3://<bucket>api/ > result` | `echo "... s3://<bucket>api/txc-${params.olcs_transxchange_version}.war" > result` | as line 155, for the txc package | yes |
| 216 (ins.) | (inside `dir('app-version')`, after `deleteDir()`) | `sh "git init -q -b develop ${WORKSPACE}/.gitlab/aws/app-version.git && ... hiera/app_version.eyaml committed"` | creates the `app-version` repository (a `develop` branch holding the hiera file) that the checkout clones and the push targets | yes: `deleteDir`, `checkout` of `refs/heads/develop`, `git checkout -b release-candidate`, `writeFile`, `git add`, the push |
| 221 (213) | `url: 'git@repo.shd.ci.nonprod.dvsa.aws:aws/app-version.git'` | `url: GitRepo + 'aws/app-version.git'` | the hard-coded GitLab URL takes the same stand-in prefix as the other repositories | yes: the `checkout` step and its `credentialsId` |
| 228 (220) | `sh "git commit -m \"Release ${VERSION}\""` | `sh "git -c user.name=j2gha -c user.email=j2gha@localhost commit -m ..."` | the harness node has no git identity, and `git commit` refuses without one | yes: the commit message with `${VERSION}`; `git push --set-upstream origin release-candidate` (line 229) is untouched and pushes for real, to the local stand-in only |

Not edited: `node('master')` (the localiser maps it to the built-in node), `deleteDir()`, the eleven `build job:`
calls (harness stubs returning SUCCESS in full mode, traced as `build`), the empty first stage, the `stageName`
binding assignments (Jenkins warns, harmless), `import org.jvnet.jenkins.plugins.nodelabelparameter.*` (removed by
the localiser). The `credentialsId: 'OLCS-Jenkins'` on the checkouts is not provisioned; the git plugin warns and
clones the `file://` repositories without it.

What this twin tests: a scripted pipeline whose stages are Groovy `for` loops over a list of repositories, with
`checkout`/`sh`/`readFile` inside the loop body, downstream `build job:` calls chosen by shell-parsed listings and a
boolean parameter, and a release manifest committed and pushed. All of it now runs for real on Jenkins (except the
downstream jobs, which are stubs by design); with `--param DRYRUN=true` the same pipeline takes the dry-run path
(ten `MISSING:` lines, no builds, the manifest only printed).

**Expected result: Jenkins SUCCESS; converted run FAILURE at *Get App Release Tags*; verdict *differs*.** The
converter emits both `for` loops as manual-migration placeholders (there is no stand-in repository creation and no
clone on the converted side), then runs the one unconditional command of *Get App Release Tags* for real:
`git describe --abbrev=0 --tags \`git rev-list ...\`` in `olcs-api-version/`, a plain directory created by `mkdir`
inside a workspace whose `.git` the converted `deleteDir` (`find . -mindepth 1 -delete`) has already removed. That
`git` call exits non-zero and fails the job before the `DRYRUN` gates (which the converter does map, as
`env.DRYRUN == 'true'` from the declared input) are reached. This is the reproducible statement of the loop gap: the
original 018 compared a Jenkins failure on `openam-null` with an act run of placeholders.

Scenario: `uv run j2gha run 118 --tier jenkins,act --mode full` (the declared defaults: `DRYRUN=false`, every
artefact "Creating", both input packages "Exists", manifest committed and pushed to the local stand-in). The dry-run
path: `uv run j2gha run 118 --tier jenkins,act --mode full --param DRYRUN=true`. No `--branch`: the pipeline never
checks out the cited repository, so the branch is immaterial.

Result (2026-10-10, Jenkins full vs act full): Jenkins **SUCCESS**, act **failure** at *Get App Release Tags*, verdict **differs**. The Groovy `for` loops are manual placeholders on the converted side (no stand-in repositories), and the converted `deleteDir` removes the checkout before an unconditional `git describe` runs, so it fails at *Get App Release Tags*; the Jenkins reference runs the ten checkouts from the local stand-in GitLab, the ten stubbed downstream builds and the manifest push.
