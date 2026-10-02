# Protected base refresh

At 2026-10-02 07:13 UTC, protected master advanced from
9268fc8dd8c071c02dc5c698274dbf6fcd112776 to
fa729ca4bcca0f2c2e7a2aa0601890d1356b8842 (normal KL029 PR86 merge).
The branch incorporates that protected commit without modifying peer artifacts.
The new protected-base diff remains only HG044 scope. No frozen, validator,
plan, index or manifest authority changed on master during this refresh.

The new full test round and governance record use fa729ca as base. Historical
raw reports retain their original SHA/base and are not reused as final evidence.
Reviews starting at080f25c were interrupted before final artifacts and remain
unselected; their partial own r2 raw files are retained as development evidence.
The selected result must precede four fresh reviews. No actual merge or M3
closure record is authorized by this refresh.
