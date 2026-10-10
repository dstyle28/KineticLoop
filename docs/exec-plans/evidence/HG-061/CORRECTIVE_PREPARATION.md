# Same-task prospective submission-order correction

The original B remains ebee712b591d14c165007cd3d56d89cb14ea1487. Original Tde3,
R1f45 and C93a remain intact in the first-parent history. The final ci-pr failure
is preserved under superseded-93a922a86dab-final, with exact original result/review
and check-index Git pointers instead of duplicate bulk records.

The existing tested-suffix guard correctly rejected the author's post-T manifest
update. This is a submission-order defect, not a missing semantic rule. No validator,
test, packet semantics or frozen authority is changed for this correction. Remove
only own mutable HG-061.yaml registration from the manifest before the new T;
retain immutable prior capture registrations and unrelated entries. All helper and
derived-manifest changes are prepared before testing. The capture_result_v2 helper
asserts byte-identical manifest before and after capture/result creation and never
writes it. New output is appended only under own evidence and the result record.

run_checks_v2 executes all eight author checks freshly at the new stable T, using
the existing intact pytest-xdist3.8.0/execnet2.1.2 cache and approved Python3.12
fallback. Package hashes are pinned in DEPENDENCY_PROVENANCE_V2.json and rechecked
by the capture helper. A fresh envelope binds each actual new execution, even when
identical raw bytes share an existing same-directory content-addressed payload.
No old de3, HG060 or prior review/installation acceptance is reused.

Old canonical reviews are historical until fresh reviews replace selection under a
new own REVIEW_RECORD_ONLY suffix. Their original canonical bytes and unchanged
support remain retrievable at C93a. Before requesting new reviews, a read-only
unchanged governance_suffix_errors tested proof must pass for new T to new R;
retain that proof in scratch. Do not rerun full ci-pr until fresh reviews and final C.
Root retains complete installation review/install/admission/App/fullDB/cleanup/live
gates/normal merge. No guard relaxation, history rewrite or DB/App reservation occurs.
