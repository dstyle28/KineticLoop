"""Render only the HG036 draft packet, never the active definition."""
import json
from pathlib import Path

folder = Path('docs/exec-plans/evidence/HG-036')
t = json.loads((folder / 'KL047_definition_draft.json').read_text())
def bullets(values):
    return '\n'.join('- ' + value for value in values) if values else '- none'
packet = f'''# KL-047 — {t['title']}

**Task identity:** `{t['task_identity']}`  
**Thread:** `THREAD-KL-047`  
**Milestone:** `M7`  
**Mode:** one fresh thread + one worktree + one PR  
**Status:** NOT_STARTED  
**Packet refinement:** ENFORCEABLE

## Goal

Implement only the fixed synthetic offline infrastructure foundation and source-derived mechanical scorer. Preserve genuine Fitness quality and all original evaluation/release obligations as unresolved; infrastructure task PASS does not close them.

## Dependencies

KL-005, KL-018

### Conditional dependencies
- none

## Entry conditions
{bullets(t['entry_conditions'])}

## Read first

Read root AGENTS.md, CURRENT_DOCUMENT_INDEX.json, this packet and actual merged prerequisite results/reviews/integrations first. Open only relevant source sections: plan G-REMOTE-AI/M7, Technical Spec section 11 and shadow path, Protocol 7.2–7.5, frozen S48, current release gates and the existing strict contract sources. Historical task IDs without namespace are not authority.

{bullets(t['context_files'])}

## Frozen impact map
- Invariants: INV-16
- Transactions: none
- Logical tables: S48

S48 is a read-only constraint reference; no S48 writer, database change, registration, production release selection or activation is authorized.

## Requirements covered (does NOT mean PASS)
- none

## Checks required for this task PR
{bullets(t['checks_required_for_this_task'])}

## Machine-readable check contract

```json
{json.dumps({'check_contracts': t['check_contracts'], 'evidence_paths': t['evidence_paths']}, indent=2)}
```

Execute every exact command on tested_commit. All checks begin NOT_RUN; no skip/xfail/xpass or zero collected tests meets a PASS oracle. Record committed output and counts. The full explicit evaluation suite must run in addition to every named selector. Existing default test discovery cannot substitute for it.

## Resource / write isolation

Resource keys:
{bullets(t['resource_keys'])}

Expected write paths:
{bullets(t['write_paths'])}

Environment requirements:
- none

Parallel write policy: **PARALLEL_IF_DEPENDENCIES_MET**. Reject overlapping resource keys/write paths before scheduling. Pure local functions own fitness_eval_contract only; no DB/Compose resources exist. Preserve all existing files outside this exact list, including shared package markers. Normal task result/evidence/review bookkeeping is permitted only under KL-047's own contract paths. No product/requirement registry status may be changed.

## Deliverables
{bullets(t['deliverables'])}

## Definition of Done
{t['definition_of_done']}

## Review requirements
- GENERAL
- PROTOCOL

Fresh independent review binds the implementation/result SHA; only the task's own REVIEW_RECORD_ONLY suffix may follow without rereview.

'''
packet += (folder / 'packet_body_draft.md').read_text()
(folder / 'KL047_packet_draft.md').write_text(packet)
