# Third-party notices

The project is MIT-licensed ([LICENSE.md](LICENSE.md)), except for the example corpus. Each `examples/0NN/` directory
(other than the hand-written `examples/000`) holds a Jenkinsfile copied verbatim from a public repository, together with
files that contain or are derived from it: the `Jenkinsfile.localized` copies and logs under `runs/`, the converted
workflow and model under `gha/`, and the analysis under `analysis/`. Each twin in `examples/1NN/` is an edited copy of
its original's Jenkinsfile (the edits are listed in its `LOCAL.md`) and has the same kind of derived files.

All of these stay under the licence of the repository the Jenkinsfile came from. A copy of that licence, taken at the
cited commit, is in the example's `LICENSE.upstream`, and the repository's `NOTICE` file, where it has one, in
`NOTICE.upstream`. The citation (repository, path and commit) is at the top of the example's `README.md` and in
`source.json`.

| Example | Twin | Source repository | Commit | Licence | Notice |
|---|---|---|---|---|---|
| [001](examples/001/) | [101](examples/101/) | [apache/couchdb](https://github.com/apache/couchdb) | [`d072d90`](https://github.com/apache/couchdb/tree/d072d90125e39c41b8e4947a89691c6e5ad23c77) | Apache-2.0 ([copy](examples/001/LICENSE.upstream)) | [NOTICE](examples/001/NOTICE.upstream) |
| [002](examples/002/) | [102](examples/102/) | [jenkinsci/jenkins](https://github.com/jenkinsci/jenkins) | [`d076aeb`](https://github.com/jenkinsci/jenkins/tree/d076aeb66b68af42c61568676bf29dba9ae3cee8) | MIT ([copy](examples/002/LICENSE.upstream)) | - |
| [003](examples/003/) | [103](examples/103/) | [frankarobotics/franka_description](https://github.com/frankarobotics/franka_description) | [`37c4be2`](https://github.com/frankarobotics/franka_description/tree/37c4be2ce36ae6d354339509a3d324063fc99968) | Apache-2.0 ([copy](examples/003/LICENSE.upstream)) | [NOTICE](examples/003/NOTICE.upstream) |
| [004](examples/004/) | [104](examples/104/) | [EclipseFdn/open-vsx.org](https://github.com/EclipseFdn/open-vsx.org) | [`4d48d2d`](https://github.com/EclipseFdn/open-vsx.org/tree/4d48d2d9d80c31817c6026a1b269589601f34de6) | EPL-2.0 ([copy](examples/004/LICENSE.upstream)) | - |
| [005](examples/005/) | - | [opensearch-project/opensearch-migrations](https://github.com/opensearch-project/opensearch-migrations) | [`8fc52e4`](https://github.com/opensearch-project/opensearch-migrations/tree/8fc52e4e4da5af545d7f33a88ffdbf3085e128bb) | Apache-2.0 ([copy](examples/005/LICENSE.upstream)) | [NOTICE](examples/005/NOTICE.upstream) |
| [006](examples/006/) | [106](examples/106/) | [fabiojose/platform-as-code-example](https://github.com/fabiojose/platform-as-code-example) | [`ee4cfb0`](https://github.com/fabiojose/platform-as-code-example/tree/ee4cfb0dfbbce20115f98cb2be4d486747549b59) | Apache-2.0 ([copy](examples/006/LICENSE.upstream)) | - |
| [007](examples/007/) | [107](examples/107/) | [oracle/weblogic-kubernetes-operator](https://github.com/oracle/weblogic-kubernetes-operator) | [`a102837`](https://github.com/oracle/weblogic-kubernetes-operator/tree/a1028378bd770495180ddabca31e8d1399be7900) | UPL-1.0 ([copy](examples/007/LICENSE.upstream)) | - |
| [008](examples/008/) | [108](examples/108/) | [h2oai/h2o-3](https://github.com/h2oai/h2o-3) | [`f26129f`](https://github.com/h2oai/h2o-3/tree/f26129ff5c9c3646573f98af753c8cd227462a7c) | Apache-2.0 ([copy](examples/008/LICENSE.upstream)) | - |
| [009](examples/009/) | [109](examples/109/) | [TheHPXProject/hpx](https://github.com/TheHPXProject/hpx) | [`0aa9f24`](https://github.com/TheHPXProject/hpx/tree/0aa9f24db04a24dbb87746b6c7210fa65089b769) | BSL-1.0 ([copy](examples/009/LICENSE.upstream)) | - |
| [010](examples/010/) | - | [apicollective/apibuilder](https://github.com/apicollective/apibuilder) | [`11b4b94`](https://github.com/apicollective/apibuilder/tree/11b4b94e5fe33581d3d7de46c4002dbffcb3afc6) | MIT ([copy](examples/010/LICENSE.upstream)) | - |
| [011](examples/011/) | [111](examples/111/) | [oneanupam/jenkins-shared-libs](https://github.com/oneanupam/jenkins-shared-libs) | [`c4b839d`](https://github.com/oneanupam/jenkins-shared-libs/tree/c4b839ddc8934f978a3f5c336dd144bfaf5fc464) | MIT ([copy](examples/011/LICENSE.upstream)) | - |
| [012](examples/012/) | [112](examples/112/) | [owen2016/devops-practices](https://github.com/owen2016/devops-practices) | [`c04fb6c`](https://github.com/owen2016/devops-practices/tree/c04fb6c34767617e62b6e3d4b55903be74fd3c2a) | MIT ([copy](examples/012/LICENSE.upstream)) | - |
| [013](examples/013/) | - | [EclipseNebula/nebula](https://github.com/EclipseNebula/nebula) | [`811efd8`](https://github.com/EclipseNebula/nebula/tree/811efd82360cc40cef0763362c38651a848a6d12) | EPL-2.0 ([copy](examples/013/LICENSE.upstream)) | - |
| [014](examples/014/) | [114](examples/114/) | [The-OpenROAD-Project/OpenLane](https://github.com/The-OpenROAD-Project/OpenLane) | [`32dc185`](https://github.com/The-OpenROAD-Project/OpenLane/tree/32dc185225c45f1a3d3756f231b4cbdfaac2f68c) | Apache-2.0 ([copy](examples/014/LICENSE.upstream)) | - |
| [015](examples/015/) | [115](examples/115/) | [IBM/cloudant-node-sdk](https://github.com/IBM/cloudant-node-sdk) | [`e775c33`](https://github.com/IBM/cloudant-node-sdk/tree/e775c33e2de8b8245290200c3e36e52208b09521) | Apache-2.0 ([copy](examples/015/LICENSE.upstream)) | - |
| [016](examples/016/) | [116](examples/116/) | [dvsa/cvs-auto-mobile-app-retired](https://github.com/dvsa/cvs-auto-mobile-app-retired) | [`bf150f6`](https://github.com/dvsa/cvs-auto-mobile-app-retired/tree/bf150f606a385a8ed5eacc00070a988c675dd815) | MIT ([copy](examples/016/LICENSE.upstream)) | - |
| [017](examples/017/) | [117](examples/117/) | [dvsa/recalls-pipeline](https://github.com/dvsa/recalls-pipeline) | [`356eb91`](https://github.com/dvsa/recalls-pipeline/tree/356eb91d1ffcaf98f2e5a39ed57bd2a5e7f3ce08) | MIT ([copy](examples/017/LICENSE.upstream)) | - |
| [018](examples/018/) | [118](examples/118/) | [dvsa/olcs-ci](https://github.com/dvsa/olcs-ci) | [`e7e9913`](https://github.com/dvsa/olcs-ci/tree/e7e9913a6090bd18f16fb85eb98b7b5f0dbfa87c) | MIT ([copy](examples/018/LICENSE.upstream)) | - |
| [019](examples/019/) | [119](examples/119/) | [dvsa/dvsa-mobile-pipeline](https://github.com/dvsa/dvsa-mobile-pipeline) | [`1827396`](https://github.com/dvsa/dvsa-mobile-pipeline/tree/1827396f6752465cf0a91a3bcf2ea4bb021c2d3d) | MIT ([copy](examples/019/LICENSE.upstream)) | - |
| [020](examples/020/) | - | [dvsa/mes-beta-sandbox](https://github.com/dvsa/mes-beta-sandbox) | [`6e6a4b0`](https://github.com/dvsa/mes-beta-sandbox/tree/6e6a4b0b53dadc4bdfb451bbc1899d8af5b17532) | MIT ([copy](examples/020/LICENSE.upstream)) | - |

This list is a record of where the files came from, not legal advice.
