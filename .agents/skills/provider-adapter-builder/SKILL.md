---
name: provider-adapter-builder
description: Build Hevy, HealthKit, Oura or import adapters under the KineticLoop Integration Spec without letting provider data bypass Evidence Admission.
---
1. Read the provider section in `12_KineticLoop_Integration_Spec_v0.1.md` and its INT-A requirements.
2. Emit immutable provider evidence with stable source identity, known/observed time, provenance and revision/deletion semantics.
3. Never write progression, readiness verdicts, Program state, approvals or authorization directly.
4. Preserve partial permissions/missing-data semantics; missing is not zero.
5. Reconcile duplicate underlying events instead of applying universal source overwrite priority.
6. Wearable workout labels never invent strength exercise/sets/reps/load/RPE.
7. Implement outage, late-data, correction and idempotency fixtures before declaring the adapter ready.
