The selected final task executions are listed in `final-checks.json`. All run at
`d6bfb285087456a1a43d6c6b856a07eee4e1746d` using the exact packet commands.

`checks.json` is the serial driver checkpoint for the namespace/pure, all own DB,
validation and unit commands. The DB selectors remain serialized on the task's
exact owned namespace. The independent harness, lint and type commands use
`*.parallel.log`, their JUnit where relevant, and `*.parallel.json`. These runs
are independent of the database lifecycle and use the same immutable SHA.

After the serial driver had finished all own DB and repository unit checks, it
started a redundant harness run. Only that duplicate harness and its driver were
interrupted. Its incomplete diagnostics remain outside the repository under
`/private/tmp/kl080-duplicate-harness-d6bfb28`; the independent actual full harness
execution supplies the selected final result. No implementation changed between
these runs, and no mandatory failure was relabeled PASS.

The exact selector collection logs/manifests and JUnit bind executed counts to
node IDs with no skip/xfail/zero collection. `source_suite_dc.log` contains all
raw owner rows, guard traces and 106 matching namespace/cleanup witnesses;
`witness-index.json` provides their line numbers. The two final FAIL commands
both expose `test_owner_trajectories[legacy]`; its positive oracle remains unsatisfied.
`legacy-scope-blocker.json` separates the actual earlier guard failure from the
later synthetic certificate mismatch found by static inspection.
