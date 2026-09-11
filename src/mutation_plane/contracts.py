"""Core types for the mutation approval plane.

A *mutation* is a proposed change to some resource. It is never applied
directly: it is proposed, reviewed, and only then executed, with every
transition recorded. This module holds the shared vocabulary.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


def digest(value: Any) -> str:
    """Stable content digest of any JSON-serializable value.

    Used two ways: to make proposing the same change twice idempotent, and to
    detect that a resource changed underneath an approved proposal (before-image
    check).
    """
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RequestContext:
    """Who is acting. ``is_internal`` gates who may approve."""

    actor: str
    is_internal: bool = False


class MutationState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


@dataclass
class Proposal:
    proposal_id: str
    domain: str
    action: str
    payload: Dict[str, Any]
    requested_by: str
    idempotency_key: str
    before_hash: Optional[str] = None
    state: MutationState = MutationState.PROPOSED
    approved_by: Optional[str] = None
    result: Any = None
    created_at: float = field(default_factory=time.time)


@dataclass
class JournalEntry:
    proposal_id: str
    from_state: Optional[MutationState]
    to_state: MutationState
    actor: str
    at: float = field(default_factory=time.time)


# --- Errors -----------------------------------------------------------------

class MutationError(RuntimeError):
    """Base class for every refusal in the plane."""


class MutationDisabled(MutationError):
    """The domain is turned off by a flag."""


class StateConflict(MutationError):
    """The proposal is not in a state that allows the requested transition."""


class BeforeImageConflict(MutationError):
    """The resource changed since the proposal was made; executing now would
    clobber that change."""


class ExecutionFailed(MutationError):
    """The applier raised while applying an approved mutation."""
