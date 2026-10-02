# Superseded development round at 18aa599

Initial immutable round 18aa5995c5e44cd22b0c55384648a03ab5bf16eb passed 241 unit,
lint, typecheck, validation, integration and scope/frozen checks. Focused 130 cases
returned 129 PASS / 1 FAIL: the old pre-corrective real-revision test expected a
KL028/029 integration error; new exact 17-task membership correctly denies earlier.
The complete failed focused raw capture is retained and is not selected PASS evidence.
The concurrent full harness run was interrupted as incomplete/NOT_RUN after this
known failure. It produced no completed PASS evidence and is not selected.

Refined only corresponding M3 fixture expectations and direct omission proofs for
KL028/029/KL080 integrations. Narrowly made the read-only audited prior-deployment
fixture route explicit in the new prospective KL080 packet/oracle, pinned its updated
hash and added FEASIBILITY to context. No runtime, test fixture implementation,
historical artifact, immutable row or frozen authority changed. Final selected checks
must execute anew at the next immutable implementation SHA; no 18aa599 evidence is
promoted to final PASS, and reviewer evidence binds the later result revision.

## Incomplete round at 6bf24b3

After self-review found that a changed-files-only fixture guard could omit one of the
four mandatory older corrections, strengthened the KL080 selected-task gate to
require all four paths in addition to exact six-literal content. Added a negative
omission test. This fixes enforceability, not runtime or fixture implementation.
Focused/full harness runs at 6bf24b3448c58727d09904fd6dad41059e4b1e65 were interrupted
incomplete/NOT_RUN. Their partial streamed .log files are retained byte-for-byte;
neither supplies selected PASS evidence. The completed 241-unit/lint/type/validation/
integration/scope/diff captures from this round are historical diagnostics only.
Final required checks execute again at the next immutable SHA with this guard.

## Completed superseded round at d6603c6

At d6603c6a4280b58fef634cdd7c3da1dfbc99b2bc, all 134 focused source/M3 tests and
241 unit tests passed. Full harness returned 904 PASS / 20 FAIL; every failure was
packet:KL-080. Generic ValidatorTests copy only delivery-manifest files, so the new
packet needed its own derived SHA/byte-count manifest entry. A read-only mocked
manifest diagnostic made three representative failures pass without validator changes.
Append only the new packet's derived hash entry and a source-scope regression test
requiring it. Do not modify test_validator.py or relax its existing gates. Full raw
failed output is retained, not selected as final PASS.

The final focused capture runs the source scope/pinning/negative/delivery tests.
The full harness capture includes all M3 feasibility/provenance/omission cases;
that mandatory full execution supplies final M3 regression evidence without running
the entire expensive M3 suite twice. Every required check reruns at the next immutable
SHA. Superseded rounds, including successful earlier M3/unit outputs, remain diagnostic
context only; selected PASS references all bind the final tested SHA.
