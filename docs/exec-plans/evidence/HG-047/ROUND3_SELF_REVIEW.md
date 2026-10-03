# HG-047 Linux pytest ID correction self-review

Source `f29ffa97d9057eacc4bda7ad593b843c9c52c5a2`, protected base `391c9198fa8ec647e377a0572700bc7568468c85`. This is author self-review.
The final App gate at `8a78241e9b752247c3c4f4a43c4fe54bad72ef6c`
failed with 1304 passing harness cases and two E2BIG fixture setup errors.
Its exact raw logs, JUnit, observer data and receipts remain losslessly preserved
under `development-8a78241/`; this failure never becomes PASS evidence.
Round2 reviews of b737094 and all earlier evidence remain in committed history.

The only subsequent code change adds stable concise IDs to the four bounded
decoder cases and six bulk/duplicate-metadata budget cases. Corrected node IDs are
at most 105 bytes. AST comparison after removing only parametrization `ids`
keywords proves all data, test bodies and assertions unchanged; collection still
contains all 1306 cases. Historical planning-test IDs still reach 272839 bytes;
they are outside this correction and passed the full Linux run unchanged.
No decoder, validator, runtime, gate, frozen baseline, CI classifier or workflow
changed in this correction. General review G-01 about ordinary duplicate-key
Unicode JSON remains a prospective nonblocking followup, outside this fix.

The coordinator-authorized installed helper was read before use; every asset was
verified byte-for-byte against reviewed release b737094. Its code-only run_worker
used full_db=False/test_only=True and a fresh UUID container/data volume. The
worker received an exact committed Git bundle, trusted installed validator and
decoder, no host directory/socket mount and no signer data. No App object, signer
configuration, admission or publication was used. Linux ARM64 image identity,
command plan, complete argv, raw stdout, JUnit, observer IDs, exact exit codes and
monotonic durations are captured under `docs/exec-plans/evidence/HG-047/round3-f29ffa9/`. The owned container and volume
were both removed. The retained image cache is expected.

All 1306 harness and 241 unit cases passed without skipped cases or errors. Lint,
typecheck and authority passed inside Linux. Exact-source scope/diff, collection
and bounded benchmark checks also passed. Raw evidence remains reconstructable;
metadata summaries do not replace stdout or JUnit. This is
DEVELOPMENT_NO_PUBLICATION and is not the mandatory final local-db-gate, full DB,
independent review, M3, product or release PASS. All three fresh reviews and the
coordinator's final reviewed-head full DB/App run remain required.
