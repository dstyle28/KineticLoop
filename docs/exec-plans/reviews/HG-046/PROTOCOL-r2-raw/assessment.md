# HG-046 independent PROTOCOL r2

Reviewed head: `5182feb0ad33319336efd913f63bf8c01c74b6a7`.
Protected base: `26906bd7f4444914c228e98377f2b164fee0dd5d`.
Selected tested source: `58de0f7dfbf39947f2c2c1852cc927823e79b4c3`.

CHANGES_REQUIRED: `compact_evidence.envelope` returns plain bytes before JSON
parsing when UTF-8 marker/storage-key/escape bytes are absent. UTF-16/32 JSON
storage manifests therefore avoid envelope validation and missing-payload checks.
The SECURITY reviewer reported the executable reproduction; this review
independently confirms the blocking control flow by source inspection. No additional
codec probe was run. Recognize supported JSON encodings before classification, or
reject encoded reserved storage records, with codec/missing-payload regressions.

The earlier HG046-PROTOCOL-001 extension bypass is closed at this head for the
tested UTF-8 records. Shared availability and M3 read reserved content independently
of extension; M3 stdout, JUnit, collection JSON and collection stdout bind exact
execution/collection commands. The authorized nine compact M3 cases passed;
`m3-compact.json` captures their actual output once. Its 90 deselected cases reflect
the explicitly selected reviewer run and are not an integrated M3 regression claim.
Actual raw counts, JUnit dispositions, complete collection/nodeids and selector
coverage checks remain mandatory; metadata counts alone do not create PASS.

Independent committed decoding verified all seven selected governance checks at the
reviewed head, with exact tested source, commands and zero exits. Raw outputs show
950 harness, 241 unit and 59 compact tests; authority/lint/typecheck/diff outputs
also match their stated oracles. The tested-to-reviewed suffix is linear and only
adds own evidence plus the governance record. The committed prospective budget is
45,135 bytes across 52 changed evidence/review blobs, with no reported errors.

No frozen invariant, transaction boundary or table is touched. Diff scope contains
harness tooling/tests/contracts, derived hashes and own HG-046 artifacts. Frozen
baseline/files, requirement set, backlog and result/review/M3 schemas are byte
unchanged; index/manifest entries and authority metadata are unchanged. There is no
runtime, authorization, T1–T8, lock-order, provider trust, production activation or
executable-shadow change, and no SPEC_CHANGE_REQUIRED. Product/release NOT_RUN
meaning is preserved.

Ordinary review evidence still resolves at the reviewed SHA. Review-created evidence
requires an absent original entry, the same task directory, the exact record SHA
and a linear exclusively REVIEW_RECORD_ONLY suffix; it cannot repair an ordinary
invalid envelope using later bytes. This review's new child artifacts require that
exception when committed. The parent must run the mandatory selected gate after
reviews; this reviewer ran no full harness or normal check-harness command.
