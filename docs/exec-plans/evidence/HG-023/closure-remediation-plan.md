# HG-023 closure evidence correction

This is a work plan, not PASS evidence. The protected project plan defines four
M2 exits. The initial HG-023 implementation omitted them and must not be merged
in that state.

| Canonical exit | Required evidence before closure |
| --- | --- |
| schema rebuild from zero | Fresh complete migration/DB regression on the integrated repair revision, including empty upgrade, deterministic rebuild and latest single head; historical KL-013/KL-072 results remain supporting evidence. |
| migration dependency graph documented | KL-010 topology document and acyclic/authority-order checks bound through its validated integration record; verify the integrated migration chain still follows that graph. |
| no writer can bypass owner/subject guard | Fresh complete DB and transaction suites, preserving KL-012 direct-SQL denial, KL-015 owner/subject checks, KL-017 isolation, and KL-072 definer/role boundary coverage. |
| G-SHADOW and G-REGISTRY closed before affected contracts merge | Review historical KL-014 shadow/test contract evidence and KL-016/KL-072 registry evidence against the actual merge ordering of affected contracts; record exact revisions and checks, not a generic regression assertion. |

Closure must also retain the exact active M2 integration set, validate the M1
prerequisite at the evaluated revision, reject unknown or misnamed closure files,
and bind fresh execution records to committed raw logs and machine-readable test
reports. A JSON field saying PASS is insufficient. All expected commands must exit
zero, with nonempty test coverage and no failed/skipped required tests. Evidence
freshness must inspect every intervening commit, including changes later reverted.

The historical logs ending in 32455ed are manually transcribed summaries. Their
full SHA was corrected to 32455ed4e1af93475e5598d254f95ada1a80cec0. The earlier
112-test run preceded the implementation commit and is exploratory only. It must
not be represented as a run on that SHA. Fresh closure evidence will supersede
these summaries without relabeling the failed run as PASS.

Prerequisite: user-approved HG-024/KL-073 combined emergency change must pass
independent review and all CI checks and merge normally before M2 can close.
