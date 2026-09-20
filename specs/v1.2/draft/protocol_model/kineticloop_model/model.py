"""Executable protocol semantics with synthetic time and no external services.

Every public mutation is a copy-on-write atomic command. This models committed
transactions, not PostgreSQL MVCC or physical network delivery. Test-only policy
numbers are never health recommendations. See README for the proof boundary.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from functools import wraps
import hashlib
import json
from pathlib import Path


class Rejected(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_policy(profile="local_shadow"):
    path = Path(__file__).resolve().parents[1] / "policies.json"
    return json.loads(path.read_text())[profile]


def atomic(fn):
    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        before = deepcopy(self.db)
        try:
            value = fn(self, *args, **kwargs)
            self.assert_invariants()
            return deepcopy(value)
        except Exception:
            self.db = before
            raise
    return wrapped


@dataclass
class FakeRepository:
    now: int = 0
    serial: int = 0
    frontier: int = 0
    generation: int = 0
    epoch: int = 0
    execution_basis: int = 0
    registry_revision: int = 0
    current_factset: str = ""
    current_manifest: str = ""
    current_bundle: str = ""
    artifacts: dict = field(default_factory=dict)
    revocations: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)
    associations: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    mappings: list = field(default_factory=list)
    admissions: list = field(default_factory=list)
    controls: list = field(default_factory=list)
    active_holds: set = field(default_factory=set)
    factsets: dict = field(default_factory=dict)
    projections: dict = field(default_factory=dict)
    manifests: dict = field(default_factory=dict)
    intents: dict = field(default_factory=dict)
    attempts: dict = field(default_factory=dict)
    reservations: dict = field(default_factory=dict)
    ledger: list = field(default_factory=list)
    proposals: dict = field(default_factory=dict)
    demands: dict = field(default_factory=dict)
    validations: dict = field(default_factory=dict)
    prescriptions: dict = field(default_factory=dict)
    authorizations: dict = field(default_factory=dict)
    authorization_events: list = field(default_factory=list)
    sessions: dict = field(default_factory=dict)
    bindings: list = field(default_factory=list)
    receipts: dict = field(default_factory=dict)
    event_log: list = field(default_factory=list)
    source_keys: dict = field(default_factory=dict)
    physical_sends: list = field(default_factory=list)


class ProtocolModel:
    LIVE = {"ADMITTED", "RUNNING"}

    def __init__(self, policy=None):
        self.db = FakeRepository()
        self.policy = deepcopy(policy) if policy is not None else load_policy()

    def check(self, condition, code):
        if not condition:
            raise Rejected(code)

    def new_id(self, prefix):
        self.db.serial += 1
        return "%s%d" % (prefix, self.db.serial)

    def event(self, kind, **data):
        self.db.event_log.append({"kind": kind, "at": self.db.now, **data})

    def artifact_closure(self, roots):
        seen = set()
        todo = list(roots)
        while todo:
            key = todo.pop()
            self.check(key in self.db.artifacts, "ARTIFACT_UNKNOWN")
            if key not in seen:
                seen.add(key)
                todo.extend(self.db.artifacts[key]["dependencies"])
        return tuple(sorted(seen))

    def artifacts_allowed(self, roots):
        closure = self.artifact_closure(roots)
        revoked = {e["artifact"] for e in self.db.revocations}
        self.check(not (set(closure) & revoked), "ARTIFACT_REVOKED")
        for key in closure:
            validity = self.db.artifacts[key]["validity"]
            if isinstance(validity, int):
                self.check(self.db.now < validity, "ARTIFACT_EXPIRED")
            else:
                self.check(isinstance(validity, dict) and validity.get("kind") == "TIMELESS"
                           and validity.get("approved_policy") == "policy-v1" and validity.get("reason"),
                           "VALIDITY_UNDEFINED")
        return closure

    @atomic
    def register_artifact(self, key, dependencies=(), validity=None):
        self.check(key not in self.db.artifacts, "IMMUTABLE_ARTIFACT")
        self.check(all(d in self.db.artifacts for d in dependencies), "ARTIFACT_UNKNOWN")
        self.db.artifacts[key] = {"dependencies": tuple(dependencies), "known_at": self.db.now,
                                  "validity": deepcopy(validity)}

    @atomic
    def revoke_artifact(self, key, command_key):
        receipt = ("REVOKE_ARTIFACT", command_key)
        if receipt in self.db.receipts:
            self.check(self.db.receipts[receipt] == key, "IDEMPOTENCY_CONFLICT")
            return {"replayed": True}
        self.check(key in self.db.artifacts, "ARTIFACT_UNKNOWN")
        self.db.registry_revision += 1
        self.db.revocations.append({"artifact": key, "revision": self.db.registry_revision,
                                    "known_at": self.db.now})
        self.db.receipts[receipt] = key
        self.event("ARTIFACT_REVOKED", artifact=key)

    @atomic
    def advance_time(self, ticks):
        self.check(ticks >= 0, "CLOCK_BACKWARDS")
        self.db.now += ticks

    @atomic
    def receive(self, source_key, payload, observed_at=0, trust="USER_CONTENT"):
        if source_key in self.db.source_keys:
            eid = self.db.source_keys[source_key]
            self.check(self.db.evidence[eid]["payload"] == payload, "SOURCE_IDENTITY_CONFLICT")
            return eid
        eid = self.new_id("E")
        self.db.evidence[eid] = {"payload": deepcopy(payload), "known_at": self.db.now,
                                 "observed_at": observed_at, "trust": trust,
                                 "command_authority": "NONE"}
        self.db.source_keys[source_key] = eid
        return eid

    @atomic
    def associate(self, evidence_id, candidates):
        self.check(evidence_id in self.db.evidence, "EVIDENCE_UNKNOWN")
        self.db.associations.append({"evidence": evidence_id, "candidates": tuple(candidates),
                                     "accepted": candidates[0] if len(candidates) == 1 else None,
                                     "known_at": self.db.now})
        self.db.frontier += 1

    def association_at(self, evidence_id, cutoff=None):
        cutoff = self.db.now if cutoff is None else cutoff
        rows = [r for r in self.db.associations
                if r["evidence"] == evidence_id and r["known_at"] <= cutoff]
        return rows[-1]["accepted"] if rows else None

    @atomic
    def accept_fact(self, evidence_id, actual_sets, upper, exercise="squat", success=True,
                    stable_id=None, credit=True):
        e = self.db.evidence[evidence_id]
        self.check(e["payload"].get("actual_sets") == actual_sets, "ACTUAL_NOT_SUPPORTED")
        self.check(actual_sets >= 0 and (upper is None or upper >= actual_sets), "EXPOSURE_INVALID")
        self.check(upper is None or e["payload"].get("actual_upper") == upper, "UPPER_NOT_SUPPORTED")
        sid = stable_id or self.new_id("F")
        prior = self.db.facts.get(sid, [])
        row = {"stable_id": sid, "revision": len(prior) + 1, "evidence": evidence_id,
               "known_at": self.db.now, "effective_at": e["observed_at"],
               "minimum": actual_sets, "upper": upper, "exercise": exercise,
               "success": success, "credit": credit}
        self.db.facts.setdefault(sid, []).append(row)
        self.db.admissions.append({"fact": sid, "revision": row["revision"],
                                   "progression": "ELIGIBLE" if credit else "UNRESOLVED",
                                   "exposure": "ELIGIBLE", "known_at": self.db.now})
        self.db.frontier += 1
        self.db.epoch += 1
        self.db.execution_basis += 1
        self.event("INPUT_ACCEPTED", fact=sid)
        return sid

    def current_facts(self, cutoff=None):
        cutoff = self.db.now if cutoff is None else cutoff
        result = {}
        for sid, versions in self.db.facts.items():
            eligible = [r for r in versions if r["known_at"] <= cutoff]
            if eligible:
                fact = deepcopy(eligible[-1])
                fact["event"] = self.association_at(fact["evidence"], cutoff)
                result[sid] = fact
        return result

    @atomic
    def hold(self, evidence_id=None, command_key="stop"):
        receipt = ("HOLD", command_key)
        if receipt in self.db.receipts:
            return self.db.receipts[receipt]
        hid = self.new_id("H")
        self.db.controls.append({"id": hid, "evidence": evidence_id, "kind": "HOLD",
                                 "at": self.db.now})
        self.db.active_holds.add(hid)
        self.db.epoch += 1
        self.db.receipts[receipt] = hid
        self.event("USER_REVOKE", hold=hid)
        return hid

    @atomic
    def clear_hold(self, hold_id, capability=False):
        self.check(capability, "CLEARANCE_NOT_AUTHORIZED")
        self.check(hold_id in self.db.active_holds, "HOLD_UNKNOWN")
        self.db.active_holds.remove(hold_id)
        self.db.controls.append({"id": hold_id, "kind": "CLEAR", "at": self.db.now})
        self.db.epoch += 1

    @atomic
    def build_factset(self):
        fid = self.new_id("FS")
        self.db.factsets[fid] = {"status": "BUILDING", "frontier": self.db.frontier,
                                  "epoch": self.db.epoch, "members": self.current_facts(),
                                  "member_revision": 0}
        return fid

    @atomic
    def edit_candidate(self, fid, key, value):
        f = self.db.factsets[fid]
        self.check(f["status"] == "BUILDING", "BUILD_CLOSED")
        f["members"][key] = deepcopy(value)
        f["member_revision"] += 1

    @atomic
    def complete_factset(self, fid):
        f = self.db.factsets[fid]
        self.check(f["status"] == "BUILDING", "BUILD_CLOSED")
        self.check(f["members"] == self.current_facts(), "MEMBERS_NOT_SUPPORTED")
        f["digest"] = digest(f["members"])
        f["completed_digest"] = f["digest"]
        f["completed_member_revision"] = f["member_revision"]
        f["status"] = "READY"

    @atomic
    def seal_factset(self, fid):
        f = self.db.factsets[fid]
        if f["status"] == "SEALED":
            return fid
        self.check(f["status"] == "READY", "FACTSET_NOT_READY")
        self.check(f["frontier"] == self.db.frontier and f["epoch"] == self.db.epoch, "BUILD_STALE")
        self.check(f["member_revision"] == f["completed_member_revision"] and
                   f["digest"] == f["completed_digest"], "BUILD_CHANGED")
        f["status"] = "SEALED"
        self.db.current_factset = fid
        self.event("FACTSET_SEALED", factset=fid)
        return fid

    def read_factset(self, fid):
        self.check(self.db.factsets[fid]["status"] == "SEALED", "FACTSET_UNSEALED")
        return deepcopy(self.db.factsets[fid]["members"])

    @atomic
    def compute_projection(self, fid, exercise="squat", expiry=80):
        facts = self.read_factset(fid)
        selected = {k: v for k, v in facts.items() if v["exercise"] == exercise}
        basis = digest(selected)
        for pid, p in self.db.projections.items():
            if (p["basis"], p["exercise"], p["expiry"]) == (basis, exercise, expiry):
                return pid
        pid = self.new_id("PR")
        self.db.projections[pid] = {"basis": basis, "exercise": exercise, "expiry": expiry,
                                    "engine": "projection-v1", "facts": selected}
        return pid

    @atomic
    def publish(self, fid, projection_ids, expiry=90, artifacts=("release-v1",)):
        facts = self.read_factset(fid)
        f = self.db.factsets[fid]
        self.check(fid == self.db.current_factset and f["frontier"] == self.db.frontier,
                   "BUILD_STALE")
        self.check(f["epoch"] == self.db.epoch, "EPOCH_MISMATCH")
        roots = tuple(artifacts) + tuple(self.db.projections[p]["engine"] for p in projection_ids)
        closure = self.artifacts_allowed(roots)
        self.check(expiry > self.db.now, "MANIFEST_EXPIRED")
        for pid in projection_ids:
            p = self.db.projections[pid]
            relevant = {k: v for k, v in facts.items() if v["exercise"] == p["exercise"]}
            self.check(p["basis"] == digest(relevant), "PROJECTION_BASIS_MISMATCH")
        mid = self.new_id("M")
        self.db.generation += 1
        self.db.manifests[mid] = {"factset": fid, "facts": facts, "projections": tuple(projection_ids),
                                 "generation": self.db.generation, "epoch": self.db.epoch,
                                 "frontier": self.db.frontier, "expiry": expiry,
                                 "artifacts": closure, "registry_revision": self.db.registry_revision}
        self.db.current_manifest = mid
        self.event("MANIFEST_PUBLISHED", manifest=mid)
        return mid

    def tool_read(self, mid, live=False):
        m = self.db.manifests[mid]
        if live:
            self.check(m["frontier"] == self.db.frontier, "INPUT_FRONTIER_MISMATCH")
        return deepcopy(m["facts"])

    def resolve(self, mid, exercise="squat", citations=(), expiry=70):
        # Citations never narrow this authoritative search.
        facts = [f for f in self.db.manifests[mid]["facts"].values() if f["exercise"] == exercise]
        grouped = {}
        ambiguous = False
        for f in facts:
            if f["event"] is None:
                ambiguous = True
                continue
            grouped.setdefault(f["event"], []).append(f)
        supporting, contradicting = [], []
        for event, items in grouped.items():
            if any(not f["success"] or not f["credit"] for f in items):
                contradicting.append(event)
            elif any(f["success"] and f["credit"] for f in items):
                supporting.append(event)
        confirmed_group_minimum = sum(max(f["minimum"] for f in items) for items in grouped.values())
        # An unassociated report may overlap an identified event. Do not add it
        # as an independent event, but do not erase its confirmed exposure.
        minimum = max([confirmed_group_minimum] + [f["minimum"] for f in facts])
        unknown = ambiguous or any(f["upper"] is None for f in facts)
        upper = None if unknown else sum(max(f["upper"] for f in items) for items in grouped.values())
        return {"manifest": mid, "supporting": sorted(supporting), "contradicting": sorted(contradicting),
                "independent_events": len(grouped), "coverage": "PARTIAL" if ambiguous else "COMPLETE",
                "minimum": minimum, "upper": upper, "expiry": expiry}

    @atomic
    def admit_intent(self, constraints, purpose="daily", request_key=None):
        receipt = ("ADMIT", request_key) if request_key else None
        if receipt and receipt in self.db.receipts:
            old_hash, iid = self.db.receipts[receipt]
            self.check(old_hash == digest(constraints), "IDEMPOTENCY_CONFLICT")
            return iid
        current = next((i for i in self.db.intents.values()
                        if i["purpose"] == purpose and i["status"] in self.LIVE), None)
        if current:
            if current["constraints"] != constraints:
                current["request_revision"] += 1
                current["constraints"] = deepcopy(constraints)
            iid = current["id"]
        else:
            self.check(len(self.db.intents) < self.policy["max_roots"], "QUOTA_EXHAUSTED")
            self.check(all(self.policy.get(k) is not None for k in
                           ("max_calls", "max_tokens", "max_cost_units", "deadline_ticks", "lease_ticks")),
                       "CONFIG_UNAVAILABLE")
            iid = self.new_id("I")
            self.db.intents[iid] = {"id": iid, "purpose": purpose, "status": "ADMITTED",
                                   "constraints": deepcopy(constraints), "request_revision": 1,
                                   "deadline": self.db.now + self.policy["deadline_ticks"],
                                   "fence": 0, "lease_until": 0, "owner": None, "stale_restarts": 0}
        if receipt:
            self.db.receipts[receipt] = (digest(constraints), iid)
        return iid

    @atomic
    def acquire(self, iid, owner):
        i = self.db.intents[iid]
        self.check(i["status"] in self.LIVE, "INTENT_TERMINAL")
        self.check(self.db.now < i["deadline"], "DEADLINE_EXCEEDED")
        self.check(i["owner"] is None or self.db.now >= i["lease_until"], "LEASE_HELD")
        i["fence"] += 1
        i["owner"] = owner
        i["lease_until"] = min(i["deadline"], self.db.now + self.policy["lease_ticks"])
        i["status"] = "RUNNING"
        aid = self.new_id("AT")
        self.db.attempts[aid] = {"intent": iid, "request_revision": i["request_revision"],
                                "manifest": self.db.current_manifest, "epoch": self.db.epoch,
                                "fence": i["fence"], "owner": owner, "status": "RUNNING"}
        return aid

    def attempt_guard(self, aid):
        a = self.db.attempts[aid]
        i = self.db.intents[a["intent"]]
        self.check(i["status"] in self.LIVE, "INTENT_TERMINAL")
        self.check(self.db.now < i["deadline"], "DEADLINE_EXCEEDED")
        self.check(a["fence"] == i["fence"] and a["owner"] == i["owner"], "FENCE_MISMATCH")
        self.check(self.db.now < i["lease_until"], "LEASE_EXPIRED")
        self.check(a["request_revision"] == i["request_revision"], "REQUEST_STALE")
        self.check(a["status"] == "RUNNING", "ATTEMPT_TERMINAL")
        return a, i

    @atomic
    def restart_stale(self, aid):
        a = self.db.attempts[aid]
        i = self.db.intents[a["intent"]]
        self.check(i["status"] in self.LIVE and self.db.now < i["deadline"], "INTENT_TERMINAL")
        self.check(a["fence"] == i["fence"], "FENCE_MISMATCH")
        self.check(a["status"] == "RUNNING", "ATTEMPT_TERMINAL")
        self.check(a["manifest"] != self.db.current_manifest or a["epoch"] != self.db.epoch or
                   a["request_revision"] != i["request_revision"], "NOT_STALE")
        a["status"] = "STALE"
        i["owner"] = None
        i["fence"] += 1
        if i["stale_restarts"] >= self.policy["max_stale_restarts"]:
            i["status"] = "STALE_RETRY_EXHAUSTED"
        else:
            i["stale_restarts"] += 1
        return i["status"]

    def usage(self, iid):
        rows = [r for r in self.db.reservations.values()
                if r["intent"] == iid and r["status"] != "CANCELLED_BEFORE_DISPATCH"]
        return {"calls": len(rows), "tokens": sum(r["charged_tokens"] for r in rows),
                "cost": sum(r["charged_cost"] for r in rows)}

    @atomic
    def reserve(self, aid, slot, max_tokens=20, max_cost=20):
        a, i = self.attempt_guard(aid)
        existing = next((k for k, r in self.db.reservations.items()
                         if r["attempt"] == aid and r["slot"] == slot), None)
        if existing:
            r = self.db.reservations[existing]
            self.check((r["reserved_tokens"], r["reserved_cost"]) == (max_tokens, max_cost),
                       "IDEMPOTENCY_CONFLICT")
            return existing
        use = self.usage(a["intent"])
        self.check(use["calls"] + 1 <= self.policy["max_calls"] and
                   use["tokens"] + max_tokens <= self.policy["max_tokens"] and
                   use["cost"] + max_cost <= self.policy["max_cost_units"], "BUDGET_EXHAUSTED")
        self.check(max_tokens >= 0 and max_cost >= 0, "RESERVATION_INVALID")
        rid = self.new_id("R")
        self.db.reservations[rid] = {"attempt": aid, "intent": a["intent"], "slot": slot,
                                    "status": "RESERVED", "reserved_tokens": max_tokens,
                                    "reserved_cost": max_cost, "charged_tokens": max_tokens,
                                    "charged_cost": max_cost}
        self.db.ledger.append({"reservation": rid, "kind": "RESERVED"})
        return rid

    @atomic
    def permit_dispatch(self, rid):
        r = self.db.reservations[rid]
        self.attempt_guard(r["attempt"])
        self.check(r["status"] == "RESERVED", "DISPATCH_ALREADY_POSSIBLE")
        r["status"] = "DISPATCH_INTENT"
        self.db.ledger.append({"reservation": rid, "kind": "DISPATCH_INTENT"})

    @atomic
    def physical_send(self, rid):
        r = self.db.reservations[rid]
        # Remote execution may outlive the local lease/cancellation.
        self.check(any(e["reservation"] == rid and e["kind"] == "DISPATCH_INTENT"
                       for e in self.db.ledger), "NO_DISPATCH_PERMIT")
        self.check(rid not in self.db.physical_sends, "DUPLICATE_PHYSICAL_SEND")
        self.db.physical_sends.append(rid)

    @atomic
    def mark_dispatched(self, rid):
        r = self.db.reservations[rid]
        self.check(r["status"] == "DISPATCH_INTENT", "INVALID_TRANSITION")
        r["status"] = "DISPATCHED"

    @atomic
    def cancel_reservation(self, rid):
        r = self.db.reservations[rid]
        self.check(r["status"] == "RESERVED", "MAY_HAVE_DISPATCHED")
        r["status"] = "CANCELLED_BEFORE_DISPATCH"
        r["charged_tokens"] = r["charged_cost"] = 0
        self.db.ledger.append({"reservation": rid, "kind": "CANCELLED_BEFORE_DISPATCH"})

    @atomic
    def settle(self, rid, receipt_id, tokens, cost):
        r = self.db.reservations[rid]
        key = ("SETTLE", receipt_id)
        payload = (rid, tokens, cost)
        if key in self.db.receipts:
            self.check(self.db.receipts[key] == payload, "SETTLEMENT_CONFLICT")
            return
        self.check(r["status"] in {"DISPATCH_INTENT", "DISPATCHED", "OUTCOME_UNKNOWN"},
                   "INVALID_TRANSITION")
        self.check(0 <= tokens <= r["reserved_tokens"] and 0 <= cost <= r["reserved_cost"],
                   "RESERVATION_BOUND_VIOLATED")
        r.update(status="SETTLED", charged_tokens=tokens, charged_cost=cost)
        self.db.ledger.append({"reservation": rid, "kind": "SETTLED", "receipt": receipt_id})
        self.db.receipts[key] = payload

    @atomic
    def reap(self, iid):
        i = self.db.intents[iid]
        if i["status"] not in self.LIVE:
            return i["status"]
        self.check(self.db.now >= i["lease_until"] or self.db.now >= i["deadline"],
                   "STALE_REAPER_CANDIDATE")
        i["fence"] += 1
        i["owner"] = None
        if self.db.now >= i["deadline"]:
            i["status"] = "DEADLINE_EXCEEDED"
        for r in self.db.reservations.values():
            if r["intent"] == iid and r["status"] in {"DISPATCH_INTENT", "DISPATCHED"}:
                r["status"] = "OUTCOME_UNKNOWN"
                self.db.ledger.append({"reservation": next(k for k, v in self.db.reservations.items() if v is r),
                                       "kind": "OUTCOME_UNKNOWN"})
        return i["status"]

    @atomic
    def cancel_intent(self, iid):
        i = self.db.intents[iid]
        if i["status"] in self.LIVE:
            i["status"] = "CANCELLED"
            for rid, r in list(self.db.reservations.items()):
                if r["intent"] == iid and r["status"] == "RESERVED":
                    self.cancel_reservation(rid)
        return i["status"]

    @atomic
    def record_proposals(self, aid, payload=None, fitness_parent=None):
        a, _ = self.attempt_guard(aid)
        payload = payload or {"load_change": 1, "working_sets": 1}
        fid = self.new_id("FP")
        self.db.proposals[fid] = {"kind": "FITNESS", "payload": deepcopy(payload),
                                  "hash": digest(payload), "attempt": aid, "parent": fitness_parent}
        did = self.new_id("DF")
        self.db.demands[did] = {"fitness": fid, "fitness_hash": digest(payload),
                                "hash": digest({"working_sets": payload["working_sets"]}),
                                "semantic": "PRESCRIBED_QUANTITY"}
        nid = self.new_id("NP")
        self.db.proposals[nid] = {"kind": "NUTRITION", "fitness": fid, "demand": did,
                                  "fitness_hash": digest(payload), "demand_hash": self.db.demands[did]["hash"],
                                  "attempt": aid}
        return fid, did, nid

    def dependency_check(self, fid, did, nid):
        f, d, n = self.db.proposals[fid], self.db.demands[did], self.db.proposals[nid]
        self.check(d["fitness"] == fid and n["fitness"] == fid and n["demand"] == did and
                   d["fitness_hash"] == f["hash"] == n["fitness_hash"] and
                   n["demand_hash"] == d["hash"], "DEPENDENCY_HASH_MISMATCH")

    @atomic
    def validate(self, aid, triple, evidence_expiry=70, extra_validities=None):
        a, _ = self.attempt_guard(aid)
        self.dependency_check(*triple)
        self.check(self.policy.get("progression_enabled") is True, "POLICY_UNCONFIGURED")
        r = self.resolve(a["manifest"], expiry=evidence_expiry)
        self.check(bool(r["supporting"]) and not r["contradicting"] and r["coverage"] == "COMPLETE",
                   "EVIDENCE_INSUFFICIENT")
        vid = self.new_id("V")
        self.db.validations[vid] = {"attempt": aid, "triple": tuple(triple), "resolution": r,
                                     "manifest": a["manifest"], "epoch": a["epoch"],
                                     "execution_basis": self.db.execution_basis,
                                     "extra_validities": extra_validities or {}}
        return vid

    def validity_closure(self, mid, validation, requested_until):
        m = self.db.manifests[mid]
        endpoints = {"requested": requested_until, "manifest": m["expiry"],
                     "resolution": validation["resolution"]["expiry"],
                     "policy_max": self.db.now + self.policy["authorization_ttl"],
                     "calendar": self.policy["calendar_end"]}
        for pid in m["projections"]:
            endpoints["projection:" + pid] = self.db.projections[pid]["expiry"]
        for key in self.artifact_closure(m["artifacts"] + ("validator-v1", "prompt-v1", "model-v1")):
            endpoints["artifact:" + key] = self.db.artifacts[key]["validity"]
        endpoints.update({"extra:" + key: value for key, value in validation["extra_validities"].items()})
        bounded = []
        for key, end in endpoints.items():
            if isinstance(end, dict):
                self.check(end.get("kind") == "TIMELESS" and end.get("approved_policy") == "policy-v1"
                           and bool(end.get("reason")), "VALIDITY_UNDEFINED")
                continue
            self.check(isinstance(end, int), "VALIDITY_UNDEFINED")
            bounded.append(end)
        end = min(bounded)
        self.check(end > self.db.now, "DEPENDENCY_EXPIRED")
        return end, endpoints

    @atomic
    def commit(self, aid, vid, command_key, requested_until=95, existing_prescription=None,
               environment="TEST_ONLY"):
        self.check(environment == "TEST_ONLY" and self.policy["environment"] == "TEST_ONLY",
                   "PRODUCTION_DISABLED")
        fingerprint = digest([aid, vid, requested_until, existing_prescription])
        key = ("COMMIT", command_key)
        if key in self.db.receipts:
            record = self.db.receipts[key]
            self.check(record["fingerprint"] == fingerprint, "IDEMPOTENCY_CONFLICT")
            return {**record["result"], "replayed": True}
        a, i = self.attempt_guard(aid)
        v = self.db.validations[vid]
        self.check(v["attempt"] == aid, "VALIDATION_MISMATCH")
        self.check(a["manifest"] == self.db.current_manifest, "MANIFEST_STALE")
        m = self.db.manifests[a["manifest"]]
        self.check(a["epoch"] == m["epoch"] == self.db.epoch, "EPOCH_MISMATCH")
        self.check(not self.db.active_holds, "HOLD_ACTIVE")
        self.check(v["execution_basis"] == self.db.execution_basis, "EXECUTION_BASIS_STALE")
        closure = self.artifacts_allowed(m["artifacts"] + ("validator-v1", "prompt-v1", "model-v1"))
        self.dependency_check(*v["triple"])
        expiry, endpoints = self.validity_closure(a["manifest"], v, requested_until)
        payload = self.db.proposals[v["triple"][0]]["payload"]
        if existing_prescription:
            pid = existing_prescription
            self.check(self.db.prescriptions[pid]["hash"] == digest(payload), "CONTENT_MISMATCH")
        else:
            pid = self.new_id("P")
            self.db.prescriptions[pid] = {"payload": deepcopy(payload), "hash": digest(payload)}
        auth = self.new_id("A")
        self.db.authorizations[auth] = {"prescription": pid, "hash": digest(payload),
                                        "manifest": a["manifest"], "epoch": self.db.epoch,
                                        "valid_from": self.db.now, "valid_until": expiry,
                                        "dependency_validities": endpoints, "artifacts": closure,
                                        "registry_revision": self.db.registry_revision,
                                        "scope": "training", "environment": "TEST_ONLY"}
        bundle = self.new_id("B")
        self.db.current_bundle = bundle
        self.db.execution_basis += 1
        i.update(status="FOUND_VALID_PLAN", result={"bundle": bundle, "prescription": pid, "authorization": auth})
        a["status"] = "COMMITTED"
        result = deepcopy(i["result"])
        self.db.receipts[key] = {"fingerprint": fingerprint, "result": result}
        self.event("PLAN_COMMITTED", authorization=auth)
        return {**result, "replayed": False}

    def executable(self, auth, scope="training"):
        a = self.db.authorizations[auth]
        self.check(a["scope"] == scope, "AUTH_SCOPE_DENIED")
        self.check(a["hash"] == self.db.prescriptions[a["prescription"]]["hash"], "CONTENT_MISMATCH")
        self.check(a["epoch"] == self.db.epoch, "EPOCH_MISMATCH")
        self.check(not self.db.active_holds, "HOLD_ACTIVE")
        self.artifacts_allowed(a["artifacts"])
        self.check(not any(e["authorization"] == auth for e in self.db.authorization_events), "AUTH_REVOKED")
        self.check(a["valid_from"] <= self.db.now < a["valid_until"], "AUTH_EXPIRED")
        for validity in a["dependency_validities"].values():
            if isinstance(validity, int):
                self.check(self.db.now < validity, "DEPENDENCY_EXPIRED")
        return True

    @atomic
    def start(self, auth, command_key, session=None, resume=False):
        key = ("RESUME" if resume else "START", command_key)
        fingerprint = (auth, session)
        if key in self.db.receipts:
            old, sid = self.db.receipts[key]
            self.check(old == fingerprint, "IDEMPOTENCY_CONFLICT")
            return {"session": sid, "replayed": True}
        self.executable(auth)
        if resume:
            self.check(session in self.db.sessions, "SESSION_UNKNOWN")
            sid = session
        else:
            sid = session or self.new_id("S")
            self.check(sid not in self.db.sessions, "EXECUTION_CONFLICT")
            self.db.sessions[sid] = {"origin": "APP_STARTED", "status": "RUNNING"}
        self.db.bindings.append({"session": sid, "authorization": auth,
                                 "prescription": self.db.authorizations[auth]["prescription"],
                                 "kind": "RESUME" if resume else "START", "at": self.db.now})
        self.db.sessions[sid]["status"] = "RUNNING"
        self.db.execution_basis += 1
        self.db.receipts[key] = (fingerprint, sid)
        self.event("SESSION_STARTED", authorization=auth)
        return {"session": sid, "replayed": False}

    @atomic
    def record_external_session(self, fact_id):
        self.check(fact_id in self.db.facts, "FACT_UNKNOWN")
        sid = self.new_id("S")
        self.db.sessions[sid] = {"origin": "EXTERNAL_REPORTED", "fact": fact_id, "status": "COMPLETED"}
        return sid

    @atomic
    def stop_authorization(self, auth):
        self.db.authorization_events.append({"authorization": auth, "kind": "REVOKED", "at": self.db.now})

    @atomic
    def finish_search(self, iid, proof=None):
        i = self.db.intents[iid]
        self.check(i["status"] in self.LIVE, "INTENT_TERMINAL")
        # This small model has no general constraint solver and cannot assert infeasibility.
        self.check(proof is None, "UNVERIFIED_CONFLICT_PROOF")
        i["status"] = "SEARCH_BUDGET_EXHAUSTED"

    def summary(self, evidence_ids, text):
        self.check(all(e in self.db.evidence for e in evidence_ids), "EVIDENCE_UNKNOWN")
        return {"text": text, "sources": tuple(evidence_ids), "trust": "MODEL_DERIVED", "command_authority": "NONE"}

    def approve(self, content, capability=False):
        self.check(capability and content.get("command_authority") == "DEDICATED_UI_CAPABILITY",
                   "COMMAND_NOT_AUTHORIZED")

    @atomic
    def record_mapping(self, source, target):
        self.db.mappings.append({"source": source, "target": target, "known_at": self.db.now})

    def replay(self, cutoff, mode, historical_release="release-v1", current_release="release-v2"):
        self.check(mode in {"HISTORICAL", "CURRENT_BACKTEST"}, "REPLAY_MODE_INVALID")
        return {"mode": mode, "cutoff": cutoff, "facts": self.current_facts(cutoff),
                "mappings": [deepcopy(m) for m in self.db.mappings if m["known_at"] <= cutoff],
                "release": historical_release if mode == "HISTORICAL" else current_release,
                "simulation": True}

    def fallback(self):
        if not self.policy["fallbacks"] or self.db.active_holds:
            return "UNAVAILABLE"
        raise Rejected("FALLBACK_NOT_IMPLEMENTED")

    def assert_invariants(self):
        for f in self.db.factsets.values():
            if f["status"] == "SEALED":
                assert f["digest"] == digest(f["members"]), "sealed factset mutated"
        if self.db.current_factset:
            assert self.db.factsets[self.db.current_factset]["status"] == "SEALED"
        assert self.db.generation == len(self.db.manifests)
        for iid in self.db.intents:
            u = self.usage(iid)
            assert u["calls"] <= self.policy["max_calls"]
            assert u["tokens"] <= self.policy["max_tokens"]
            assert u["cost"] <= self.policy["max_cost_units"]
        assert len(self.db.physical_sends) == len(set(self.db.physical_sends))
        for rid in self.db.physical_sends:
            assert self.db.reservations[rid]["status"] != "CANCELLED_BEFORE_DISPATCH"
        for a in self.db.authorizations.values():
            assert a["hash"] == self.db.prescriptions[a["prescription"]]["hash"]
            assert all(a["valid_until"] <= end for end in a["dependency_validities"].values()
                       if isinstance(end, int))
        for b in self.db.bindings:
            assert b["prescription"] == self.db.authorizations[b["authorization"]]["prescription"]


def seeded_model(model_class=ProtocolModel, policy=None):
    m = model_class(load_policy("test_fixture") if policy is None else policy)
    timeless = {"kind": "TIMELESS", "approved_policy": "policy-v1", "reason": "synthetic immutable artifact; revocable"}
    for name in ("policy-v1", "projection-v1", "validator-v1", "prompt-v1", "model-v1", "system-v1"):
        m.register_artifact(name, validity=timeless)
    m.register_artifact("release-v1", ("policy-v1", "projection-v1", "validator-v1", "prompt-v1", "model-v1", "system-v1"), validity=timeless)
    e = m.receive("seed", {"actual_sets": 1, "actual_upper": 1})
    m.associate(e, ["workout-1"])
    fact = m.accept_fact(e, 1, 1)
    publish_current(m)
    return m, fact


def publish_current(m, expiry=90, projection_expiry=80):
    f = m.build_factset()
    m.complete_factset(f)
    m.seal_factset(f)
    p = m.compute_projection(f, expiry=projection_expiry)
    return m.publish(f, [p], expiry=expiry)


def ready_plan(m, purpose="daily", evidence_expiry=70, extra_validities=None):
    iid = m.admit_intent({"minutes": 70}, purpose=purpose)
    aid = m.acquire(iid, "worker-1")
    triple = m.record_proposals(aid)
    vid = m.validate(aid, triple, evidence_expiry=evidence_expiry, extra_validities=extra_validities)
    return iid, aid, vid
