"""Resolve current documents and validate durable evidence handoff metadata.

Authority is deliberately resolved from ``CURRENT_DOCUMENT_INDEX.json`` only.
Filenames, history directories, and display-only task IDs are never authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

DOCUMENT_INDEX = "CURRENT_DOCUMENT_INDEX.json"
EVIDENCE_MANIFEST = "KineticLoop_Evidence_Manifest_v0.1.json"
HISTORICAL_TASK_MAP = "HISTORICAL_TASK_ID_MAP.json"
CURRENT_BACKLOG = "KineticLoop_Harness_Backlog_v0.2.json"
PACKAGE_MANIFEST = "HARNESS_DOCUMENT_MANIFEST.json"

_PACKAGE_BINDINGS = (DOCUMENT_INDEX, HISTORICAL_TASK_MAP, EVIDENCE_MANIFEST)
_LEGACY_NAMESPACE_SOURCES = {
    "project-backlog-v0.3": "docs/history/v1.2.2/KineticLoop_Project_Backlog_v0.3.json",
}
_FREEZE_EVIDENCE_STATUS = "DECLARED_HISTORICAL_EVIDENCE_PARTIALLY_BUNDLED"
_HISTORICAL_RESULTS_STATUS = "UNVERIFIED_HISTORICAL_DECLARATION"
_HISTORICAL_DECLARED_RESULTS = {
    "original_model_cases": "34/34",
    "boundary_cases": "18/18",
    "interleavings": "9/9",
    "complete_schedules": 589,
    "visited_prefixes": 2997,
    "seeded_mutants": "8/8",
}

_DOCUMENT_ID = re.compile(r"DOC-[A-Z0-9][A-Z0-9.-]*\Z")
_TASK_IDENTITY = re.compile(r"([a-z0-9][a-z0-9.-]*)/(KL-[0-9]{3}[A-Z]?)\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class ValidationError(ValueError):
    """Raised when a durable handoff artifact is invalid."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError([f"duplicate-key:{key}"])
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_strict_object)
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError([f"invalid-json:{path.name}:{error}"]) from error
    if not isinstance(value, dict):
        raise ValidationError([f"expected-object:{path.name}"])
    return value


def _relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts)


def _target(root: Path, value: str) -> Path:
    target = (root / value).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError as error:
        raise ValidationError([f"path-escapes-root:{value}"]) from error
    return target


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_file(root: Path, path: object, digest: object, prefix: str) -> list[str]:
    if not _relative_path(path):
        return [f"{prefix}-invalid-path:{path}"]
    assert isinstance(path, str)
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        return [f"{prefix}-invalid-sha256:{path}"]
    target = _target(root, path)
    if not target.is_file():
        return [f"{prefix}-missing:{path}"]
    actual = _sha256(target)
    return [] if actual == digest else [f"{prefix}-hash:{path}:expected={digest}:actual={actual}"]


@dataclass(frozen=True)
class ResolvedDocument:
    document_id: str
    path: str
    sha256: str
    status: str
    absolute_path: Path


