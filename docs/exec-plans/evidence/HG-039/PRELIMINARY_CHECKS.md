# Preparation-only checks

These checks predate KL075 merge and are not final governance or task evidence.

- Focused governance suite: 138 passed after the packet/replay feasibility clarification; lint and typecheck passed (125 files at the HG038 base).
- Unit suite: 209 passed. This is not the required final KL075-based run.
- Initial full harness suite overlapped preparation edits to the KL026 packet/hash after pytest had imported the earlier validator module: 3 failed, 574 passed. The three failures were test_legal_implementation_and_bookkeeping_pass, test_result_then_review_only_suffix_passes and test_yaml_and_json_valid_results_pass, each reporting only m3-next-wave-packet:KL-026. Module-level expected hash and later copied packet bytes came from different preparation states. No gate is weakened to accept this run; a settled-tree validator regression rerun and all final required checks must pass at the final tested SHA.
- No database/Docker lifecycle or foreign-worktree write ran. Temporary HG039 dependencies are isolated under /private/tmp/hg039-venv; the former shared kl017 environment disappeared during preparation, so it is no longer used.
