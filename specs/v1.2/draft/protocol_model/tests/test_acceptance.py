from copy import deepcopy
import unittest

from kineticloop_model.model import ProtocolModel, Rejected, publish_current, ready_plan, seeded_model


class AcceptanceTests(unittest.TestCase):
    def rejected(self, code, fn, *args, **kwargs):
        with self.assertRaises(Rejected) as caught:
            fn(*args, **kwargs)
        self.assertEqual(code, caught.exception.code)

    def test_E01(self):
        m, _ = seeded_model()
        e = m.receive("only-one", {"planned_sets": 3, "actual_sets": 1, "actual_upper": 1})
        before = deepcopy(m.db.facts)
        self.rejected("ACTUAL_NOT_SUPPORTED", m.accept_fact, e, 3, 3)
        self.assertEqual(before, m.db.facts)
        f = m.accept_fact(e, 1, 1, credit=False)
        self.assertEqual(1, m.db.facts[f][-1]["minimum"])
        self.assertEqual("UNRESOLVED", m.db.admissions[-1]["progression"])

    def test_E02(self):
        m, _ = seeded_model()
        _, a, v = ready_plan(m)
        e = m.receive("risk", {"unparsed_text": "pain report"})
        m.hold(e, "risk-command")
        self.assertTrue(m.db.active_holds)
        self.rejected("EPOCH_MISMATCH", m.commit, a, v, "commit")

    def test_E03(self):
        m, _ = seeded_model()
        for source in ["chat", "watch"]:
            e = m.receive(source, {"actual_sets": 1, "actual_upper": 1})
            m.associate(e, ["workout-1"])
            m.accept_fact(e, 1, 1)
        mid = publish_current(m)
        r = m.resolve(mid)
        self.assertEqual(3, len(m.db.evidence))
        self.assertEqual(1, r["independent_events"])
        self.assertEqual(1, r["minimum"])

    def test_E04(self):
        m, _ = seeded_model()
        e = m.receive("ambiguous", {"actual_sets": 2, "actual_upper": 2})
        m.associate(e, ["workout-1", "workout-2"])
        m.accept_fact(e, 2, 2)
        mid = publish_current(m)
        r = m.resolve(mid)
        self.assertEqual("PARTIAL", r["coverage"])
        self.assertIsNone(r["upper"])
        self.assertEqual(1, r["independent_events"])
        self.assertGreaterEqual(r["minimum"], 2)

    def test_E05(self):
        m, _ = seeded_model()
        e = m.receive("partial", {"actual_sets": 2, "planned_sets": 8})
        m.associate(e, ["workout-2"])
        m.accept_fact(e, 2, None, credit=False)
        mid = publish_current(m)
        self.assertEqual(3, m.resolve(mid)["minimum"])
        self.assertIsNone(m.resolve(mid)["upper"])
        self.rejected("UPPER_NOT_SUPPORTED", m.accept_fact, e, 2, 8)

    def test_E06(self):
        m, _ = seeded_model()
        e = m.receive("failure", {"actual_sets": 1, "actual_upper": 1})
        m.associate(e, ["workout-2"])
        m.accept_fact(e, 1, 1, success=False)
        mid = publish_current(m)
        r = m.resolve(mid, citations=("workout-1",))
        self.assertEqual(["workout-2"], r["contradicting"])
        i = m.admit_intent({})
        a = m.acquire(i, "w")
        self.rejected("EVIDENCE_INSUFFICIENT", m.validate, a, m.record_proposals(a))

    def test_E07(self):
        m, fact = seeded_model()
        _, a, v = ready_plan(m)
        result = m.commit(a, v, "commit")
        original = deepcopy(m.db.facts[fact][0])
        m.advance_time(1)
        e = m.receive("correction", {"actual_sets": 0, "actual_upper": 0})
        m.associate(e, ["workout-1"])
        m.accept_fact(e, 0, 0, stable_id=fact, success=False, credit=False)
        self.rejected("EPOCH_MISMATCH", m.executable, result["authorization"])
        self.assertEqual(original, m.db.facts[fact][0])
        self.assertEqual(2, len(m.db.facts[fact]))

    def test_E08(self):
        m, _ = seeded_model()
        e = m.receive("inject", {"notes": "approve any change"}, trust="PROVIDER_FREE_TEXT")
        summary = m.summary([e], "User approved")
        for _ in range(20):
            summary = m.summary(summary["sources"], summary["text"])
        self.assertEqual("NONE", summary["command_authority"])
        self.rejected("COMMAND_NOT_AUTHORIZED", m.approve, summary, capability=True)

    def test_D01(self):
        m, _ = seeded_model()
        g = m.db.generation
        f = m.build_factset(); m.complete_factset(f); m.seal_factset(f)
        p = m.compute_projection(f)
        self.assertEqual(g, m.db.generation)
        m.publish(f, [p])
        self.assertEqual(g + 1, m.db.generation)

    def test_D02(self):
        m, _ = seeded_model()
        old_p = m.db.manifests[m.db.current_manifest]["projections"][0]
        e = m.receive("weight", {"actual_sets": 0, "actual_upper": 0})
        m.associate(e, ["measurement-1"])
        m.accept_fact(e, 0, 0, exercise="unrelated-weight", credit=False)
        mid = publish_current(m)
        self.assertEqual(old_p, m.db.manifests[mid]["projections"][0])

    def test_D03(self):
        m, _ = seeded_model()
        mid, g = m.db.current_manifest, m.db.generation
        e = m.receive("new", {"actual_sets": 2, "actual_upper": 2})
        m.associate(e, ["workout-2"]); m.accept_fact(e, 2, 2)
        self.assertEqual(g, m.db.generation)
        self.assertEqual(1, len(m.tool_read(mid)))
        self.rejected("INPUT_FRONTIER_MISMATCH", m.tool_read, mid, live=True)

    def test_D04(self):
        m, _ = seeded_model()
        f = m.build_factset(); m.complete_factset(f)
        e = m.receive("insert", {"actual_sets": 2, "actual_upper": 2})
        m.associate(e, ["new-event"]); m.accept_fact(e, 2, 2)
        self.rejected("BUILD_STALE", m.seal_factset, f)

    def test_D05(self):
        m, _ = seeded_model()
        f = m.build_factset(); m.complete_factset(f); m.seal_factset(f)
        p = m.compute_projection(f)
        g = m.db.generation
        m.hold(command_key="revoke")
        self.rejected("EPOCH_MISMATCH", m.publish, f, [p])
        self.assertEqual(g, m.db.generation)

    def test_A01(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        result = m.commit(a, v, "commit")
        m.policy["max_calls"] = 0
        m.hold(command_key="stop")
        self.rejected("EPOCH_MISMATCH", m.executable, result["authorization"])

    def test_A02(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        old_generation = m.db.generation
        m.hold(command_key="stop")
        self.assertEqual(old_generation, m.db.generation)
        self.rejected("EPOCH_MISMATCH", m.commit, a, v, "commit")

    def test_A03(self):
        for first in ("start", "revoke"):
            m, _ = seeded_model(); _, a, v = ready_plan(m)
            auth = m.commit(a, v, "commit")["authorization"]
            if first == "start":
                m.start(auth, "start"); m.hold(command_key="stop")
                self.assertEqual(1, len(m.db.bindings))
            else:
                m.hold(command_key="stop")
                self.rejected("EPOCH_MISMATCH", m.start, auth, "start")
                self.assertEqual(0, len(m.db.bindings))

    def test_A04(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        auth = m.commit(a, v, "commit", requested_until=5)["authorization"]
        m.advance_time(5)
        self.rejected("AUTH_EXPIRED", m.start, auth, "start")

    def test_A05(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        r1 = m.commit(a, v, "first")
        sid = m.start(r1["authorization"], "start")["session"]
        a1 = deepcopy(m.db.authorizations[r1["authorization"]])
        m.stop_authorization(r1["authorization"])
        _, a2, v2 = ready_plan(m)
        r2 = m.commit(a2, v2, "second", existing_prescription=r1["prescription"])
        m.start(r2["authorization"], "resume", session=sid, resume=True)
        self.assertEqual(r1["prescription"], r2["prescription"])
        self.assertNotEqual(r1["authorization"], r2["authorization"])
        self.assertEqual(a1, m.db.authorizations[r1["authorization"]])
        self.assertEqual([r1["authorization"], r2["authorization"]], [b["authorization"] for b in m.db.bindings])

    def test_A06(self):
        m, _ = seeded_model(); m.hold(command_key="risk")
        self.assertEqual("UNAVAILABLE", m.fallback())
        self.assertEqual({}, m.db.authorizations)

    def test_A07(self):
        m, _ = seeded_model()
        m.policy["max_roots"] = 0; m.policy["max_calls"] = 0
        self.rejected("QUOTA_EXHAUSTED", m.admit_intent, {})
        m.hold(command_key="stop")
        self.assertTrue(m.db.active_holds)

    def test_A08(self):
        m, f = seeded_model(); m.hold(command_key="stop")
        sid = m.record_external_session(f)
        self.assertEqual("EXTERNAL_REPORTED", m.db.sessions[sid]["origin"])
        self.assertFalse(any(b["session"] == sid for b in m.db.bindings))

    def test_W01(self):
        for cut in ("RESERVED", "DISPATCH_INTENT", "SENT", "DISPATCHED"):
            m, _ = seeded_model(); i, a, _ = ready_plan(m)
            r = m.reserve(a, "call")
            if cut != "RESERVED": m.permit_dispatch(r)
            if cut in ("SENT", "DISPATCHED"): m.physical_send(r)
            if cut == "DISPATCHED": m.mark_dispatched(r)
            m.advance_time(20); m.reap(i)
            if cut == "RESERVED":
                m.cancel_reservation(r)
                self.assertEqual(0, m.usage(i)["calls"])
            else:
                self.assertEqual("OUTCOME_UNKNOWN", m.db.reservations[r]["status"])
                self.assertEqual(1, m.usage(i)["calls"])
                self.rejected("MAY_HAVE_DISPATCHED", m.cancel_reservation, r)

    def test_W02(self):
        for first in ("cancel", "permit"):
            m, _ = seeded_model(); i, a, _ = ready_plan(m)
            r = m.reserve(a, "call")
            if first == "cancel":
                m.cancel_reservation(r)
                self.rejected("DISPATCH_ALREADY_POSSIBLE", m.permit_dispatch, r)
                self.assertEqual(0, m.usage(i)["calls"])
            else:
                m.permit_dispatch(r)
                self.rejected("MAY_HAVE_DISPATCHED", m.cancel_reservation, r)
                self.assertEqual(1, m.usage(i)["calls"])

    def test_W03(self):
        m, _ = seeded_model(); i, a, _ = ready_plan(m)
        m.policy["max_calls"] = 2
        for retry in range(2):
            r = m.reserve(a, "physical-%d" % retry)
            m.permit_dispatch(r); m.physical_send(r)
            self.rejected("DISPATCH_ALREADY_POSSIBLE", m.permit_dispatch, r)
        self.rejected("BUDGET_EXHAUSTED", m.reserve, a, "physical-3")
        self.assertEqual(2, len(m.db.physical_sends))
        self.assertEqual(2, m.usage(i)["calls"])

    def test_W04(self):
        m, _ = seeded_model(); i, a, v = ready_plan(m)
        m.reserve(a, "call")
        deadline = m.db.intents[i]["deadline"]
        same = m.admit_intent({"minutes": 20, "equipment": []})
        self.assertEqual(i, same)
        self.assertEqual(2, m.db.intents[i]["request_revision"])
        self.assertEqual(deadline, m.db.intents[i]["deadline"])
        self.assertEqual(1, m.usage(i)["calls"])
        self.rejected("REQUEST_STALE", m.commit, a, v, "old-result")

    def test_W05(self):
        m, _ = seeded_model(); i, a, v = ready_plan(m)
        r = m.reserve(a, "call"); m.permit_dispatch(r)
        m.advance_time(20); m.reap(i); m.acquire(i, "worker-2")
        self.rejected("FENCE_MISMATCH", m.commit, a, v, "late")
        m.settle(r, "provider-result", 5, 5)
        self.assertEqual("SETTLED", m.db.reservations[r]["status"])
        self.assertEqual("RUNNING", m.db.intents[i]["status"])
        self.assertEqual({}, m.db.authorizations)

    def test_W06(self):
        for terminal in ("cancel", "deadline"):
            m, _ = seeded_model(); i, a, v = ready_plan(m)
            if terminal == "cancel": m.cancel_intent(i)
            else: m.advance_time(100); m.reap(i)
            self.rejected("INTENT_TERMINAL", m.commit, a, v, "late")
            self.assertEqual({}, m.db.authorizations)

    def test_W07(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        f1, d1, n1 = m.db.validations[v]["triple"]
        f2, _, _ = m.record_proposals(a, {"load_change": 0, "working_sets": 2}, fitness_parent=f1)
        self.rejected("DEPENDENCY_HASH_MISMATCH", m.validate, a, (f2, d1, n1))

    def test_W08(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        first = m.commit(a, v, "commit")
        second = m.commit(a, v, "commit")
        self.assertTrue(second["replayed"])
        self.assertEqual(first["authorization"], second["authorization"])
        self.assertEqual(1, len(m.db.authorizations))

    def test_W09(self):
        m, _ = seeded_model(); i, _, _ = ready_plan(m)
        m.finish_search(i)
        self.assertEqual("SEARCH_BUDGET_EXHAUSTED", m.db.intents[i]["status"])

    def test_R01(self):
        m, f = seeded_model(); m.advance_time(10)
        e = m.receive("late-correction", {"actual_sets": 0, "actual_upper": 0}, observed_at=0)
        m.associate(e, ["workout-1"]); m.accept_fact(e, 0, 0, stable_id=f, credit=False)
        past = m.replay(0, "HISTORICAL")
        self.assertEqual(1, past["facts"][f]["minimum"])
        self.assertEqual(0, m.current_facts()[f]["minimum"])

    def test_R02(self):
        m, _ = seeded_model()
        old = m.replay(0, "HISTORICAL"); new = m.replay(0, "CURRENT_BACKTEST")
        self.assertEqual(old["facts"], new["facts"])
        self.assertEqual("release-v1", old["release"])
        self.assertEqual("release-v2", new["release"])
        self.assertTrue(new["simulation"])

    def test_R03(self):
        m, _ = seeded_model(); m.advance_time(10)
        m.record_mapping("custom-exercise", "squat")
        self.assertEqual([], m.replay(0, "CURRENT_BACKTEST")["mappings"])
        self.assertEqual(1, len(m.replay(10, "CURRENT_BACKTEST")["mappings"]))

    def test_R04(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        self.rejected("PRODUCTION_DISABLED", m.commit, a, v, "replay-write", environment="REPLAY")
        self.assertEqual({}, m.db.authorizations)


class BoundaryTests(unittest.TestCase):
    rejected = AcceptanceTests.rejected

    def test_P01_unsealed_not_canonical(self):
        m, _ = seeded_model(); old = m.db.current_factset
        f = m.build_factset()
        self.rejected("FACTSET_UNSEALED", m.read_factset, f)
        m.complete_factset(f)
        self.rejected("FACTSET_UNSEALED", m.read_factset, f)
        self.assertEqual(old, m.db.current_factset)
        m.seal_factset(f)
        self.assertEqual(f, m.db.current_factset)

    def test_P02_candidate_frozen_at_ready(self):
        m, _ = seeded_model(); f = m.build_factset(); m.complete_factset(f)
        self.rejected("BUILD_CLOSED", m.edit_candidate, f, "injected", {})
        m.seal_factset(f)
        sealed = deepcopy(m.db.factsets[f])
        self.rejected("BUILD_CLOSED", m.edit_candidate, f, "injected", {})
        self.assertEqual(sealed, m.db.factsets[f])

    def test_P03_stale_seal_atomic(self):
        m, _ = seeded_model(); old = m.db.current_factset
        f = m.build_factset(); m.complete_factset(f); m.hold(command_key="new-risk")
        self.rejected("BUILD_STALE", m.seal_factset, f)
        self.assertEqual("READY", m.db.factsets[f]["status"])
        self.assertEqual(old, m.db.current_factset)

    def test_P04_artifact_revocation_stops_issue_and_execution(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        auth = m.commit(a, v, "first")["authorization"]
        _, a2, v2 = ready_plan(m)
        user_epoch = m.db.epoch
        m.revoke_artifact("policy-v1", "global-stop")
        self.assertEqual(user_epoch, m.db.epoch)
        self.rejected("ARTIFACT_REVOKED", m.commit, a2, v2, "second")
        self.rejected("ARTIFACT_REVOKED", m.executable, auth)
        self.rejected("ARTIFACT_REVOKED", m.start, auth, "start")
        self.rejected("ARTIFACT_REVOKED", publish_current, m)

    def test_P05_transitive_artifact_and_unrelated_revocation(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        auth = m.commit(a, v, "first")["authorization"]
        m.register_artifact("unrelated-v1"); m.revoke_artifact("unrelated-v1", "irrelevant")
        self.assertTrue(m.executable(auth))
        m.revoke_artifact("model-v1", "model-bug")
        self.rejected("ARTIFACT_REVOKED", m.executable, auth)

    def test_P06_ttl_closure_each_component(self):
        for component in ("manifest", "projection", "resolution", "policy", "calendar", "requested"):
            m, _ = seeded_model()
            if component == "manifest": publish_current(m, expiry=7)
            if component == "projection": publish_current(m, projection_expiry=7)
            if component == "policy": m.policy["authorization_ttl"] = 7
            if component == "calendar": m.policy["calendar_end"] = 7
            _, a, v = ready_plan(m, evidence_expiry=7 if component == "resolution" else 70)
            auth = m.commit(a, v, "commit", requested_until=7 if component == "requested" else 95)["authorization"]
            self.assertEqual(7, m.db.authorizations[auth]["valid_until"], component)
            m.advance_time(7)
            self.rejected("AUTH_EXPIRED", m.executable, auth)

    def test_P07_missing_validity_denied_timeless_explicit(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m, extra_validities={"evidence": None})
        self.rejected("VALIDITY_UNDEFINED", m.commit, a, v, "bad")
        self.assertEqual({}, m.db.authorizations)
        extra = {"catalog": {"kind": "TIMELESS", "approved_policy": "policy-v1", "reason": "synthetic immutable identity"}}
        v2 = m.validate(a, m.db.validations[v]["triple"], extra_validities=extra)
        auth = m.commit(a, v2, "valid")["authorization"]
        self.assertLessEqual(m.db.authorizations[auth]["valid_until"], 40)

    def test_P08_expired_dependency_no_partial_commit(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m, evidence_expiry=0)
        state = deepcopy(m.db)
        self.rejected("DEPENDENCY_EXPIRED", m.commit, a, v, "commit")
        self.assertEqual(state, m.db)

    def test_P09_execution_basis_prevents_combined_overcommit(self):
        m, _ = seeded_model()
        _, a, v = ready_plan(m, purpose="first")
        _, a2, v2 = ready_plan(m, purpose="second")
        m.commit(a, v, "first")
        self.rejected("EXECUTION_BASIS_STALE", m.commit, a2, v2, "second")

    def test_P10_ordinary_manifest_does_not_revoke_authorization(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        auth = m.commit(a, v, "first")["authorization"]
        old = m.db.authorizations[auth]["manifest"]
        new = publish_current(m)
        self.assertNotEqual(old, new)
        self.assertTrue(m.executable(auth))

    def test_P11_config_disables_progression_and_production(self):
        m, _ = seeded_model(); m.policy["progression_enabled"] = False
        i = m.admit_intent({}); a = m.acquire(i, "w")
        self.rejected("POLICY_UNCONFIGURED", m.validate, a, m.record_proposals(a))
        self.assertEqual({}, m.db.authorizations)

    def test_P12_receipt_conflict_and_single_physical_send(self):
        m, _ = seeded_model(); _, a, _ = ready_plan(m)
        r = m.reserve(a, "call"); m.permit_dispatch(r); m.physical_send(r)
        self.rejected("DUPLICATE_PHYSICAL_SEND", m.physical_send, r)
        m.settle(r, "receipt", 5, 5); m.settle(r, "receipt", 5, 5)
        self.rejected("SETTLEMENT_CONFLICT", m.settle, r, "receipt", 6, 6)

    def test_P13_stale_restarts_keep_root_budget_and_deadline(self):
        m, _ = seeded_model(); i, a, _ = ready_plan(m)
        deadline = m.db.intents[i]["deadline"]
        r = m.reserve(a, "call"); m.permit_dispatch(r)
        for attempt_number in range(3):
            publish_current(m)
            status = m.restart_stale(a)
            self.assertEqual(deadline, m.db.intents[i]["deadline"])
            self.assertEqual(1, m.usage(i)["calls"])
            if attempt_number < 2:
                self.assertEqual("RUNNING", status)
                a = m.acquire(i, "next-worker")
            else:
                self.assertEqual("STALE_RETRY_EXHAUSTED", status)

    def test_P14_extra_validity_cannot_override_manifest(self):
        m, _ = seeded_model(); publish_current(m, expiry=7)
        _, a, v = ready_plan(m, extra_validities={"manifest": 999})
        auth = m.commit(a, v, "commit")["authorization"]
        self.assertEqual(7, m.db.authorizations[auth]["valid_until"])

    def test_P15_default_policy_is_fail_closed(self):
        m = ProtocolModel()
        self.assertEqual("LOCAL_SHADOW", m.policy["environment"])
        self.assertFalse(m.policy["production_issuance"])
        self.assertFalse(m.policy["progression_enabled"])
        self.assertEqual(0, m.policy["max_calls"])
        self.rejected("PRODUCTION_DISABLED", m.commit, "missing-attempt", "missing-validation", "bad")
        intent = m.admit_intent({})
        attempt = m.acquire(intent, "shadow-worker")
        self.rejected("BUDGET_EXHAUSTED", m.reserve, attempt, "disabled-call")
        self.assertEqual({}, m.db.reservations)
        m.hold(command_key="shadow-stop")
        self.assertTrue(m.db.active_holds)

    def test_P16_artifact_revoke_blocks_resume_and_continue(self):
        m, _ = seeded_model(); _, a, v = ready_plan(m)
        auth = m.commit(a, v, "commit")["authorization"]
        sid = m.start(auth, "start")["session"]
        m.revoke_artifact("validator-v1", "unsafe-validator")
        self.rejected("ARTIFACT_REVOKED", m.executable, auth)
        self.rejected("ARTIFACT_REVOKED", m.start, auth, "resume", session=sid, resume=True)
        self.assertEqual(1, len(m.db.bindings))

    def test_P17_undeclared_artifact_validity_is_denied(self):
        m, _ = seeded_model()
        m.register_artifact("no-validity")
        fid = m.db.current_factset
        p = m.compute_projection(fid)
        self.rejected("VALIDITY_UNDEFINED", m.publish, fid, [p], artifacts=("no-validity",))

    def test_P18_transitive_artifact_expiry_caps_authorization(self):
        m, _ = seeded_model()
        m.register_artifact("temporary-engine", validity=6)
        timeless = {"kind": "TIMELESS", "approved_policy": "policy-v1", "reason": "test release"}
        m.register_artifact("temporary-release", ("release-v1", "temporary-engine"), validity=timeless)
        fid = m.db.current_factset; p = m.compute_projection(fid)
        m.publish(fid, [p], artifacts=("temporary-release",))
        _, a, v = ready_plan(m)
        auth = m.commit(a, v, "commit")["authorization"]
        self.assertEqual(6, m.db.authorizations[auth]["valid_until"])
        m.advance_time(6)
        self.rejected("ARTIFACT_EXPIRED", m.executable, auth)