class DocumentIndex:
    """Validated, stable-ID-only view of the current document index."""

    def __init__(self, root: Path, records: dict[str, ResolvedDocument]):
        self.root = root.resolve()
        self._records = records

    @classmethod
    def load(cls, root: Path) -> DocumentIndex:
        root = root.resolve()
        data = _load_json(root / DOCUMENT_INDEX)
        errors: list[str] = []
        if data.get("status") != "CURRENT":
            errors.append("document-index-status-not-current")
        documents = data.get("documents")
        machine_readable = data.get("machine_readable")
        history_roots = data.get("history_roots")
        if not isinstance(documents, list) or not documents:
            errors.append("document-index-documents")
            documents = []
        if not isinstance(machine_readable, list):
            errors.append("document-index-machine-readable")
            machine_readable = []
        if not isinstance(history_roots, list) or not all(_relative_path(item) for item in history_roots):
            errors.append("document-index-history-roots")
            history_roots = []

        records: dict[str, ResolvedDocument] = {}
        seen_paths: set[str] = set()
        for entry in documents:
            if not isinstance(entry, dict):
                errors.append("document-index-entry-not-object")
                continue
            document_id = entry.get("document_id")
            path = entry.get("path")
            digest = entry.get("sha256")
            status = entry.get("status")
            if not isinstance(document_id, str) or not _DOCUMENT_ID.fullmatch(document_id):
                errors.append(f"document-index-invalid-id:{document_id}")
                continue
            if document_id in records:
                errors.append(f"document-index-duplicate-id:{document_id}")
                continue
            if not _relative_path(path):
                errors.append(f"document-index-invalid-path:{path}")
                continue
            assert isinstance(path, str)
            if path in seen_paths:
                errors.append(f"document-index-duplicate-path:{path}")
            if any(path == history or path.startswith(history + "/") for history in history_roots):
                errors.append(f"document-index-current-points-to-history:{document_id}:{path}")
            if status not in ("CURRENT", "FROZEN"):
                errors.append(f"document-index-invalid-status:{document_id}:{status}")
            errors.extend(_validate_file(root, path, digest, "document-index"))
            if isinstance(digest, str) and isinstance(status, str):
                records[document_id] = ResolvedDocument(
                    document_id=document_id,
                    path=path,
                    sha256=digest,
                    status=status,
                    absolute_path=_target(root, path),
                )
            seen_paths.add(path)

        for entry in machine_readable:
            if not isinstance(entry, dict):
                errors.append("document-index-machine-entry-not-object")
                continue
            path = entry.get("path")
            if isinstance(path, str) and path in seen_paths:
                errors.append(f"document-index-duplicate-path:{path}")
            errors.extend(_validate_file(root, path, entry.get("sha256"), "document-index"))
            if isinstance(path, str):
                seen_paths.add(path)

        if errors:
            raise ValidationError(errors)
        return cls(root, records)

    @property
    def document_ids(self) -> tuple[str, ...]:
        return tuple(self._records)

    def resolve(self, document_id: str) -> ResolvedDocument:
        """Resolve one exact stable ID; paths and guessed aliases are rejected."""
        try:
            return self._records[document_id]
        except KeyError as error:
            raise ValidationError([f"unknown-document-id:{document_id}"]) from error


def validate_package_manifest(root: Path) -> tuple[str, ...]:
    """Validate derived package bindings for KL-006's indexed handoff files."""
    root = root.resolve()
    data = _load_json(root / PACKAGE_MANIFEST)
    files = data.get("files")
    if not isinstance(files, list):
        raise ValidationError(["package-manifest-files"])
    entries: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            errors.append("package-manifest-entry-not-object")
            continue
        path = entry["path"]
        if path in entries:
            errors.append(f"package-manifest-duplicate-path:{path}")
        entries[path] = entry
    for path in _PACKAGE_BINDINGS:
        entry = entries.get(path)
        if entry is None:
            errors.append(f"package-manifest-missing-entry:{path}")
            continue
        target = _target(root, path)
        if entry.get("sha256") != _sha256(target):
            errors.append(f"package-manifest-hash:{path}")
        if entry.get("bytes") != target.stat().st_size:
            errors.append(f"package-manifest-bytes:{path}")
    if errors:
        raise ValidationError(errors)
    return _PACKAGE_BINDINGS


@dataclass(frozen=True)
class ManifestFinding:
    artifact_id: str
    artifact_kind: str
    path: str | None
    reason: str


@dataclass(frozen=True)
class EvidenceManifestReport:
    verified_paths: tuple[str, ...]
    missing: tuple[ManifestFinding, ...]
    historical_claims_status: str


