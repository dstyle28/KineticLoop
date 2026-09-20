---
name: db-transaction-reviewer
description: Review or implement PostgreSQL transaction, locking, idempotency, lease/fencing, outbox and authorization guard code for KineticLoop.
---
1. Map the change to T1-T8 and the frozen lock order.
2. Verify SafetyRegistry shared/exclusive coordination before user coordination where required.
3. Keep external/model/network work outside coordination transactions.
4. Verify idempotency keys and natural uniqueness cannot double-apply after ACK loss.
5. For leases/fencing, prove old workers lose commit authority.
6. For call ledger, prove DISPATCH_INTENT is persisted before the physical request and unknown outcomes do not refund budget.
7. Write/require real PostgreSQL concurrency tests for cross-row/cross-transaction guarantees; unit mocks are insufficient.
