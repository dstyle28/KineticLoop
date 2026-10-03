# Preserved failed final App gate

Exact head `8a78241e9b752247c3c4f4a43c4fe54bad72ef6c` failed its Linux harness: 1304 passed, two fixture-setup
E2BIG errors from oversized automatically generated pytest parameter IDs. The run
stopped before authority/full DB. Container and volume cleanup both succeeded.
These lossless captures preserve the original raw logs, JUnit, execution observer,
worker/controller receipts and published failure. They are historical FAIL, never
selected task PASS or full DB PASS. The artifact-capture command is explicitly a
preservation operation; actual executed argv/exit/durations are in the receipt.

- `dependency_sync.log`: `docs/exec-plans/evidence/HG-047/development-8a78241/dependency_sync-log.json`
- `harness.log`: `docs/exec-plans/evidence/HG-047/development-8a78241/harness-log.json`
- `image_build.log`: `docs/exec-plans/evidence/HG-047/development-8a78241/image_build-log.json`
- `lint.log`: `docs/exec-plans/evidence/HG-047/development-8a78241/lint-log.json`
- `published-check.json`: `docs/exec-plans/evidence/HG-047/development-8a78241/published-check-json.json`
- `receipt.json`: `docs/exec-plans/evidence/HG-047/development-8a78241/receipt-json.json`
- `typecheck.log`: `docs/exec-plans/evidence/HG-047/development-8a78241/typecheck-log.json`
- `unit.log`: `docs/exec-plans/evidence/HG-047/development-8a78241/unit-log.json`
- `worker/harness.xml`: `docs/exec-plans/evidence/HG-047/development-8a78241/worker--harness-xml.json`
- `worker/run/execution.json`: `docs/exec-plans/evidence/HG-047/development-8a78241/worker--run--execution-json.json`
- `worker/unit.xml`: `docs/exec-plans/evidence/HG-047/development-8a78241/worker--unit-xml.json`
- `worker-receipt.json`: `docs/exec-plans/evidence/HG-047/development-8a78241/worker-receipt-json.json`