def validate_evidence_manifest(root: Path) -> EvidenceManifestReport:
    """Validate bound evidence and retain declared gaps without promoting them."""
    root = root.resolve()
    index = DocumentIndex.load(root)
    data = _load_json(root / EVIDENCE_MANIFEST)
    errors: list[str] = []
    verified: list[str] = []

    authority_bindings = (
        ("DOC-PROTOCOL-V1.2", "protocol_file", "protocol_sha256"),
        ("DOC-DB-V0.2", "db_file", "db_sha256"),
    )
    for document_id, path_key, hash_key in authority_bindings:
        record = index.resolve(document_id)
        if data.get(path_key) != record.path or data.get(hash_key) != record.sha256:
            errors.append(f"evidence-authority-binding:{document_id}")
        else:
            verified.append(record.path)

    available = data.get("available_evidence")
    if not isinstance(available, list):
        errors.append("evidence-available-list")
        available = []
    seen_artifacts: set[str] = set()
    seen_paths = set(verified)
    for entry in available:
        if not isinstance(entry, dict):
            errors.append("evidence-available-entry-not-object")
            continue
        artifact_id = entry.get("artifact_id")
        path = entry.get("path")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"evidence-artifact-id:{artifact_id}")
        elif artifact_id in seen_artifacts:
            errors.append(f"evidence-duplicate-artifact:{artifact_id}")
        else:
            seen_artifacts.add(artifact_id)
        if isinstance(path, str) and path in seen_paths:
            errors.append(f"evidence-duplicate-path:{path}")
        file_errors = _validate_file(root, path, entry.get("sha256"), "evidence")
        errors.extend(file_errors)
        if not file_errors and isinstance(path, str):
            verified.append(path)
            seen_paths.add(path)

    unresolved = data.get("unresolved_evidence")
    if not isinstance(unresolved, list) or not unresolved:
        errors.append("evidence-unresolved-list")
        unresolved = []
    missing: list[ManifestFinding] = []
    for entry in unresolved:
        if not isinstance(entry, dict):
            errors.append("evidence-unresolved-entry-not-object")
            continue
        artifact_id = entry.get("artifact_id")
        kind = entry.get("artifact_kind")
        status = entry.get("status")
        path = entry.get("path")
        reason = entry.get("reason")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append(f"evidence-artifact-id:{artifact_id}")
            continue
        if artifact_id in seen_artifacts:
            errors.append(f"evidence-duplicate-artifact:{artifact_id}")
        seen_artifacts.add(artifact_id)
        if kind not in ("MODEL_SOURCE", "MODEL_REPORT", "POLICY_FIXTURE", "SOURCE_REVISION"):
            errors.append(f"evidence-unresolved-kind:{artifact_id}:{kind}")
        if status != "MISSING":
            errors.append(f"evidence-unresolved-status:{artifact_id}:{status}")
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"evidence-unresolved-reason:{artifact_id}")
        if path is not None:
            if not _relative_path(path):
                errors.append(f"evidence-unresolved-invalid-path:{artifact_id}:{path}")
            elif _target(root, path).exists():
                errors.append(f"evidence-unresolved-path-present:{artifact_id}:{path}")
        missing.append(ManifestFinding(artifact_id, str(kind), path, str(reason)))

    if data.get("independently_reproducible_from_this_package") is not False:
        errors.append("evidence-reproducibility-must-remain-false")
    if data.get("freeze_evidence_status") != _FREEZE_EVIDENCE_STATUS:
        errors.append("evidence-freeze-status")
    if data.get("historical_declared_results_status") != _HISTORICAL_RESULTS_STATUS:
        errors.append("evidence-historical-results-status")
    if data.get("historical_declared_results") != _HISTORICAL_DECLARED_RESULTS:
        errors.append("evidence-historical-results-declaration")
    if data.get("production_test_promotion") != "NONE":
        errors.append("evidence-production-promotion")
    required_kinds = {"MODEL_SOURCE", "MODEL_REPORT", "POLICY_FIXTURE", "SOURCE_REVISION"}
    if not required_kinds <= {item.artifact_kind for item in missing}:
        errors.append("evidence-missing-model-sources-not-explicit")
    if errors:
        raise ValidationError(errors)
    return EvidenceManifestReport(tuple(verified), tuple(missing), _HISTORICAL_RESULTS_STATUS)


