# Migration report: dvsa/recalls-pipeline `jenkinsfile.groovy`

- **Classification:** assisted (difficulty 36/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 34.5% (30 mapped, 53 approximated, 100 manual, 3 dropped)
- **Weighted step coverage (analysis):** 84.3%

## Difficulty breakdown

| Dimension | Score | Max |
|---|---:|---:|
| declarative structure | 10 | 20 |
| step mapping | 3.9 | 25 |
| plugin coupling | 6.0 | 15 |
| library opacity | 11 | 15 |
| runtime coupling | 4.0 | 10 |
| security identity | 0 | 10 |
| control flow | 1.0 | 5 |

- **Hard gates:** none
- **Unknown steps (1):** `fail` - plugin or shared-library steps the step catalog does not know, each a manual item below. If every one were mapped, the difficulty would be **34/100 - assisted**.
- How the score is built: `docs/scoring.md` in the j2gha repository.

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `options: disableConcurrentBuilds` |  |  | concurrency | GHA keeps only the latest pending run per group |
| ✅ mapped | `post always` |  |  | final job if: always() |  |
| ✅ mapped | `post failure` |  |  | final job if: always() && (contains(needs.*.result, 'failure') || failure()) |  |
| ✅ mapped | `assign buildUser = env.BUILD_USER ` | 202 | Init: TF deployment bucket | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `decl releaseTimestamp = sh(script: 'date +%Y%m%d%H%M%S'` | 213 | Init: TF deployment bucket | run step; its output goes to $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `assign manifestVersion = ${releaseTimestamp}_${env.BUILD_` | 214 | Init: TF deployment bucket | run: $GITHUB_ENV | later steps of the job read the variable |
| ✅ mapped | `dir` | 225 | Init: TF deployment bucket | working-directory |  |
| ✅ mapped | `dir` | 252 | Init: Verify environment | working-directory |  |
| ✅ mapped | `dir` | 322 | Build: CVR frontend | working-directory |  |
| ✅ mapped | `deleteDir` | 323 | Build: CVR frontend | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `dir` | 335 | Build: CVR frontend | working-directory |  |
| ✅ mapped | `dir` | 355 | Build: CVR backend | working-directory |  |
| ✅ mapped | `deleteDir` | 356 | Build: CVR backend | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `dir` | 368 | Build: CVR backend | working-directory |  |
| ✅ mapped | `dir` | 387 | Build: frontend assets | working-directory |  |
| ✅ mapped | `deleteDir` | 388 | Build: frontend assets | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `dir` | 401 | Build: frontend assets | working-directory |  |
| ✅ mapped | `dir` | 402 | Build: frontend assets | working-directory |  |
| ✅ mapped | `sh` | 403 | Build: frontend assets | run |  |
| ✅ mapped | `dir` | 456 | Build: CVR data update module | working-directory |  |
| ✅ mapped | `deleteDir` | 457 | Build: CVR data update module | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `dir` | 469 | Build: CVR data update module | working-directory |  |
| ✅ mapped | `dir` | 494 | Deploy: Upload CVR frontend package | working-directory |  |
| ✅ mapped | `dir` | 513 | Deploy: Upload CVR backend package | working-directory |  |
| ✅ mapped | `dir` | 532 | Deploy: Upload CVR data update package | working-directory |  |
| ✅ mapped | `dir` | 551 | Deploy: Terraform CVR | working-directory |  |
| ✅ mapped | `dir` | 634 | Deploy: Upload CVR frontend assets | working-directory |  |
| ✅ mapped | `dir` | 639 | Deploy: Upload CVR frontend assets | working-directory |  |
| ✅ mapped | `dir` | 684 | Load test data to DB | working-directory |  |
| ✅ mapped | `dir` | 692 | Load test data to DB | working-directory |  |
| ⚪ dropped | `options: ansiColor` |  |  | - | native in GitHub Actions |
| ⚪ dropped | `options: timestamps` |  |  | - | native in GitHub Actions |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 60 (per job) | Jenkins timeout covers the whole pipeline |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `agent label '${jenkinsCtrlNodeLabel} && ${account}'` | 183 | Init | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `stage 'Init: Check DB data completion' when` | 186 | Init: Check DB data completion | if: env.action == 'apply' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 188 | Init: Check DB data completion | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (params.force_reload_data == 'true')` | 190 | Init: Check DB data completion | if: env.force_reload_data == 'true' |  |
| 🟡 approximated | `destroyExistingDbTables() (local helper method)` | 192 | Init: Check DB data completion | inlined | body of the Jenkinsfile helper method inlined with params substituted |
| 🟡 approximated | `isAnyDbTableMissing() (local helper method)` | 194 | Init: Check DB data completion | inlined | body of the Jenkinsfile helper method inlined with params substituted |
| 🟡 approximated | `script {}` | 201 | Init: TF deployment bucket | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `wrap` | 202 | Init: TF deployment bucket | body inlined | wrapper semantics not reproduced |
| 🟡 approximated | `getAwsFunctions() (local helper method)` | 203 | Init: TF deployment bucket | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `sh` | 213 | Init: TF deployment bucket | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `stage 'Init: Verify environment' when` | 239 | Init: Verify environment | if: env.action != 'destroy' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 242 | Init: Verify environment | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `getOutputOrFail() (local helper method)` | 253 | Init: Verify environment | inlined | body of the Jenkinsfile helper method inlined with output, messageOnFailure substituted |
| 🟡 approximated | `getOutputOrFail() (local helper method)` | 256 | Init: Verify environment | inlined | body of the Jenkinsfile helper method inlined with output, messageOnFailure substituted |
| 🟡 approximated | `getOutputOrFail() (local helper method)` | 259 | Init: Verify environment | inlined | body of the Jenkinsfile helper method inlined with output, messageOnFailure substituted |
| 🟡 approximated | `getOutputOrFail() (local helper method)` | 262 | Init: Verify environment | inlined | body of the Jenkinsfile helper method inlined with output, messageOnFailure substituted |
| 🟡 approximated | `getAwsFunctions() (local helper method)` | 267 | Init: Verify environment | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `stage 'Build' failFast` | 313 | Build | - | GHA cannot cancel sibling jobs outside a matrix; consider strategy.fail-fast |
| 🟡 approximated | `stage 'Build' parallel (4 branches)` | 313 | Build | parallel jobs with needs | branches and later stages no longer share the workspace: files made by earlier stages are not available (add stash/unstash or artifacts) |
| 🟡 approximated | `stage 'Build' when` | 314 | Build | if: env.action == 'apply' | evaluated once at stage entry against env |
| 🟡 approximated | `agent label '${jenkinsBuildLabel} && ${account}'` | 319 | Build / Build: CVR frontend | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 321 | Build: CVR frontend | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `getRevisionFromArtifactName() (local helper method)` | 336 | Build: CVR frontend | inlined | body of the Jenkinsfile helper method inlined with artifactName substituted |
| 🟡 approximated | `agent label '${jenkinsBuildLabel} && ${account}'` | 352 | Build / Build: CVR backend | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 354 | Build: CVR backend | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `getRevisionFromArtifactName() (local helper method)` | 369 | Build: CVR backend | inlined | body of the Jenkinsfile helper method inlined with artifactName substituted |
| 🟡 approximated | `agent label '${jenkinsBuildLabel} && ${account}'` | 384 | Build / Build: frontend assets | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 386 | Build: frontend assets | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `agent label '${jenkinsBuildLabel} && ${account}'` | 453 | Build / Build: CVR data update module | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 455 | Build: CVR data update module | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `getRevisionFromArtifactName() (local helper method)` | 470 | Build: CVR data update module | inlined | body of the Jenkinsfile helper method inlined with artifactName substituted |
| 🟡 approximated | `script {}` | 493 | Deploy: Upload CVR frontend package | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `script {}` | 512 | Deploy: Upload CVR backend package | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `script {}` | 531 | Deploy: Upload CVR data update package | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `script {}` | 549 | Deploy: Terraform CVR | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `stage 'Deploy: Upload CVR frontend assets' when` | 595 | Deploy: Upload CVR frontend assets | if: env.action == 'apply' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 598 | Deploy: Upload CVR frontend assets | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `stage 'Deploy: Manifest' when` | 650 | Deploy: Manifest | if: env.action == 'apply' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 652 | Deploy: Manifest | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `agent label '${jenkinsBuildLabel} && ${account}'` | 672 | Load test data to DB | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 674 | Load test data to DB | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `agent label '${jenkinsCtrlNodeLabel} && ${account}'` | 706 | Tests | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `stage 'Tests' when` | 707 | Tests | if: env.action == 'apply' && env.skip_tests != 'true' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 709 | Tests | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `sh` | 711 | Tests | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `node (in steps)` | 766 | Declarative: Post Actions | inlined | nested agent allocation flattened |
| 🟡 approximated | `script {}` | 767 | Declarative: Post Actions | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (params.clean_workspace == "true")` | 768 | Declarative: Post Actions | if: env.clean_workspace == 'true' |  |
| 🟡 approximated | `node (in steps)` | 782 | Declarative: Post Actions | inlined | nested agent allocation flattened |
| 🟡 approximated | `script {}` | 783 | Declarative: Post Actions | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (params.clean_workspace == "true")` | 784 | Declarative: Post Actions | if: env.clean_workspace == 'true' |  |
| 🟡 approximated | `script {}` | 795 | Declarative: Post Actions | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🔴 manual | `return ()` | 74 | Init: TF deployment bucket | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `info` | 93 | Build: CVR frontend | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `return ()` | 94 | Build: CVR frontend | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `assign output = [status: 0, stdout: abc1234, stderr: ]` | 98 | Init: Verify environment | - | Groovy variable assignment |
| 🔴 manual | `if (output.status)` | 99 | Init: Verify environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `return ()` | 104 | Init: Verify environment | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `decl isAnyTableMissing = False` | 131 | Init: Check DB data completion | - | Groovy variable assignment |
| 🔴 manual | `for (getDbTables(params))` | 133 | Init: Check DB data completion | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `info` | 139 | Init: Check DB data completion | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `return ()` | 140 | Init: Check DB data completion | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `for (getDbTables(params))` | 144 | Init: Check DB data completion | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `assign shouldLoadDbData = False` | 189 | Init: Check DB data completion | - | Groovy variable assignment |
| 🔴 manual | `info` | 191 | Init: Check DB data completion | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign shouldLoadDbData = isAnyDbTableMissing(...)` | 194 | Init: Check DB data completion | - | Groovy variable assignment from a step |
| 🔴 manual | `decl output = getAwsFunctions().awsCli(...)` | 203 | Init: TF deployment bucket | - | Groovy variable assignment from a step |
| 🔴 manual | `assign output = [status: 0, stdout: 123456789012]` | 206 | Init: TF deployment bucket | - | Groovy variable assignment |
| 🔴 manual | `if (output.status)` | 207 | Init: TF deployment bucket | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `assign accountId = output.stdout.trim(...)` | 211 | Init: TF deployment bucket | - | Groovy variable assignment from a step |
| 🔴 manual | `trim` | 211 | Init: TF deployment bucket | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `assign projectBucketPrefix = ${project}-${accountId}-${gl` | 212 | Init: TF deployment bucket | - | Groovy variable assignment |
| 🔴 manual | `assign currentBuild.description = CVR ${params.action} <b` | 215 | Init: TF deployment bucket | - | Groovy variable assignment |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 216 | Init: TF deployment bucket | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh(returnStatus: true, script: "echo terraform sca)` | 226 | Init: TF deployment bucket | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 243 | Init: Verify environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `decl backendRevision = getOutputOrFail(...)` | 253 | Init: Verify environment | - | Groovy variable assignment from a step |
| 🔴 manual | `decl frontendRevision = getOutputOrFail(...)` | 256 | Init: Verify environment | - | Groovy variable assignment from a step |
| 🔴 manual | `decl commonsRevision = getOutputOrFail(...)` | 259 | Init: Verify environment | - | Groovy variable assignment from a step |
| 🔴 manual | `decl dataUpdateRevision = getOutputOrFail(...)` | 262 | Init: Verify environment | - | Groovy variable assignment from a step |
| 🔴 manual | `decl isNewCommonsRevision = True` | 265 | Init: Verify environment | - | Groovy variable assignment |
| 🔴 manual | `decl manifestsListing = getAwsFunctions().awsCli(...)` | 267 | Init: Verify environment | - | Groovy variable assignment from a step |
| 🔴 manual | `if (!manifestsListing.status && manifestsListing.stdou)` | 268 | Init: Verify environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (isNewVersion[frontendAppName])` | 294 | Init: Verify environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (isNewVersion[backendAppName])` | 297 | Init: Verify environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (isNewVersion[dataUpdateModuleName])` | 300 | Init: Verify environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (isNewCommonsRevision)` | 303 | Init: Verify environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Build: CVR frontend' when` | 318 | Build: CVR frontend | if: vars.J2GHA_WHEN_L318 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 326 | Build: CVR frontend | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `decl revision = getRevisionFromArtifactName(...)` | 336 | Build: CVR frontend | - | Groovy variable assignment from a step |
| 🔴 manual | `info` | 337 | Build: CVR frontend | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl feVersion = "${manifestVersion}_${revision}".toStr` | 338 | Build: CVR frontend | - | Groovy variable assignment from a step |
| 🔴 manual | `toString` | 338 | Build: CVR frontend | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (buildPackage(frontendAppName, feVersion))` | 340 | Build: CVR frontend | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Build: CVR backend' when` | 351 | Build: CVR backend | if: vars.J2GHA_WHEN_L351 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 359 | Build: CVR backend | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `decl revision = getRevisionFromArtifactName(...)` | 369 | Build: CVR backend | - | Groovy variable assignment from a step |
| 🔴 manual | `info` | 370 | Build: CVR backend | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl backendVersion = "${manifestVersion}_${revision}".` | 371 | Build: CVR backend | - | Groovy variable assignment from a step |
| 🔴 manual | `toString` | 371 | Build: CVR backend | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (buildPackage(backendAppName, backendVersion))` | 373 | Build: CVR backend | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 391 | Build: frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `decl assetsVersion = null` | 400 | Build: frontend assets | - | Groovy variable assignment |
| 🔴 manual | `assign assetsVersion = readFile(...)` | 404 | Build: frontend assets | - | Groovy variable assignment from a step |
| 🔴 manual | `readFile` | 404 | Build: frontend assets | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `if (!assetsVersion)` | 405 | Build: frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 410 | Build: frontend assets | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 412 | Build: frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Build: CVR data update module' when` | 452 | Build: CVR data update module | if: vars.J2GHA_WHEN_L452 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 460 | Build: CVR data update module | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `decl revision = getRevisionFromArtifactName(...)` | 470 | Build: CVR data update module | - | Groovy variable assignment from a step |
| 🔴 manual | `info` | 471 | Build: CVR data update module | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl dataUpdateVersion = "${manifestVersion}_${revision` | 472 | Build: CVR data update module | - | Groovy variable assignment from a step |
| 🔴 manual | `toString` | 472 | Build: CVR data update module | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (buildPackage(dataUpdateModuleName, dataUpdateVersi)` | 474 | Build: CVR data update module | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Deploy: Upload CVR frontend package' when` | 490 | Deploy: Upload CVR frontend package | if: vars.J2GHA_WHEN_L490 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!fileExists(frontendArtifact))` | 495 | Deploy: Upload CVR frontend package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 499 | Deploy: Upload CVR frontend package | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (sh(returnStatus: true, script: "echo aws s3 cp ${f)` | 500 | Deploy: Upload CVR frontend package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Deploy: Upload CVR backend package' when` | 509 | Deploy: Upload CVR backend package | if: vars.J2GHA_WHEN_L509 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!fileExists(backendArtifact))` | 514 | Deploy: Upload CVR backend package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 518 | Deploy: Upload CVR backend package | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (sh(returnStatus: true, script: "echo aws s3 cp ${b)` | 519 | Deploy: Upload CVR backend package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Deploy: Upload CVR data update package' when` | 528 | Deploy: Upload CVR data update package | if: vars.J2GHA_WHEN_L528 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!fileExists(dataUpdateArtifact))` | 533 | Deploy: Upload CVR data update package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 537 | Deploy: Upload CVR data update package | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (sh(returnStatus: true, script: "echo aws s3 cp ${d)` | 538 | Deploy: Upload CVR data update package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `checkoutGitRepo` | 550 | Deploy: Terraform CVR | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl frontendTfVar = -var lambda_frontend_s3_key=${mani` | 552 | Deploy: Terraform CVR | - | Groovy variable assignment |
| 🔴 manual | `decl backendTfVar = -var lambda_backend_s3_key=${manife` | 553 | Deploy: Terraform CVR | - | Groovy variable assignment |
| 🔴 manual | `decl dataUpdateTfVar = -var lambda_data_update_s3_key=$` | 554 | Deploy: Terraform CVR | - | Groovy variable assignment |
| 🔴 manual | `decl tfLambdaParams = "${frontendTfVar} ${backendTfVar}` | 555 | Deploy: Terraform CVR | - | Groovy variable assignment from a step |
| 🔴 manual | `toString` | 555 | Deploy: Terraform CVR | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (sh(returnStatus: true, script: "echo terraform sca)` | 556 | Deploy: Terraform CVR | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (isNewVersion['assets'])` | 599 | Deploy: Upload CVR frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 626 | Deploy: Upload CVR frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh(returnStatus: true, script: "echo aws s3 cp . s)` | 635 | Deploy: Upload CVR frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh(returnStatus: true, script: "echo aws s3 cp . s)` | 640 | Deploy: Upload CVR frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `writeJSON` | 653 | Deploy: Manifest | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `if (!fileExists("${env.WORKSPACE}/manifests/manifest_$)` | 657 | Deploy: Manifest | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh(returnStatus: true, script: "echo aws s3 cp ${e)` | 661 | Deploy: Manifest | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Load test data to DB' when` | 671 | Load test data to DB | if: vars.J2GHA_WHEN_L671 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 675 | Load test data to DB | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh (
                script: "echo npm run build:$)` | 685 | Load test data to DB | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh(
                  script: "AWS_REGION=${global)` | 693 | Load test data to DB | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 710 | Tests | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 712 | Tests | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (fileExists(github.front_end.name))` | 769 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (fileExists(github.cvr_app.name))` | 774 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (fileExists(gitlab.cvr_terraform.name))` | 785 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (monitoredEnvironments.contains(params.environment))` | 796 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `fatal` | 803 | Declarative: Post Actions | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Stage graph

```text
pipeline [declarative] agent: none
├── Init  [agent label]
│   ├── Init: Check DB data completion  [when]
│   │   · script, <assign>×2, <if>, log.info, destroyExistingDbTables, isAnyDbTableMissing
│   ├── Init: TF deployment bucket
│   │   · script, wrap, <assign>×6, <decl>×2, getAwsFunctions, <if>×3, failure×3, output.stdout.trim …
│   └── Init: Verify environment  [when]
│       · script, <if>×7, failure×2, dir, <decl>×7, getOutputOrFail×4, getAwsFunctions, log.info×2 …
├── Build  [when; parallel]
│   ├── Build: CVR frontend  [when; agent label]
│   │   · script, dir×2, deleteDir, <if>×2, failure×2, <decl>×2, getRevisionFromArtifactName, log.info …
│   ├── Build: CVR backend  [when; agent label]
│   │   · script, dir×2, deleteDir, <if>×2, failure×2, <decl>×2, getRevisionFromArtifactName, log.info …
│   ├── Build: frontend assets  [agent label]
│   │   · script, dir×3, deleteDir, <if>×3, failure×3, <decl>, sh, <assign> …
│   └── Build: CVR data update module  [when; agent label]
│       · script, dir×2, deleteDir, <if>×2, failure×2, <decl>×2, getRevisionFromArtifactName, log.info …
├── Deploy
│   ├── Deploy: Upload CVR frontend package  [when; agent label]
│   │   · script, dir, <if>×2, failure×2, log.info
│   ├── Deploy: Upload CVR backend package  [when; agent label]
│   │   · script, dir, <if>×2, failure×2, log.info
│   ├── Deploy: Upload CVR data update package  [when; agent label]
│   │   · script, dir, <if>×2, failure×2, log.info
│   ├── Deploy: Terraform CVR  [agent label]
│   │   · script, repoFunctionsFactory.checkoutGitRepo, dir, <decl>×4, "${frontendTfVar} ${backendTfVar} ${dataUpdateTfVar}".toString, <if>, failure
│   ├── Deploy: Upload CVR frontend assets  [when; agent label]
│   │   · script, <if>×7, log.info, dir×3, failure×5
│   └── Deploy: Manifest  [when; agent label]
│       · script, writeJSON, <if>×2, failure×2
├── Load test data to DB  [when; agent label]
│   · script, <if>×3, failure×3, dir×2
└── Tests  [when; agent label]
    · script, log.info, sh, <if>, fail
post: always, failure
```

## Assumptions

- `when` conditions are evaluated once at stage entry (a step whose output the stage's steps test) against Jenkins-compatible env vars (`BRANCH_NAME`, `TAG_NAME`, `CHANGE_ID`...) defined at workflow level; hoist to job-level `if:` (github context) to save runner minutes.
- An untranslatable condition becomes a repository variable `J2GHA_WHEN_L<line>` ('true'/'false'); while it is unset the stage runs only where it would run whatever that condition's value.
- Stages sharing an agent run as steps of one job (shared workspace); parallel/matrix/agent/input stages become separate jobs. They do **not** share a workspace (use stash/unstash → artifacts).
- Actions are referenced by major version tag; pin to commit SHAs before production use (zizmor will flag this).
- Shell steps run with `bash -e -o pipefail` (Jenkins `sh` uses `/bin/sh -xe`); a retried step runs each attempt as its own process with the same options.

## Reference documentation

Where to read about each construct above, most work first: jenkins.io and docs.github.com (GitHub.com) pages from the crosswalk in `j2gha/rules/docs-xref.yaml`. With the local docs bundles fetched, `uv run j2gha docs xref <construct>` resolves the same pages offline, or for another GitHub version.

- **`scripted`** (🔴 73 manual, 🟡 32 approximated, ✅ 3 mapped): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`when`** (🔴 7 manual, 🟡 6 approximated): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`sh`** (🟡 2 approximated, ✅ 1 mapped): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 7 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`parallel`** (🟡 2 approximated): parallel stages -> independent jobs; failFast -> strategy.fail-fast only applies within a matrix.
  - Jenkins: [syntax #parallel](https://www.jenkins.io/doc/book/pipeline/syntax/#parallel)
  - GitHub Actions: [use-jobs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-jobs) · [workflow-syntax #jobsjob_idneeds](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)
- **`node`** (🟡 2 approximated)
  - Jenkins: [step `node`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [self-hosted-runners](https://docs.github.com/en/actions/concepts/runners/self-hosted-runners)
- **`options`** (⚪ 1 dropped)
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
- **`timestamps`** (⚪ 1 dropped): GHA logs are always timestamped - drop it.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [use-workflow-run-logs](https://docs.github.com/en/actions/how-tos/monitor-workflows/use-workflow-run-logs)
- **`buildDiscarder`** (⚪ 1 dropped): no per-count run retention; artifact retention-days and the repository log retention setting.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepswith](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepswith) · [workflow-artifacts](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts)
- **`disableConcurrentBuilds`** (✅ 1 mapped): abortPrevious true -> cancel-in-progress true.
  - Jenkins: [syntax #options](https://www.jenkins.io/doc/book/pipeline/syntax/#options)
  - GitHub Actions: [concurrency](https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency) · [control-workflow-concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency) · [workflow-syntax #concurrency](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#concurrency)
- **`post`** (✅ 2 mapped): always/success/failure/aborted -> if always()/success()/failure()/cancelled(); unstable/changed/fixed/regression have no equivalent.
  - Jenkins: [syntax #post](https://www.jenkins.io/doc/book/pipeline/syntax/#post)
  - GitHub Actions: [expressions #status-check-functions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions#status-check-functions) · [workflow-syntax #jobsjob_idstepsif](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsif)
- **`dir`** (✅ 19 mapped)
  - Jenkins: [step `dir`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsworking-directory](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsworking-directory)
- **`checkout`** (ℹ️ 1 info): actions/checkout fetches one commit by default (fetch-depth 0 for history/tags).
  - Jenkins: [step `checkout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [find-and-customize-actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/find-and-customize-actions)
