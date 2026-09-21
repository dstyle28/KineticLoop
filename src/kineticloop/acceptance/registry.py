"""Build the acceptance registry from the repository's indexed current sources."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Mapping, Sequence, cast

Layer = Literal["PU", "DC", "WF", "E2E"]
ObligationKind = Literal["ORIGINAL", "BOUNDARY", "INTERLEAVING", "INTEGRATION"]

_LAYERS = frozenset({"PU", "DC", "WF", "E2E"})
_DEFAULT_STATUS: Final[Literal["NOT_RUN"]] = "NOT_RUN"


class RegistryValidationError(ValueError):
    """Raised when indexed requirement sources cannot produce a safe registry."""


@dataclass(frozen=True)
class Obligation:
    """One tracked acceptance obligation or stable supplemental requirement."""

    obligation_id: str
    requirement_id: str
    kind: ObligationKind
    layer: Layer | None
    required_layers: tuple[Layer, ...]
    specification: Mapping[str, Any]
    status: Literal["NOT_RUN"] = _DEFAULT_STATUS

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "requirement_id": self.requirement_id,
            "kind": self.kind,
            "layer": self.layer,
            "required_layers": list(self.required_layers),
            "status": self.status,
            "specification": dict(self.specification),
        }


@dataclass(frozen=True)
class AcceptanceRegistry:
    """Validated registry plus the exact source identities used to derive it."""

    requirement_set_id: str
    source_bindings: tuple[Mapping[str, str], ...]
    obligations: tuple[Obligation, ...]

    def to_dict(self) -> dict[str, Any]:
        counts = {
            kind.lower(): sum(obligation.kind == kind for obligation in self.obligations)
            for kind in ("ORIGINAL", "BOUNDARY", "INTERLEAVING", "INTEGRATION")
        }
        counts["total"] = len(self.obligations)
        return {
            "schema_version": "1.0",
            "requirement_set_id": self.requirement_set_id,
            "status": _DEFAULT_STATUS,
            "source_bindings": [dict(binding) for binding in self.source_bindings],
            "counts": counts,
            "obligations": [obligation.to_dict() for obligation in self.obligations],
        }


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise RegistryValidationError(f"{context} must be an object")
    return cast(Mapping[str, Any], value)


def _sequence(value: Any, context: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise RegistryValidationError(f"{context} must be an array")
    return cast(Sequence[Any], value)


def _string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise RegistryValidationError(f"{context} must be a non-empty string")
    return value


def _layers(value: Any, context: str) -> tuple[Layer, ...]:
    raw_layers = [_string(layer, f"{context} layer") for layer in _sequence(value, context)]
    _require_unique(raw_layers, context)
    if not raw_layers:
        raise RegistryValidationError(f"{context} must declare at least one layer")
    unknown = [layer for layer in raw_layers if layer not in _LAYERS]
    if unknown:
        raise RegistryValidationError(f"{context} has unknown layers: {unknown}")
    return cast(tuple[Layer, ...], tuple(raw_layers))


def _require_unique(values: Sequence[str], context: str) -> None:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    if duplicates:
        raise RegistryValidationError(f"{context} contains duplicate values: {duplicates}")


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, json.JSONDecodeError) as error:
        raise RegistryValidationError(f"cannot parse {path}: {error}") from error


def _source_path(repository_root: Path, relative_path: str) -> Path:
    root = repository_root.resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise RegistryValidationError(f"source path escapes repository root: {relative_path}")
    if not path.is_file():
        raise RegistryValidationError(f"indexed requirement source does not exist: {relative_path}")
    return path


def _load_sources(
    repository_root: Path, requirement_set: Mapping[str, Any]
) -> tuple[tuple[Mapping[str, str], ...], Mapping[str, Any], Mapping[str, Any]]:
    source_rows = _sequence(requirement_set.get("sources"), "requirement set sources")
    paths: list[str] = []
    bindings: list[Mapping[str, str]] = []
    acceptance_source: Mapping[str, Any] | None = None
    integration_source: Mapping[str, Any] | None = None

    for index, raw_row in enumerate(source_rows):
        row = _mapping(raw_row, f"requirement set source {index}")
        relative_path = _string(row.get("path"), f"requirement set source {index} path")
        expected_hash = _string(row.get("sha256"), f"requirement set source {index} sha256")
        paths.append(relative_path)
        path = _source_path(repository_root, relative_path)
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            raise RegistryValidationError(
                f"indexed hash mismatch for {relative_path}: expected {expected_hash}, got {actual_hash}"
            )
        source = _read_json(path)
        if "original_tests" in source:
            if acceptance_source is not None:
                raise RegistryValidationError("multiple original acceptance sources are indexed")
            acceptance_source = source
            kind = "acceptance"
        elif "requirements" in source:
            if integration_source is not None:
                raise RegistryValidationError("multiple integration acceptance sources are indexed")
            integration_source = source
            kind = "integration"
        else:
            raise RegistryValidationError(f"unrecognized requirement source shape: {relative_path}")
        bindings.append({"path": relative_path, "sha256": actual_hash, "kind": kind})

    _require_unique(paths, "requirement set source paths")
    if acceptance_source is None or integration_source is None:
        raise RegistryValidationError(
            "requirement set must index one original and one integration acceptance source"
        )
    return tuple(bindings), acceptance_source, integration_source


def _expected_ids(requirement_set: Mapping[str, Any], key: str) -> list[str]:
    obligations = _mapping(requirement_set.get("obligations"), "requirement set obligations")
    ids = [
        _string(value, f"requirement set obligations.{key}")
        for value in _sequence(obligations.get(key), f"requirement set obligations.{key}")
    ]
    _require_unique(ids, f"requirement set obligations.{key}")
    return ids


def _assert_expected(actual: Sequence[str], expected: Sequence[str], context: str) -> None:
    if list(actual) == list(expected):
        return
    missing = [value for value in expected if value not in actual]
    unexpected = [value for value in actual if value not in expected]
    raise RegistryValidationError(
        f"{context} does not match current requirement set; "
        f"missing={missing}, unexpected={unexpected}, order_matches=False"
    )


def _original_obligations(
    acceptance: Mapping[str, Any], requirement_set: Mapping[str, Any]
) -> list[Obligation]:
    raw_tests = _sequence(acceptance.get("original_tests"), "original_tests")
    tests: dict[str, tuple[Mapping[str, Any], tuple[Layer, ...]]] = {}
    expanded: list[str] = []
    for index, raw_test in enumerate(raw_tests):
        test = _mapping(raw_test, f"original_tests[{index}]")
        test_id = _string(test.get("test_id"), f"original_tests[{index}].test_id")
        if test_id in tests:
            raise RegistryValidationError(f"duplicate original test ID: {test_id}")
        layers = _layers(test.get("layers"), f"original test {test_id} layers")
        tests[test_id] = (test, layers)
        expanded.extend(f"{test_id}@{layer}" for layer in layers)

    declared_rows = _sequence(
        acceptance.get("original_layer_obligations"), "original_layer_obligations"
    )
    declared_ids: list[str] = []
    obligations: list[Obligation] = []
    for index, raw_row in enumerate(declared_rows):
        row = _mapping(raw_row, f"original_layer_obligations[{index}]")
        obligation_id = _string(
            row.get("obligation_id"), f"original_layer_obligations[{index}].obligation_id"
        )
        requirement_id = _string(
            row.get("test_id"), f"original_layer_obligations[{index}].test_id"
        )
        layer = _layers([row.get("layer")], f"original obligation {obligation_id} layer")[0]
        if obligation_id != f"{requirement_id}@{layer}":
            raise RegistryValidationError(f"malformed original obligation ID: {obligation_id}")
        if requirement_id not in tests:
            raise RegistryValidationError(
                f"original obligation {obligation_id} refers to unknown test {requirement_id}"
            )
        test, required_layers = tests[requirement_id]
        declared_ids.append(obligation_id)
        obligations.append(
            Obligation(
                obligation_id=obligation_id,
                requirement_id=requirement_id,
                kind="ORIGINAL",
                layer=layer,
                required_layers=required_layers,
                specification={
                    "given": test.get("given"),
                    "when": test.get("when"),
                    "then": test.get("then"),
                    "primary_tables": test.get("primary_tables"),
                },
            )
        )

    _require_unique(declared_ids, "original layer obligation IDs")
    _assert_expected(declared_ids, expanded, "original layer declarations")
    _assert_expected(
        declared_ids,
        _expected_ids(requirement_set, "original_layer_obligations"),
        "original layer obligations",
    )
    declared_count = acceptance.get("original_layer_obligation_count")
    if declared_count != len(declared_ids):
        raise RegistryValidationError(
            "original_layer_obligation_count does not match derived obligation count"
        )
    return obligations


def _supplemental_obligations(
    acceptance: Mapping[str, Any],
    requirement_set: Mapping[str, Any],
    *,
    source_key: str,
    expected_key: str,
    kind: Literal["BOUNDARY", "INTERLEAVING"],
) -> list[Obligation]:
    rows = _sequence(acceptance.get(source_key), source_key)
    ids: list[str] = []
    obligations: list[Obligation] = []
    for index, raw_row in enumerate(rows):
        row = _mapping(raw_row, f"{source_key}[{index}]")
        requirement_id = _string(row.get("requirement_id"), f"{source_key}[{index}].requirement_id")
        layers = _layers(row.get("layers"), f"{kind.lower()} {requirement_id} layers")
        ids.append(requirement_id)
        if kind == "BOUNDARY":
            specification = {
                "given": row.get("given"),
                "when": row.get("when"),
                "then": row.get("then"),
                "primary_tables": row.get("primary_tables"),
            }
        else:
            specification = {"scenario": row.get("scenario")}
        obligations.append(
            Obligation(
                obligation_id=requirement_id,
                requirement_id=requirement_id,
                kind=kind,
                layer=None,
                required_layers=layers,
                specification=specification,
            )
        )
    _require_unique(ids, f"{kind.lower()} requirement IDs")
    _assert_expected(ids, _expected_ids(requirement_set, expected_key), f"{kind.lower()} requirements")
    return obligations


def _integration_obligations(
    integration: Mapping[str, Any], requirement_set: Mapping[str, Any]
) -> list[Obligation]:
    rows = _sequence(integration.get("requirements"), "integration requirements")
    requirement_ids: list[str] = []
    obligation_ids: list[str] = []
    obligations: list[Obligation] = []
    for index, raw_row in enumerate(rows):
        row = _mapping(raw_row, f"integration requirements[{index}]")
        requirement_id = _string(row.get("id"), f"integration requirements[{index}].id")
        if requirement_id in requirement_ids:
            raise RegistryValidationError(f"duplicate integration requirement ID: {requirement_id}")
        requirement_ids.append(requirement_id)
        layers = _layers(row.get("layers"), f"integration requirement {requirement_id} layers")
        for layer in layers:
            obligation_id = f"{requirement_id}@{layer}"
            obligation_ids.append(obligation_id)
            obligations.append(
                Obligation(
                    obligation_id=obligation_id,
                    requirement_id=requirement_id,
                    kind="INTEGRATION",
                    layer=layer,
                    required_layers=layers,
                    specification={"name": row.get("name"), "assertion": row.get("assertion")},
                )
            )
    _require_unique(obligation_ids, "integration layer obligation IDs")
    _assert_expected(
        obligation_ids,
        _expected_ids(requirement_set, "integration_layer_obligations"),
        "integration layer obligations",
    )
    return obligations


def build_registry(repository_root: Path) -> AcceptanceRegistry:
    """Derive and validate the registry from ``CURRENT_REQUIREMENT_SET.json``."""

    requirement_set_path = repository_root / "CURRENT_REQUIREMENT_SET.json"
    requirement_set = _read_json(requirement_set_path)
    if requirement_set.get("status") != "CURRENT":
        raise RegistryValidationError("CURRENT_REQUIREMENT_SET.json must have status CURRENT")
    requirement_set_id = _string(
        requirement_set.get("requirement_set_id"), "requirement_set_id"
    )
    bindings, acceptance, integration = _load_sources(repository_root, requirement_set)
    obligations = [
        *_original_obligations(acceptance, requirement_set),
        *_supplemental_obligations(
            acceptance,
            requirement_set,
            source_key="supplemental_boundary_requirements",
            expected_key="boundary_requirements",
            kind="BOUNDARY",
        ),
        *_supplemental_obligations(
            acceptance,
            requirement_set,
            source_key="interleaving_requirements",
            expected_key="interleaving_requirements",
            kind="INTERLEAVING",
        ),
        *_integration_obligations(integration, requirement_set),
    ]
    _require_unique(
        [obligation.obligation_id for obligation in obligations], "registry obligation IDs"
    )
    return AcceptanceRegistry(
        requirement_set_id=requirement_set_id,
        source_bindings=bindings,
        obligations=tuple(obligations),
    )
