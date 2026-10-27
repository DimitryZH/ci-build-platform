# Online Shop build producer

The producer extends the existing manual runner request -> Cloud Run controller ->
GCE ephemeral runner -> Docker Hub path. AML owns inventory, Dockerfiles, input
validation and planning. The sample still builds `application/` and publishes
`ci-artifact:latest`; Online Shop never uses `latest`.

## Prerequisites and trust

Use the configured controller and runner infrastructure, existing Actions secrets
`CLOUD_RUN_CONTROLLER_URL`, `CLOUD_RUN_TOKEN`, `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN`, and Docker Hub push permission for the selected existing
repositories. Public Docker Hub pull/token endpoints must be reachable. Runner
requires Python 3.10+, Git and Docker with Linux/amd64 support. The updated startup
template installs Python, bounds idle/active runner lifetime to 90 minutes and
stops the VM through an EXIT trap, including failure paths. Existing provisioned
templates are not automatically updated by this PR; deployment of that template
through the normal reviewed infrastructure process is a prerequisite for those
cleanup improvements. No Terraform deployment was performed for implementation.
The Online Shop job installs Buildx with `docker/setup-buildx-action` and uses
`docker buildx build --load` for upstream BuildKit cache mounts. The single-platform
result is loaded into the local Docker store before the explicit push.

Dispatch only reviewed requests from the default branch. The selected AML
revision's Python planner and Dockerfiles execute code; a commit hash establishes
identity, not trustworthiness. Source repository and workload are fixed to
`https://github.com/DimitryZH/application-modernization-lab` and
`workloads/online-shop`. No source inventory is duplicated in this repository.

## Dispatch and handoff

After this change reaches the default branch through normal review:

```bash
gh workflow run request-runner.yml --ref main \
  -f build_kind=online-shop \
  -f source_revision=87c39c498ebf4b7f9b7347f7b317aae27a0630f3 \
  -f components=frontend -f platform=linux/amd64 -f build_arguments='[]'
```

For another build, change the full lowercase SHA and explicit space-separated
component IDs. Optional arguments are a JSON string array, e.g.
`["frontend.SKAFFOLD_GO_GCFLAGS=all=-N -l"]`. Argument values retain spaces;
the executor uses subprocess argument vectors without shell evaluation. AML
validates allowed names/values and unknown/duplicate selections. `SOURCE_REVISION`
must equal the selected SHA. Leave AML fields empty and choose `sample` for the
original sample. Do not select all eleven components for issue #1 validation.

Validation and upstream planning occur on a hosted runner before requesting
capacity. The immutable upload-artifact v4 artifact
`build-request-<request-run-id>-<request-attempt>` carries `request.json` and the
plan. The consumer downloads that exact name from the triggering run ID, never
the latest run. A hosted gate checks repository, workflow path, dispatch event,
success, default branch, SHA, run ID and attempt before scheduling the ephemeral
job. It forwards the validated data in an artifact bound to the current build run
and attempt. The ephemeral job repeats correlation checks and recomputes the
plan, contract hash and destinations from the selected AML revision.

Missing artifacts or previous-attempt/mismatched envelopes fail closed. Retrying a
request creates a new attempt artifact; retrying a build uses the original
request identity and a new build attempt. Overlapping requests cannot exchange
inputs. Capacity remains the existing singleton VM, so operators should dispatch
one request at a time and wait for VM shutdown before repeating; this change does
not add a capacity scheduler or guarantee simultaneous runner availability.

GitHub's [workflow_run documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_run)
specifies default-branch workflow execution and default-branch HEAD for
`GITHUB_SHA`. Dispatch inputs are not automatically propagated. Consequently
branch-only testing cannot validate this new chain: do not merge or check out
unreviewed request code in the privileged consumer to bypass that behavior.
Each request/build reference records the actual `GITHUB_SHA` tooling revision,
`GITHUB_WORKFLOW_SHA` workflow revision, workflow ref, run URL/ID and attempt.
Those revisions are independent of the AML source SHA. Consumer checkout is
explicitly pinned to its own `github.sha`, not the request head or mutable main.

## Source, publication and verification

Each phase uses a new isolated detached checkout with `core.autocrlf=false`.
Every tracked workload file, including planner/contract/mapping, must equal its
Git blob bytes; ignored/untracked artifacts and nonregular workload files fail.
The same-revision planner supplies contexts, Dockerfiles, arguments, preparation
and input hashes. Paths are workload-relative; COPY inputs are context-relative.
Consumed bytes and Dockerfile hashes are checked again. No ordinary host code
generation occurs; a null target omits Docker's target option. Plans/logs/results
live outside source and build contexts.

