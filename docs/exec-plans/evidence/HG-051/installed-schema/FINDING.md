# Installed archival schema correction

At reviewed 7141b1dfe48df8f0e25429cf9ff646af6de4b5ce / head
b9c355fd9663b20a8d0af7297eb00b42093c9361, the copied worker decoder tried to
read /gate/HISTORICAL_EVIDENCE_MAPPING.schema.json. Neither the eleven controller
ASSETS nor the six worker Python copies included this file. Exact authorized
archive retrieval raised FileNotFoundError, while the HG051 no-archive budget
passed. KL080 budget also failed even before migration. See before.json and
before.py; the temporary fixture recovered approved bytes only and made no claim
about original execution proof.

BLOCKER corrected by embedding the exact indexed authority bytes in the reviewed,
pinned decoder, checking exact candidate schema bytes at validator entry, and
exercising the installed worker layout in the committed inventory roundtrip.
No filesystem/candidate fallback, controller asset expansion, installation,
credential change, DB lifecycle, production authorization or migration occurred.
The prior four reviews bind the preceding implementation and require fresh review.
