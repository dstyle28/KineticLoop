# Lossless raw retrieval

All original final-run and interrupted-run files, plus successful prototype raw
logs, JUnit, collection IDs and manifests, are captured once
as deterministic gzip payloads with SHA-256, byte lengths, command, tested SHA and
exit status. Identical bodies share a content-addressed payload. BENCHMARK_INDEX.json
maps original filenames to envelopes and records raw hashes. No arrays/logs/XML
were truncated or rewritten. The two obsolete successful prototype phase records
listed in excluded_development_artifacts remain local and are not PR task evidence.
CAPTURE_COMMANDS.py verifies a byte-for-byte roundtrip.

The codec is reused read-only from separately owned PR 91, not implemented or
modified in this PR. CODEC_SOURCE.json binds Git blob `6a27ad70e847e8662d5f28a79256982f34dbdcc2`
and SHA-256 `d0b8c7fd40f5ca5a6ab91641ea04678027af29cb80935d1bbc72f69097e9da6a`. Before integration, retrieve that blob from fetched
PR 91 and verify its hash before using it; after HG-047 merge the equivalent
repository command is available. The selected codec is a storage tool, not a
claim that the installed controller already admits its format.

From a checkout containing the result revision and fetched PR 91 objects:

```sh
git cat-file blob 6a27ad70e847e8662d5f28a79256982f34dbdcc2 > /private/tmp/hg048-codec.py
shasum -a 256 /private/tmp/hg048-codec.py
python3 /private/tmp/hg048-codec.py --root "$PWD" read \
  docs/exec-plans/evidence/HG-048/raw/final-serial-pytest-log.json \
  --revision RESULT_SHA > /private/tmp/hg048-serial-original.log
```

Replace RESULT_SHA with the committed implementation/result revision. The reader
uses that revision's regular Git blobs, validates payload/raw hashes and bounded
single gzip decoding, and checks tested-SHA ancestry. Keep the complete raw folder
when exporting envelopes because they refer to sibling content-addressed payloads.
COMPARISON.json and SCOPE_AUDIT.json are compact summaries, not replacements for
raw evidence. No complete diff patch is stored; use the recorded base/result SHAs.
