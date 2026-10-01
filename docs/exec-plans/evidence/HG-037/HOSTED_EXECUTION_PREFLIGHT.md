# HG037 hosted execution feasibility correction

Coordinator preflight identified a real gap at PR69 head 67c03d1. Independent reads of the protected-base/current `.github/workflows/ci.yml` and `db.yml` confirm that neither executes the exact `uv run pytest -q -p no:cacheprovider`, accepts arbitrary hosted commands, or exposes workflow_dispatch/workflow_call inputs. The former five-path scope and workflow prohibition therefore could not satisfy KL074's required hosted full-suite evidence.

The correction adds only the future `.github/workflows/kl074-readiness.yml` to KL074's implementation scope. HG037 does not create that live workflow or modify either existing workflow. The proposal in this evidence directory specifies the exact bytes authorized by the source guard, a same-repository `codex/kl074-` PR entrypoint available before KL074 merge, no inputs, trusted head-SHA environment values, explicit checkout of that SHA, locked uv, and one fresh ubuntu-latest VM with a bounded local-daemon preflight. Coldstart and exact complete-suite steps preserve exit status through pipefail, time bounds and raw logs. Artifact upload runs for failures as well as successes. No secrets, token permission expansion, self-hosted/remote daemon, test skips or existing gate replacement is allowed.

A workflow_dispatch-only design would remain unavailable before the new workflow reaches the default branch. GitHub documents the default-branch condition for manual dispatch and head-SHA checkout for PR tests. This proposal uses the supported PR event instead. It is a prospective implementation contract, not evidence that a KL074 workflow or its checks have already run.

Future KL074 must open a draft or ordinary PR from the declared prefix after committing its implementation plus the new workflow. Retain the actual run/job URL, event/head SHA, run ID/attempt and artifact ID/digest; download all raw artifacts into the task evidence directory before expiry and commit them before final result/review. Check hosted-provenance and log SHA against tested_commit and verify both exact commands and actual oracles. A skipped/missing job, incomplete artifact, failure, unavailable actual-image proof or mismatch is NOT_RUN/FAIL, never PASS. Existing normal CI/gates must also pass independently at the final reviewed head.

Primary references, retrieved during correction:

- [GitHub workflow triggers](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
- [GitHub PR events and checkout](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub hosted runner isolation](https://docs.github.com/en/enterprise-cloud%40latest/actions/reference/runners/github-hosted-runners)
- [Docker contexts](https://docs.docker.com/engine/manage-resources/contexts/)

Manual dispatch, hosted-runner and Docker-context facts here are paraphrased reference support, not deployed-image or future execution PASS evidence. The prior GENERAL/DB reviews remain valid only for their older SHA and are preserved as historical evidence; this substantive correction requires fresh checks and GENERAL/DB_CONCURRENCY/SECURITY_DATA_BOUNDARY reviews.