Destinations come from `images.lock.json` at the requested revision and must be
under `docker.io/dmitryzhuravlev/online-shop-*`. Frontend resolves to
`docker.io/dmitryzhuravlev/online-shop-frontend`. Historical mapping digests are
not reused as evidence for these builds.

Tags use `sha-<full-source-sha>-q<request-id>a<request-attempt>-b<build-id>a<build-attempt>`.
Before building, an authenticated public registry read checks that the identity
is unused. Only HTTP 404 counts as absent; auth/rate-limit/network failures stop
publication. An existing tag fails instead of being replaced. Unique Actions
run/attempt identities prevent concurrent producer collisions. Docker Hub does
not provide compare-and-set tag publication here: out-of-band writers with push
access must not race these reserved tags. Registry-side immutable tag policies
can further restrict those writers.

After push, the producer hashes raw registry manifest bytes and checks
`Docker-Content-Digest`, retrieves the manifest by digest, pulls the image by that
digest and inspects Linux/amd64 and the full OCI revision label. Only single image
manifests are supported; unexpected indexes fail verification. Config digest,
local image ID and manifest digest are distinct fields, even when config and
local IDs match. No success record is emitted before all these checks pass.

## Build-result v1 and evidence

`ci/online_shop.py` writes one `<component>.result.json` per verified publication:

| Field | Meaning |
| --- | --- |
| `buildResultVersion`, `status`, `componentId` | `1`, `published-and-verified`, explicit component ID |
| `sourceRepository`, `sourceRevision`, `workloadPath` | Fixed AML source identity and full selected SHA |
| `contract` | Version, repository-relative path and SHA-256 of raw contract bytes |
| `planSha256` | SHA-256 of UTF-8 `json.dumps(plan, sort_keys=True, indent=2) + '\n'` |
| `buildContext`, `dockerfile`, `target`, `effectiveArguments`, `platform` | Effective plan settings, workload-relative paths |
| `request`, `build` | CI repository, run ID/URL, attempt, tooling revision, workflow revision/ref |
| `image` | Repository, tag, verified registry `manifestDigest`, `indexDigest: null`, local image/config IDs |

Results are producer metadata, not release approval, signatures or cryptographically
verified provenance. Mutable base tags, OS/package repositories and incomplete
dependency locking remain upstream limitations. Docker layer/compiler caches are
allowed; byte-identical or fully locked reproducibility is not claimed.

`online-shop-evidence-<build-id>-<attempt>` retains the plan, successful component
results and Docker logs for 90 days. A caught failure writes a separate
`failure.json`; earlier verified components in a multi-selection remain valid,
but no failed component gets a success result. Failed push/verification may leave
a tag in the registry without a success record. Keep it for diagnosis; retry with
a new attempt identity rather than deleting or overwriting it. Request artifacts
expire after 30 days, so very late build reruns must create a new request.

Copy the actual sanitized request, plan and result files into a new
`docs/evidence/issue-1/<build-id>-<attempt>/` record through a focused reviewed
commit after live validation. Include run URLs, actual executed CI SHAs, cleanup
observations with UTC times and limitations. Review raw logs before publishing;
exclude credentials, controller endpoints and private infrastructure identifiers.
The initial durable pending record is `docs/evidence/issue-1/status.json`.

## Live validation and cleanup

1. After merge, verify prerequisites and default-branch workflow revision, then
   dispatch the pinned SHA with frontend only using the command above.
2. Capture the request URL/attempt and the resulting build URL/attempt. Download
   their exact artifacts. Verify metadata identity against run details and
   independently pull `repository@manifestDigest`; inspect platform/revision.
3. Observe runner deregistration via GitHub Actions runner settings/API. Separately
   check VM status `TERMINATED` using authorized GCP access and inspect serial or
   shutdown logs. Record sanitized timestamps/observations; Actions success alone
   does not establish VM shutdown. The VM resource persists by design.
4. If the consumer gate rejects a handoff or capacity never registers, inspect
   restricted controller/serial logs. The updated startup script bounds orphan
   lifetime; older deployed templates may require normal operator shutdown.
   Cancellation, forced termination or loss of the runner can interrupt artifact
   upload; inspect registry state before retrying and record the gap.
5. Commit sanitized durable evidence and explicitly reassess each live acceptance
   item. Keep the issue open until publication, retrieval and cleanup are verified.

Offline tests: `python -m unittest discover -s tests -v`. They fake Docker/registry
operations and use disposable local Git repositories, with no cloud provisioning.
