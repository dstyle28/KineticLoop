# Raw-output formatting and selected source diff

The broad source_diff at 263c82e761747b88ac56f96be014e158f494dae0 reported trailing
whitespace only in the preserved failed pytest stdout harness-d6603c6.log. Pytest
uses literal spaces in traceback source lines and separators. That evidence remains
byte-identical to the captured subprocess stdout and its JSON capture/raw SHA.
No raw failure output is trimmed, sanitized, overwritten or selected as PASS.

The selected source_diff_preserved_raw check runs git diff --check across every
protected-base changed path except that one exact owned raw log. It passes. The
scope/frozen audit still checks every changed path, including that log, and validates
unchanged frozen files and historical definitions. No source/packet/schema/contract/
metadata/test path is exempted. The rejected broad formatting capture remains in own
HG045 evidence as an unselected diagnostic, not an approval refusal or test bypass.
This new note and selected capture are append-only governance evidence after the
immutable tested SHA, permitted by the governance tested-to-reviewed suffix contract.
