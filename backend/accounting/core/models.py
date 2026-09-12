from typing import Optional

from pydantic import BaseModel, Field, field_validator

from .types import AccountType


class AccountCreate(BaseModel):
    """Input for creating one account. `code` is optional: omit it to have the Core
    allocate the next child code atomically under `parent`."""
    name: str = Field(min_length=1, max_length=160)
    name_ar: Optional[str] = Field(default=None, max_length=160)
    type: AccountType
    parent: Optional[str] = None
    code: Optional[str] = None
    is_group: bool = False
    notes: Optional[str] = Field(default=None, max_length=500)

    @field_validator("code", "parent")
    @classmethod
    def _strip(cls, v):
        if v is None:
            return None
        v = str(v).strip()
        return v or None


class AccountUpdate(BaseModel):
    """Only the fields below are ever updatable. `code` is intentionally absent: an account
    code is immutable for the whole life of the chart (renaming a code would silently
    rewrite history once the journal exists)."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    name_ar: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=500)
    type: Optional[AccountType] = None
    parent: Optional[str] = None
    is_group: Optional[bool] = None


PUBLIC_FIELDS = (
    "id", "entity_id", "code", "name", "name_ar", "type", "parent", "level",
    "is_group", "origin", "role", "is_active", "next_child_seq", "notes",
    "created_at", "created_by", "updated_at", "updated_by",
)


def account_public(doc: dict) -> dict:
    """Projection used by every read path — never returns `_id` or internal fields."""
    return {k: doc.get(k) for k in PUBLIC_FIELDS}
