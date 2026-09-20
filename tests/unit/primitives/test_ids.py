from uuid import UUID

import pytest

from kineticloop.primitives import canonical_id, is_canonical_id, new_id


class _MisleadingUUID(UUID):
    def __str__(self) -> str:
        return "not-a-uuid"


def test_id_format_valid_for_generated_and_existing_ids() -> None:
    generated = new_id()

    assert is_canonical_id(generated)
    assert UUID(generated).version == 4
    assert canonical_id(UUID("8c7d83ee-49db-4b2c-9df2-0b0f158c328f")) == (
        "8c7d83ee-49db-4b2c-9df2-0b0f158c328f"
    )


@pytest.mark.parametrize(
    "value",
    [
        "8C7D83EE-49DB-4B2C-9DF2-0B0F158C328F",
        "8c7d83ee49db4b2c9df20b0f158c328f",
        " 8c7d83ee-49db-4b2c-9df2-0b0f158c328f",
        "00000000-0000-0000-0000-000000000000",
    ],
)
def test_invalid_input_rejected_for_noncanonical_ids(value: str) -> None:
    with pytest.raises(ValueError):
        canonical_id(value)
    assert not is_canonical_id(value)


def test_invalid_input_rejected_for_uuid_subclass_with_noncanonical_text() -> None:
    value = _MisleadingUUID("8c7d83ee-49db-4b2c-9df2-0b0f158c328f")

    with pytest.raises(ValueError, match="lower-case, hyphenated RFC 4122 UUID"):
        canonical_id(value)
