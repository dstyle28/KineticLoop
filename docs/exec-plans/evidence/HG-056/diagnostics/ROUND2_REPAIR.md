# HG056 round-two classifier repair

Independent SECURITY_DATA_BOUNDARY review at R388557f1 / T272784e9 found S6 prefixed/comment-separated adjacent literals, S7 named Unicode ASCII escapes, and S8 multiline typed identifier writes. The exact review and metadata probes are preserved in round2/ and security_round2/.

The repair adds classification-only views for literal prefixes/comments and named ASCII escapes, and reuses the bounded lexical delimiter walk to identify logical statements for typed writes. It does not execute source, grant source trust or accept source as evidence metadata. Original byte acceptance, codecs, budgets, binding, ancestry, provenance, per-edge mapping and suffix guards remain unchanged. Independent ordinary-read and separate-statement annotation fixtures guard compatibility; shared bound-read/M3/audit and review-only history fixtures reject each new wrapper.

The complete Python set observation stays ambiguous under the existing damaged/partial-object rule; no set exemption is introduced. Root source-inspection adjudication remains NOT_IMPLEMENTED and BLOCKED, as do immutable KL036 history and unrepeated full-cycle gates. Previous actual results and all review rounds remain unchanged.
