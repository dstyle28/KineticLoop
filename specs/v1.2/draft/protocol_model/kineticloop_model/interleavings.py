"""Enumerate every enabled schedule in a bounded transaction/lock model.

An APPLY step is atomic (guard + durable changes or rollback). READ observation,
shared/exclusive registry gate, user lock, and releases are independently
scheduled. This proves the model's stated linearization rules only; it does not
model SQL statement execution, OS fairness, or PostgreSQL's lock implementation.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from .model import Rejected, ready_plan, seeded_model


@dataclass
class Operation:
    name: str
    method: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    registry_mode: str = "none"
    user_lock: bool = True

    @property
    def steps(self):
        if self.registry_mode == "none":
            return ("OBSERVE", "USER", "APPLY", "RELEASE_USER") if self.user_lock else ("APPLY",)
        return ("OBSERVE", "REGISTRY", "USER", "APPLY", "RELEASE_USER", "RELEASE_REGISTRY")


@dataclass
class ScheduleState:
    model: object
    pcs: list
    readers: set = field(default_factory=set)
    writer: object = None
    user_owner: object = None
    results: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)


def enabled(state, operations, actor):
    op = operations[actor]
    if state.pcs[actor] >= len(op.steps):
        return False
    step = op.steps[state.pcs[actor]]
    if step == "REGISTRY":
        if op.registry_mode == "exclusive":
            return state.writer is None and not state.readers
        return state.writer is None
    if step == "USER" and op.user_lock:
        return state.user_owner is None
    return True


def transition(state, operations, actor):
    result = deepcopy(state)
    op = operations[actor]
    step = op.steps[result.pcs[actor]]
    result.trace.append(op.name + ":" + step)
    if step == "REGISTRY":
        if op.registry_mode == "exclusive": result.writer = actor
        else: result.readers.add(actor)
    elif step == "USER" and op.user_lock:
        result.user_owner = actor
    elif step == "APPLY":
        try:
            getattr(result.model, op.method)(*op.args, **op.kwargs)
            result.results[op.name] = "OK"
        except Rejected as exc:
            result.results[op.name] = exc.code
    elif step == "RELEASE_USER" and op.user_lock:
        assert result.user_owner == actor
        result.user_owner = None
    elif step == "RELEASE_REGISTRY":
        if op.registry_mode == "exclusive": result.writer = None
        else: result.readers.remove(actor)
    result.pcs[actor] += 1
    return result


def explore(name, model, operations, oracle):
    stats = {"scenario": name, "complete_schedules": 0, "visited_prefixes": 0,
             "deadlocks": 0, "violations": [], "outcomes": {}}

    def visit(state):
        stats["visited_prefixes"] += 1
        if all(state.pcs[i] == len(op.steps) for i, op in enumerate(operations)):
            stats["complete_schedules"] += 1
            outcome = ";".join(op.name + "=" + state.results[op.name] for op in operations)
            stats["outcomes"][outcome] = stats["outcomes"].get(outcome, 0) + 1
            try:
                state.model.assert_invariants()
                oracle(state)
            except (AssertionError, Rejected) as exc:
                stats["violations"].append({"error": str(exc), "trace": state.trace})
            return
        actors = [i for i in range(len(operations)) if enabled(state, operations, i)]
        if not actors:
            stats["deadlocks"] += 1
            stats["violations"].append({"error": "MODEL_DEADLOCK", "trace": state.trace})
        for actor in actors:
            visit(transition(state, operations, actor))

    visit(ScheduleState(deepcopy(model), [0] * len(operations)))
    return stats


def critical_scenarios():
    scenarios = []
    m, _ = seeded_model()
    f = m.build_factset(); m.complete_factset(f); m.seal_factset(f)
    p = m.compute_projection(f)
    def publish_oracle(s):
        assert s.results["revoke"] == "OK"
        if s.results["publish"] == "OK":
            assert s.model.db.manifests[s.model.db.current_manifest]["epoch"] < s.model.db.epoch
        else:
            assert s.results["publish"] == "EPOCH_MISMATCH"
    scenarios.append(("publish_vs_user_revoke", m, [
        Operation("publish", "publish", (f, [p]), registry_mode="shared"), Operation("revoke", "hold", kwargs={"command_key": "stop"})],
        publish_oracle))

    m, _ = seeded_model(); _, a, v = ready_plan(m)
    auth = m.commit(a, v, "commit")["authorization"]
    def start_oracle(s):
        kinds = [e["kind"] for e in s.model.db.event_log]
        if s.results["start"] == "OK":
            assert kinds.index("SESSION_STARTED") < kinds.index("USER_REVOKE")
        else:
            assert s.results["start"] == "EPOCH_MISMATCH"
            assert not s.model.db.bindings
    scenarios.append(("start_vs_user_revoke", m, [Operation("start", "start", (auth, "start"), registry_mode="shared"),
        Operation("revoke", "hold", kwargs={"command_key": "stop"})], start_oracle))

    m, _ = seeded_model(); i, a, _ = ready_plan(m); r = m.reserve(a, "call")
    def dispatch_oracle(s):
        status = s.model.db.reservations[r]["status"]
        if s.results["permit"] == "OK":
            assert status == "DISPATCH_INTENT" and s.model.usage(i)["calls"] == 1
        else:
            assert s.results["permit"] == "INTENT_TERMINAL"
            assert status == "CANCELLED_BEFORE_DISPATCH" and s.model.usage(i)["calls"] == 0
    scenarios.append(("cancel_vs_dispatch_intent", m, [Operation("cancel", "cancel_intent", (i,)),
        Operation("permit", "permit_dispatch", (r,))], dispatch_oracle))

    m, _ = seeded_model(); i, a, v = ready_plan(m)
    def takeover_oracle(s):
        if s.results["commit"] == "OK":
            assert s.results["takeover"] != "OK"
            assert s.model.db.intents[i]["status"] == "FOUND_VALID_PLAN"
        else:
            assert s.results["commit"] in {"FENCE_MISMATCH", "LEASE_EXPIRED"}
            assert not s.model.db.authorizations
        if s.results["takeover"] == "OK":
            assert s.model.db.intents[i]["fence"] > s.model.db.attempts[a]["fence"]
    scenarios.append(("lease_takeover_vs_commit_with_clock", m, [
        Operation("takeover", "acquire", (i, "worker-2")), Operation("commit", "commit", (a, v, "commit"), registry_mode="shared"),
        Operation("clock", "advance_time", (20,), registry_mode="none", user_lock=False)], takeover_oracle))
    return scenarios


def boundary_scenarios():
    scenarios = []
    for action in ("issue", "start", "publish"):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        if action == "issue":
            op = Operation(action, "commit", (a, v, "commit"), registry_mode="shared")
        elif action == "start":
            auth = m.commit(a, v, "commit")["authorization"]
            op = Operation(action, "start", (auth, "start"), registry_mode="shared")
        else:
            f = m.build_factset(); m.complete_factset(f); m.seal_factset(f)
            p = m.compute_projection(f)
            op = Operation(action, "publish", (f, [p]), registry_mode="shared")
        def oracle(s, action=action):
            assert s.results[action] in {"OK", "ARTIFACT_REVOKED"}
            events = [e["kind"] for e in s.model.db.event_log]
            if s.results[action] == "OK":
                event = {"issue": "PLAN_COMMITTED", "start": "SESSION_STARTED", "publish": "MANIFEST_PUBLISHED"}[action]
                assert max(i for i, e in enumerate(events) if e == event) < events.index("ARTIFACT_REVOKED")
            for auth in s.model.db.authorizations:
                try: s.model.executable(auth)
                except Rejected as exc: assert exc.code == "ARTIFACT_REVOKED"
                else: raise AssertionError("revoked artifact remains executable")
        scenarios.append(("artifact_revoke_vs_" + action, m, [op,
            Operation("revoke", "revoke_artifact", ("policy-v1", "emergency"), registry_mode="exclusive", user_lock=False)], oracle))

    m, _ = seeded_model()
    e = m.receive("new-fact", {"actual_sets": 2, "actual_upper": 2}); m.associate(e, ["workout-2"])
    f = m.build_factset(); m.complete_factset(f)
    old = m.db.current_factset
    def seal_oracle(s):
        if s.results["seal"] == "OK":
            assert s.model.db.factsets[f]["frontier"] < s.model.db.frontier
        else:
            assert s.results["seal"] == "BUILD_STALE"
            assert s.model.db.current_factset == old
    scenarios.append(("factset_seal_vs_input_update", m, [Operation("seal", "seal_factset", (f,)),
        Operation("input", "accept_fact", (e, 2, 2))], seal_oracle))

    m, _ = seeded_model(); _, a, v = ready_plan(m)
    auth = m.commit(a, v, "commit", requested_until=7)["authorization"]
    def expiry_oracle(s):
        if s.results["start"] == "OK":
            assert s.model.db.bindings[-1]["at"] < 7
        else: assert s.results["start"] == "AUTH_EXPIRED"
    scenarios.append(("dependency_expiry_vs_start", m, [Operation("start", "start", (auth, "start"), registry_mode="shared"),
        Operation("clock", "advance_time", (7,), registry_mode="none", user_lock=False)], expiry_oracle))
    return scenarios


def run_all():
    return [explore(*scenario) for scenario in critical_scenarios() + boundary_scenarios()]
