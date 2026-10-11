# Migration report: dvsa/recalls-pipeline `jenkinsfile.groovy`

- **Classification:** significant-redesign (difficulty 46/100)
- **Convertibility:** partial
- **Automated mapping (effort estimate, not correctness):** 33.2% (26 mapped, 54 approximated, 100 manual, 3 dropped)
- **Weighted step coverage (analysis):** 82.8%

## Blocking items (hard gates)

- line ?: **SharedLibrary** - PipelineUtils@master → Library steps are opaque to static analysis; map them to composite actions/reusable workflows

## Mapping detail

| | Jenkins | Line | Stage | GitHub Actions | Note |
|---|---|---:|---|---|---|
| ✅ mapped | `options: disableConcurrentBuilds` |  |  | concurrency | GHA keeps only the latest pending run per group |
| ✅ mapped | `post always` |  |  | final job if: always() |  |
| ✅ mapped | `post failure` |  |  | final job if: always() && (contains(needs.*.result, 'failure') || failure()) |  |
| ✅ mapped | `dir` | 214 | Init: TF deployment bucket | working-directory |  |
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
| ✅ mapped | `dir` | 454 | Build: CVR data update module | working-directory |  |
| ✅ mapped | `deleteDir` | 455 | Build: CVR data update module | run: workspace cleanup | runners are ephemeral; kept for parity |
| ✅ mapped | `dir` | 467 | Build: CVR data update module | working-directory |  |
| ✅ mapped | `dir` | 492 | Deploy: Upload CVR frontend package | working-directory |  |
| ✅ mapped | `dir` | 511 | Deploy: Upload CVR backend package | working-directory |  |
| ✅ mapped | `dir` | 530 | Deploy: Upload CVR data update package | working-directory |  |
| ✅ mapped | `dir` | 549 | Deploy: Terraform CVR | working-directory |  |
| ✅ mapped | `dir` | 642 | Deploy: Upload CVR frontend assets | working-directory |  |
| ✅ mapped | `dir` | 647 | Deploy: Upload CVR frontend assets | working-directory |  |
| ✅ mapped | `dir` | 692 | Load test data to DB | working-directory |  |
| ✅ mapped | `dir` | 700 | Load test data to DB | working-directory |  |
| ⚪ dropped | `options: ansiColor` |  |  | - | native in GitHub Actions |
| ⚪ dropped | `options: timestamps` |  |  | - | native in GitHub Actions |
| 🟡 approximated | `options: timeout` |  |  | timeout-minutes: 60 (per job) | Jenkins timeout covers the whole pipeline |
| ⚪ dropped | `options: buildDiscarder` |  |  | - | use artifact retention-days / repo settings |
| 🟡 approximated | `agent label '${jenkinsCtrlNodeLabel} && ${account}'` | 173 | Init | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `stage 'Init: Check DB data completion' when` | 176 | Init: Check DB data completion | if: env.action == 'apply' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 178 | Init: Check DB data completion | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (params.force_reload_data == 'true')` | 180 | Init: Check DB data completion | if: env.force_reload_data == 'true' |  |
| 🟡 approximated | `destroyExistingDbTables() (local helper method)` | 182 | Init: Check DB data completion | inlined | body of the Jenkinsfile helper method inlined with params substituted |
| 🟡 approximated | `isAnyDbTableMissing() (local helper method)` | 184 | Init: Check DB data completion | inlined | body of the Jenkinsfile helper method inlined with params substituted |
| 🟡 approximated | `script {}` | 191 | Init: TF deployment bucket | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `wrap` | 192 | Init: TF deployment bucket | body inlined | wrapper semantics not reproduced |
| 🟡 approximated | `getAwsFunctions() (local helper method)` | 193 | Init: TF deployment bucket | inlined | body of the Jenkinsfile helper method inlined |
| 🟡 approximated | `decl releaseTimestamp = sh(script: 'date +%Y%m%d%H%M%S'` | 202 | Init: TF deployment bucket | run step (captured output not propagated) | write values to $GITHUB_OUTPUT/$GITHUB_ENV |
| 🟡 approximated | `sh` | 202 | Init: TF deployment bucket | run | Groovy interpolation of non-env values needs review |
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
| 🟡 approximated | `agent label '${jenkinsBuildLabel} && ${account}'` | 451 | Build / Build: CVR data update module | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 453 | Build: CVR data update module | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `getRevisionFromArtifactName() (local helper method)` | 468 | Build: CVR data update module | inlined | body of the Jenkinsfile helper method inlined with artifactName substituted |
| 🟡 approximated | `script {}` | 491 | Deploy: Upload CVR frontend package | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `script {}` | 510 | Deploy: Upload CVR backend package | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `script {}` | 529 | Deploy: Upload CVR data update package | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `script {}` | 547 | Deploy: Terraform CVR | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `stage 'Deploy: Upload CVR frontend assets' when` | 603 | Deploy: Upload CVR frontend assets | if: env.action == 'apply' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 606 | Deploy: Upload CVR frontend assets | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `stage 'Deploy: Manifest' when` | 658 | Deploy: Manifest | if: env.action == 'apply' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 660 | Deploy: Manifest | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `agent label '${jenkinsBuildLabel} && ${account}'` | 680 | Load test data to DB | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `script {}` | 682 | Load test data to DB | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `agent label '${jenkinsCtrlNodeLabel} && ${account}'` | 714 | Tests | runs-on: ubuntu-latest | use a self-hosted runner label if the agent provides special tooling/network |
| 🟡 approximated | `stage 'Tests' when` | 715 | Tests | if: env.action == 'apply' && env.skip_tests != 'true' | evaluated once at stage entry against env |
| 🟡 approximated | `script {}` | 717 | Tests | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `sh` | 719 | Tests | run | Groovy interpolation of non-env values needs review |
| 🟡 approximated | `node (in steps)` | 773 | Declarative: Post Actions | inlined | nested agent allocation flattened |
| 🟡 approximated | `script {}` | 774 | Declarative: Post Actions | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (params.clean_workspace == "true")` | 775 | Declarative: Post Actions | if: env.clean_workspace == 'true' |  |
| 🟡 approximated | `node (in steps)` | 789 | Declarative: Post Actions | inlined | nested agent allocation flattened |
| 🟡 approximated | `script {}` | 790 | Declarative: Post Actions | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🟡 approximated | `if (params.clean_workspace == "true")` | 791 | Declarative: Post Actions | if: env.clean_workspace == 'true' |  |
| 🟡 approximated | `script {}` | 802 | Declarative: Post Actions | inner steps translated individually | imperative Groovy is not executed; review control flow |
| 🔴 manual | `return ()` | 66 | Init: TF deployment bucket | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `info` | 85 | Build: CVR frontend | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `return ()` | 86 | Build: CVR frontend | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `if (output.status)` | 90 | Init: Verify environment | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `return ()` | 95 | Init: Verify environment | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `decl isAnyTableMissing = False` | 122 | Init: Check DB data completion | - | Groovy variable assignment |
| 🔴 manual | `for (getDbTables(params))` | 124 | Init: Check DB data completion | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `info` | 130 | Init: Check DB data completion | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `return ()` | 131 | Init: Check DB data completion | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `for (getDbTables(params))` | 135 | Init: Check DB data completion | placeholder | Groovy control flow requires manual migration |
| 🔴 manual | `assign shouldLoadDbData = False` | 179 | Init: Check DB data completion | - | Groovy variable assignment |
| 🔴 manual | `info` | 181 | Init: Check DB data completion | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `assign shouldLoadDbData = isAnyDbTableMissing(...)` | 184 | Init: Check DB data completion | - | Groovy variable assignment from a step |
| 🔴 manual | `assign buildUser = env.BUILD_USER ` | 192 | Init: TF deployment bucket | - | Groovy variable assignment |
| 🔴 manual | `decl output = getAwsFunctions().awsCli(...)` | 193 | Init: TF deployment bucket | - | Groovy variable assignment from a step |
| 🔴 manual | `if (output.status)` | 196 | Init: TF deployment bucket | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `assign accountId = output.stdout.trim(...)` | 200 | Init: TF deployment bucket | - | Groovy variable assignment from a step |
| 🔴 manual | `trim` | 200 | Init: TF deployment bucket | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `assign projectBucketPrefix = ${project}-${accountId}-${gl` | 201 | Init: TF deployment bucket | - | Groovy variable assignment |
| 🔴 manual | `assign manifestVersion = ${releaseTimestamp}_${env.BUILD_` | 203 | Init: TF deployment bucket | - | Groovy variable assignment |
| 🔴 manual | `assign currentBuild.description = CVR ${params.action} <b` | 204 | Init: TF deployment bucket | - | Groovy variable assignment |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 205 | Init: TF deployment bucket | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (getAwsFunctions().terraformScaffold(
             )` | 215 | Init: TF deployment bucket | placeholder | condition depends on Groovy runtime state |
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
| 🔴 manual | `assign assetsVersion = readFile(...)` | 403 | Build: frontend assets | - | Groovy variable assignment from a step |
| 🔴 manual | `readFile` | 403 | Build: frontend assets | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `if (!assetsVersion)` | 404 | Build: frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 409 | Build: frontend assets | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 411 | Build: frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Build: CVR data update module' when` | 450 | Build: CVR data update module | if: vars.J2GHA_WHEN_L450 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 458 | Build: CVR data update module | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `decl revision = getRevisionFromArtifactName(...)` | 468 | Build: CVR data update module | - | Groovy variable assignment from a step |
| 🔴 manual | `info` | 469 | Build: CVR data update module | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl dataUpdateVersion = "${manifestVersion}_${revision` | 470 | Build: CVR data update module | - | Groovy variable assignment from a step |
| 🔴 manual | `toString` | 470 | Build: CVR data update module | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (buildPackage(dataUpdateModuleName, dataUpdateVersi)` | 472 | Build: CVR data update module | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Deploy: Upload CVR frontend package' when` | 488 | Deploy: Upload CVR frontend package | if: vars.J2GHA_WHEN_L488 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!fileExists(frontendArtifact))` | 493 | Deploy: Upload CVR frontend package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 497 | Deploy: Upload CVR frontend package | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (getAwsFunctions().copyFilesToS3(s3DeploymentBucket)` | 498 | Deploy: Upload CVR frontend package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Deploy: Upload CVR backend package' when` | 507 | Deploy: Upload CVR backend package | if: vars.J2GHA_WHEN_L507 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!fileExists(backendArtifact))` | 512 | Deploy: Upload CVR backend package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 516 | Deploy: Upload CVR backend package | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (getAwsFunctions().copyFilesToS3(s3DeploymentBucket)` | 517 | Deploy: Upload CVR backend package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Deploy: Upload CVR data update package' when` | 526 | Deploy: Upload CVR data update package | if: vars.J2GHA_WHEN_L526 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!fileExists(dataUpdateArtifact))` | 531 | Deploy: Upload CVR data update package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 535 | Deploy: Upload CVR data update package | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (getAwsFunctions().copyFilesToS3(s3DeploymentBucket)` | 536 | Deploy: Upload CVR data update package | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `checkoutGitRepo` | 548 | Deploy: Terraform CVR | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `decl frontendTfVar = -var lambda_frontend_s3_key=${mani` | 550 | Deploy: Terraform CVR | - | Groovy variable assignment |
| 🔴 manual | `decl backendTfVar = -var lambda_backend_s3_key=${manife` | 551 | Deploy: Terraform CVR | - | Groovy variable assignment |
| 🔴 manual | `decl dataUpdateTfVar = -var lambda_data_update_s3_key=$` | 552 | Deploy: Terraform CVR | - | Groovy variable assignment |
| 🔴 manual | `decl tfLambdaParams = "${frontendTfVar} ${backendTfVar}` | 553 | Deploy: Terraform CVR | - | Groovy variable assignment from a step |
| 🔴 manual | `toString` | 553 | Deploy: Terraform CVR | - | Groovy method / helper call - port logic to a script |
| 🔴 manual | `if (getAwsFunctions().terraformScaffold(
             )` | 554 | Deploy: Terraform CVR | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (isNewVersion['assets'])` | 607 | Deploy: Upload CVR frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 634 | Deploy: Upload CVR frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (getAwsFunctions().copyFilesToS3(s3AssetsBucket, 'd)` | 643 | Deploy: Upload CVR frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (getAwsFunctions().copyFilesToS3(s3AssetsBucket, 'e)` | 648 | Deploy: Upload CVR frontend assets | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `writeJSON` | 661 | Deploy: Manifest | placeholder step | policy step with no deterministic mapping |
| 🔴 manual | `if (!fileExists("${env.WORKSPACE}/manifests/manifest_$)` | 665 | Deploy: Manifest | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (getAwsFunctions().copyFilesToS3("${s3DeploymentBuc)` | 669 | Deploy: Manifest | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `stage 'Load test data to DB' when` | 679 | Load test data to DB | if: vars.J2GHA_WHEN_L679 == 'true' | untranslatable condition: repository variable(s) J2GHA_WHEN_L<line> stand in for it ('true'/'false'); unset, the stage runs only where it would run whatever that condition's value |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 683 | Load test data to DB | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh (
                script: "npm run build:${data)` | 693 | Load test data to DB | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (sh(
                  script: "AWS_REGION=${global)` | 701 | Load test data to DB | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `info` | 718 | Tests | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| 🔴 manual | `if (!repoFunctionsFactory.checkoutGitRepo(
           )` | 720 | Tests | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (fileExists(github.front_end.name))` | 776 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (fileExists(github.cvr_app.name))` | 781 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (fileExists(gitlab.cvr_terraform.name))` | 792 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `if (monitoredEnvironments.contains(params.environment))` | 803 | Declarative: Post Actions | placeholder | condition depends on Groovy runtime state |
| 🔴 manual | `fatal` | 810 | Declarative: Post Actions | placeholder step | unknown step with no deterministic mapping (plugin/shared-library step) |
| ℹ️ info | `checkout: SCM environment (GIT_COMMIT, GIT_BRANCH, GIT_URL)` |  |  | env | Jenkins' git plugin exports them to every step after a checkout, so called scripts may read them; defined at workflow level even when the Jenkinsfile does not |

## Stage graph

```text
pipeline [declarative] agent: none
├── Init  [agent label]
│   ├── Init: Check DB data completion  [when]
│   │   · script, <assign>×2, <if>, log.info, destroyExistingDbTables, isAnyDbTableMissing
│   ├── Init: TF deployment bucket
│   │   · script, wrap, <assign>×5, <decl>×2, getAwsFunctions, <if>×3, failure×3, output.stdout.trim …
│   └── Init: Verify environment  [when]
│       · script, <if>×7, failure×2, dir, <decl>×7, getOutputOrFail×4, getAwsFunctions, log.info×2 …
├── Build  [when; parallel]
│   ├── Build: CVR frontend  [when; agent label]
│   │   · script, dir×2, deleteDir, <if>×2, failure×2, <decl>×2, getRevisionFromArtifactName, log.info …
│   ├── Build: CVR backend  [when; agent label]
│   │   · script, dir×2, deleteDir, <if>×2, failure×2, <decl>×2, getRevisionFromArtifactName, log.info …
│   ├── Build: frontend assets  [agent label]
│   │   · script, dir×3, deleteDir, <if>×3, failure×3, <decl>, <assign>, readFile …
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

- **`when`** (🔴 7 manual, 🟡 6 approximated): GHA == is case-insensitive; changeset -> paths filters (workflow level) or a paths-filter action (step level).
  - Jenkins: [syntax #when](https://www.jenkins.io/doc/book/pipeline/syntax/#when)
  - GitHub Actions: [control-jobs-with-conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions) · [expressions](https://docs.github.com/en/actions/reference/workflows-and-actions/expressions) · [workflow-syntax #onpushpull_requestpull_request_targetpathspaths-ignore](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore)
- **`scripted`** (🔴 73 manual, 🟡 33 approximated): Groovy control flow -> expressions/if, matrix, or a script step; anything dynamic needs redesign.
  - Jenkins: [syntax #scripted-pipeline](https://www.jenkins.io/doc/book/pipeline/syntax/#scripted-pipeline) · [cps-method-mismatches](https://www.jenkins.io/doc/book/pipeline/cps-method-mismatches/)
  - GitHub Actions: [migrate-from-jenkins](https://docs.github.com/en/actions/tutorials/migrate-to-github-actions/manual-migrations/migrate-from-jenkins)
- **`timeout`** (🟡 1 approximated)
  - Jenkins: [step `timeout`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idtimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idtimeout-minutes) · [workflow-syntax #jobsjob_idstepstimeout-minutes](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepstimeout-minutes)
- **`agent`** (🟡 7 approximated): label expressions -> runs-on labels/groups; agent { docker } -> jobs.<id>.container (runs as root); a stage-level agent forces a separate job (workspace is not shared).
  - Jenkins: [syntax #agent](https://www.jenkins.io/doc/book/pipeline/syntax/#agent)
  - GitHub Actions: [workflow-syntax #jobsjob_idruns-on](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idruns-on) · [choose-the-runner-for-a-job](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job) · [run-jobs-in-a-container](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/run-jobs-in-a-container)
- **`sh`** (🟡 2 approximated): returnStdout -> write to $GITHUB_OUTPUT and read steps.<id>.outputs.
  - Jenkins: [step `sh`](https://www.jenkins.io/doc/pipeline/steps/)
  - GitHub Actions: [workflow-syntax #jobsjob_idstepsrun](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsrun) · [workflow-syntax #jobsjob_idstepsshell](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)
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
