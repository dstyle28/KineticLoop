from dataclasses import replace
from typing import Any
from uuid import UUID

import pytest

from kineticloop.protocol.factsets import (
    EvidenceBasis,
    Factset,
    FactsetError,
    Member,
    completion_certificate,
    digest,
    reconstruct,
    storage_plan,
)


def uid(n: int) -> UUID:
    return UUID(int=n)


def test_full_delta_reconstruction_and_digest() -> None:
    basis = EvidenceBasis((uid(12),), (uid(13), uid(113)), (), "cutoff-1", "ALL")
    association = Member("ASSOCIATION", "unresolved", "ALL", uid(12))
    admission = Member("ADMISSION", "denied", "ALL", uid(13))
    contrary = Member("ADMISSION", "contrary", "ALL", uid(113))
    fact = Member("FACT", "actual", "CURRENT", uid(14))
    full = Factset(
        uid(15),
        uid(1),
        "BUILDING",
        "FULL",
        None,
        0,
        4,
        (fact, association, contrary, admission),
        basis,
    )
    base = reconstruct(full, {}, max_depth=1)
    sealed = replace(
        full,
        status="SEALED",
        membership_digest=base.membership_digest,
        member_count=base.member_count,
    )
    delta = Factset(
        uid(115),
        uid(1),
        "BUILDING",
        "DELTA",
        full.id,
        1,
        2,
        (
            replace(fact, operation="REMOVE", revision_id=None),
            Member("FACT", "replacement", "CURRENT", uid(114)),
        ),
        basis,
    )
    value = reconstruct(delta, {full.id: sealed}, max_depth=1)
    checkpoint = replace(full, id=uid(215), members=tuple(reversed(value.members)))
    assert reconstruct(checkpoint, {}, max_depth=1) == value
    assert value.member_count == 4
    assert {m.revision_id for m in value.members} == {uid(12), uid(13), uid(113), uid(114)}
    assert storage_plan(sealed, 1) == ("DELTA", sealed.id, 1)
    delta_sealed = replace(
        delta,
        status="SEALED",
        membership_digest=value.membership_digest,
        member_count=value.member_count,
    )
    assert storage_plan(delta_sealed, 1) == ("FULL", None, 0)
    compact = replace(checkpoint, members=(), checkpoint=value.members, member_revision=0)
    assert reconstruct(compact, {}, max_depth=1) == value
    for parents, pattern in (
        ({}, "missing"),
        ({full.id: replace(sealed, subject_id=uid(2))}, "foreign"),
        ({full.id: full}, "unsealed"),
    ):
        with pytest.raises(FactsetError, match=pattern):
            reconstruct(delta, parents, max_depth=1)
    cycle = replace(delta, parent_id=delta.id)
    with pytest.raises(FactsetError):
        reconstruct(cycle, {delta.id: cycle}, max_depth=2)
    with pytest.raises(FactsetError, match="ADMISSION"):
        reconstruct(replace(full, members=(fact, association, admission)), {}, max_depth=1)
    with pytest.raises(FactsetError, match="closed digest"):
        reconstruct(replace(sealed, membership_digest="wrong"), {}, max_depth=1, canonical=True)
    with pytest.raises(FactsetError, match="unsealed"):
        reconstruct(full, {}, max_depth=1, canonical=True)
    with pytest.raises(FactsetError, match="depth"):
        reconstruct(delta, {full.id: sealed}, max_depth=0)
    with pytest.raises(FactsetError, match="duplicate"):
        reconstruct(replace(full, members=(fact, fact)), {}, max_depth=1)
    assert replace(full, basis=replace(basis, knowledge_boundary="cutoff-2")) != full
    assert (
        reconstruct(
            replace(full, basis=replace(basis, knowledge_boundary="cutoff-2")), {}, max_depth=1
        ).membership_digest
        != base.membership_digest
    )

    certificate_payload = {
        "builder_identity": "test:builder",
        "captured_input_frontier": "f1",
        "captured_epoch": 0,
        "program_revision_id": str(uid(6)),
        "policy_id": str(uid(5)),
        "mapping_revision_id": None,
        "parent_factset_id": None,
        "max_delta_depth": 1,
        "domain_basis_digest": digest(basis.payload()),
    }
    certificate_args: dict[str, Any] = dict(
        subject_id=uid(1),
        build_id=full.id,
        member_revision=4,
        membership_digest=base.membership_digest,
        member_count=4,
        payload=certificate_payload,
    )
    certificate = completion_certificate(**certificate_args)
    assert completion_certificate(**(certificate_args | {"member_revision": 5})) != certificate
    assert (
        completion_certificate(
            **(
                certificate_args
                | {"payload": certificate_payload | {"domain_basis_digest": "changed-basis"}}
            )
        )
        != certificate
    )
    assert completion_certificate(**(certificate_args | {"member_count": 3})) != certificate


@pytest.mark.parametrize(
    "kind,key,scope,revision,operation",
    [
        ("PLANNED", "a", "s", uid(1), "SET"),
        ("FACT", "", "s", uid(1), "SET"),
        ("FACT", "a", "s", None, "SET"),
        ("FACT", "a", "s", uid(1), "REMOVE"),
    ],
)
def test_invalid_members(
    kind: str, key: str, scope: str, revision: UUID | None, operation: str
) -> None:
    with pytest.raises(FactsetError):
        Member(kind, key, scope, revision, operation)  # type: ignore[arg-type]
