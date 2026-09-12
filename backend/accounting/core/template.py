from dataclasses import dataclass, field
from typing import Optional, List

from .types import AccountType, AccountOrigin


@dataclass(frozen=True)
class TemplateAccount:
    """One row of a Chart-of-Accounts template.

    `role` is the semantic handle. Business logic (in later phases) must resolve accounts
    BY ROLE, never by a hardcoded number, so a project can renumber its chart freely.
    """
    code: str
    name: str
    name_ar: str
    type: AccountType
    parent: Optional[str] = None
    is_group: bool = False
    origin: AccountOrigin = AccountOrigin.STANDARD
    role: Optional[str] = None
    accepts_children: bool = False


@dataclass
class ChartTemplate:
    """A named, ordered set of template rows. Pure data — contains no engine logic and no
    business logic; the Core knows how to seed ANY template, and knows none of them."""
    key: str
    title: str
    version: int
    accounts: List[TemplateAccount] = field(default_factory=list)

    def extend(self, key: str, title: str, extra: List[TemplateAccount],
               version: Optional[int] = None) -> "ChartTemplate":
        return ChartTemplate(key=key, title=title,
                             version=version if version is not None else self.version,
                             accounts=list(self.accounts) + list(extra))

    def by_role(self, role: str) -> Optional[TemplateAccount]:
        for a in self.accounts:
            if a.role == role:
                return a
        return None
