# HG-046 mandatory merge enforcement extension

The user approved closing mandatory-test, trusted-execution, protected-master and
merge-freshness gaps before merging PR #90. This extends the same unmerged CI
concern. PR #90 is now a draft; the earlier implementation/result/reviews are
historical development evidence for this unmerged task, not approval of these
new changes. A new tested/result revision and all three reviews are required.

## Verified setup state

- Master ruleset 24391081 now explicitly targets `refs/heads/master`, with no
  bypass actors, PR-only changes, no deletion/force push, and strict required
  `quality` and `merge-gate` checks from GitHub Actions App 15368.
- Before/proposed/applied/effective API snapshots are in `hardening-setup/`.
- This is PARTIAL enforcement. It does not authenticate local DB execution, and
  a candidate Actions workflow can share the GitHub Actions identity.
- Only dstyle28 is currently a repository collaborator; PR90 has that author.
  We have not imposed an impossible self-approval requirement. The dedicated
  controller must enforce the existing SHA-bound independent review contract.

## Remaining implementation and activation

1. Install an independently reviewed, hash-pinned controller outside the candidate
   checkout. Candidate code cannot choose the image, orchestration, plugin,
   verdict parser, publication code, or App credentials.
2. Require a conservative trusted full-diff decision. Unknown paths, execution
   policy, tests, dependencies, authority changes, executable modes, symlinks and
   submodules require DB. Preserve both sides of renames. Only narrow inert
   documentation/results may be exempt. Exemption is an explicit validated
   success decision; never a skipped/neutral check.
3. Execute trusted quality/harness checks for every PR; do not accept candidate
   Actions status or uploaded JSON as proof. Execute full DB when required.
   Existing result and review evidence remain necessary, but do not substitute
   for controller-observed execution and cleanup.
4. Bind the receipt to repository ID, PR number, live master SHA, PR head/tree,
   controller/image identity, observed commands/exits, raw hashes and cleanup.
   Require live master to be an ancestor of head, then re-read both refs before
   publishing. A changed base/head, missing proof or failed cleanup cannot pass.
5. Create/install a private dedicated GitHub App on KineticLoop only, with checks
   write, contents read and pull requests read. No contents/admin write, OAuth
   delegation or public webhook. Store its private key outside Git and workers.
6. Add `local-db-gate` to master required checks bound to that exact App ID. No
   bypass and strict base freshness remain required. Demonstrate missing,
   failed, wrong-App and stale-head/base proof cannot permit merging. Do not
   claim activation until the effective branch rules are read back and tested.
7. Independent GENERAL/DB_CONCURRENCY/SECURITY_DATA_BOUNDARY reviews must pass the
   new result SHA; only review records may follow. Keep PR90 unmerged throughout.

## Trust boundary

This desktop executor admits trusted independently reviewed project code only.
A privileged nested Docker container is not a sandbox for hostile public PRs;
no permanent public self-hosted runner will be installed. Untrusted automatic
execution requires a separate disposable VM/worker without signer credentials,
host shares or other workloads. Candidate test/config changes need independent
exact-revision review; merely signing candidate-produced JUnit cannot establish
that meaningful tests ran. A compromised administrator or signing key is outside
this mechanism's guarantee, and passing tests never prove the absence of all bugs.

## Current activation state

App5169734 is installed as167371213 on selected repository1377771702 only.
The user generated the private key; its public fingerprint matches GitHub and
installation authentication confirms only KineticLoop with the approved scopes.
The key is owner-only outside Git and workers; no token/key is included here.

Master now additionally requires `local-db-gate` from App5169734, preserving strict
freshness, existing required checks and no bypass. Effective API readback is in
hardening-setup. This blocks merging until the trusted executor publishes success.
Controller validation, a new result and fresh independent reviews are still
pending. No success has been fabricated or published, and PR90 stays draft.
