from typing import Optional

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .types import AccountType

# Fields a client may NEVER set or change through any transport. Listed explicitly so the
# rule is readable and enforceable, not just an absence in a schema.
IMMUTABLE_FIELDS = ("id", "entity_id", "code", "origin", "level", "role",
                    "next_child_seq", "created_at", "created_by")

# Language separation for account names: the Arabic field holds Arabic, the English field
# holds English. Enforced here so it cannot be bypassed by calling the API directly.
_ARABIC_LETTER = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")


def _validate_name_en(v):
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    if _ARABIC_LETTER.search(v):
        raise ValueError("حقل الاسم بالإنجليزية يقبل الإنجليزية فقط — اكتب الاسم العربي في حقل الاسم بالعربية")
    return v


def _validate_name_ar(v):
    if v is None:
        return None
    v = str(v).strip()
    if not v:
        return None
    if _LATIN_LETTER.search(v):
        raise ValueError("حقل الاسم بالعربية يقبل العربية فقط — اكتب الاسم الإنجليزي في حقل الاسم بالإنجليزية")
    return v


class AccountCreate(BaseModel):
    """Input for creating one account. `code` is optional: omit it to have the Core
    allocate the next child code atomically under `parent`.

    `extra="forbid"` (Phase 2 HARDEN): sending `origin`, `role`, `level`, `entity_id` or any
    unknown key is rejected outright instead of being silently ignored — a client can never
    impersonate a SYSTEM/STANDARD account or claim a semantic role.
    """
    model_config = ConfigDict(extra="forbid")

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

    @field_validator("name")
    @classmethod
    def _name_en_only(cls, v):
        return _validate_name_en(v)

    @field_validator("name_ar")
    @classmethod
    def _name_ar_only(cls, v):
        return _validate_name_ar(v)


class AccountUpdate(BaseModel):
    """Only the fields below are ever updatable.

    `code` is intentionally absent: an account code is immutable for the whole life of the
    chart (renaming it would silently rewrite history once a journal exists). `is_active` is
    absent too — activation has its own lifecycle path with its own guards, so it can never
    be flipped as a side effect of an edit.
    """
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    name_ar: Optional[str] = Field(default=None, max_length=160)
    notes: Optional[str] = Field(default=None, max_length=500)
    type: Optional[AccountType] = None
    parent: Optional[str] = None
    is_group: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def _name_en_only(cls, v):
        return _validate_name_en(v)

    @field_validator("name_ar")
    @classmethod
    def _name_ar_only(cls, v):
        return _validate_name_ar(v)


PUBLIC_FIELDS = (
    "id", "entity_id", "code", "name", "name_ar", "type", "parent", "level",
    "is_group", "origin", "role", "is_active", "next_child_seq", "notes",
    "created_at", "created_by", "updated_at", "updated_by",
)


def account_public(doc: dict) -> dict:
    """Projection used by every read path — never returns `_id` or internal fields."""
    return {k: doc.get(k) for k in PUBLIC_FIELDS}