class HistoricalTaskMap:
    """Validate historical joins against explicit backlog namespaces."""

    @classmethod
    def validate(cls, root: Path) -> int:
        root = root.resolve()
        data = _load_json(root / HISTORICAL_TASK_MAP)
        errors: list[str] = []
        current_namespace = data.get("current_namespace")
        legacy_namespaces = data.get("legacy_namespaces")
        sources = data.get("namespace_sources")
        current_backlog = _load_json(root / CURRENT_BACKLOG)
        authoritative_current_namespace = current_backlog.get("task_namespace")
        if not isinstance(authoritative_current_namespace, str):
            errors.append("historical-current-backlog-namespace-missing")
        if current_namespace != authoritative_current_namespace:
            errors.append("historical-current-namespace")
        if not isinstance(legacy_namespaces, list) or not all(
            isinstance(item, str) for item in legacy_namespaces
        ):
            errors.append("historical-legacy-namespaces")
            legacy_namespaces = []
        if not isinstance(sources, list):
            errors.append("historical-namespace-sources")
            sources = []

        titles: dict[str, str] = {}
        source_namespaces: set[str] = set()
        for source in sources:
            if not isinstance(source, dict):
                errors.append("historical-source-not-object")
                continue
            namespace, path = source.get("namespace"), source.get("path")
            if not isinstance(namespace, str) or namespace in source_namespaces:
                errors.append(f"historical-source-namespace:{namespace}")
                continue
            source_namespaces.add(namespace)
            if not _relative_path(path):
                errors.append(f"historical-source-path:{namespace}:{path}")
                continue
            assert isinstance(path, str)
            target = _target(root, path)
            if not target.is_file():
                errors.append(f"historical-source-missing:{namespace}:{path}")
                continue
            backlog = _load_json(target)
            if path == CURRENT_BACKLOG:
                if namespace != current_namespace:
                    errors.append("historical-current-source-namespace")
                if backlog.get("task_namespace") != current_namespace:
                    errors.append("historical-current-backlog-namespace")
            tasks = backlog.get("tasks")
            if not isinstance(tasks, list):
                errors.append(f"historical-source-tasks:{namespace}")
                continue
            for task in tasks:
                if not isinstance(task, dict) or not isinstance(task.get("id"), str) or not isinstance(task.get("title"), str):
                    errors.append(f"historical-source-task-shape:{namespace}")
                    continue
                identity = f"{namespace}/{task['id']}"
                if identity in titles:
                    errors.append(f"historical-source-duplicate-task:{identity}")
                titles[identity] = task["title"]

        expected_namespaces = ({current_namespace} if isinstance(current_namespace, str) else set()) | set(legacy_namespaces)
        if source_namespaces != expected_namespaces:
            errors.append("historical-source-namespace-set")
        expected_sources = dict(_LEGACY_NAMESPACE_SOURCES)
        if isinstance(authoritative_current_namespace, str):
            expected_sources[authoritative_current_namespace] = CURRENT_BACKLOG
        observed_sources = {
            source.get("namespace"): source.get("path")
            for source in sources
            if isinstance(source, dict) and isinstance(source.get("namespace"), str)
        }
        if observed_sources != expected_sources:
            errors.append("historical-authority-sources")
        current_sources = [
            source
            for source in sources
            if isinstance(source, dict) and source.get("path") == CURRENT_BACKLOG
        ]
        if len(current_sources) != 1:
            errors.append("historical-current-backlog-source")

        reused = data.get("reused_display_ids")
        migrations = data.get("semantic_migrations")
        if not isinstance(reused, list) or not isinstance(migrations, list):
            errors.append("historical-mapping-lists")
            reused, migrations = [], []
        pairs: set[tuple[str, str, str]] = set()
        for group_name, entries in (("reused", reused), ("migration", migrations)):
            for entry in entries:
                if not isinstance(entry, dict):
                    errors.append(f"historical-{group_name}-entry-not-object")
                    continue
                legacy = entry.get("legacy_identity")
                current = entry.get("current_identity")
                parsed_legacy = _TASK_IDENTITY.fullmatch(legacy) if isinstance(legacy, str) else None
                parsed_current = _TASK_IDENTITY.fullmatch(current) if isinstance(current, str) else None
                if not parsed_legacy or parsed_legacy.group(1) not in legacy_namespaces:
                    errors.append(f"historical-legacy-identity:{legacy}")
                    continue
                if not parsed_current or parsed_current.group(1) != current_namespace:
                    errors.append(f"historical-current-identity:{current}")
                    continue
                assert isinstance(legacy, str)
                assert isinstance(current, str)
                if legacy not in titles or current not in titles:
                    errors.append(f"historical-unresolved-identity:{legacy}->{current}")
                if entry.get("legacy_title") is not None and entry.get("legacy_title") != titles.get(legacy):
                    errors.append(f"historical-legacy-title:{legacy}")
                if entry.get("current_title") is not None and entry.get("current_title") != titles.get(current):
                    errors.append(f"historical-current-title:{current}")
                if group_name == "reused" and parsed_legacy.group(2) != parsed_current.group(2):
                    errors.append(f"historical-reused-display-id:{legacy}->{current}")
                key = (group_name, legacy, current)
                if key in pairs:
                    errors.append(f"historical-duplicate-mapping:{legacy}->{current}")
                pairs.add(key)

        if errors:
            raise ValidationError(errors)
        return len(pairs)
