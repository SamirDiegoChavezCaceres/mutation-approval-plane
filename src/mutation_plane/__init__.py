"""A propose/approve/execute mutation plane: idempotent, auditable, and safe
against concurrent changes."""

from .contracts import (
    BeforeImageConflict,
    ExecutionFailed,
    JournalEntry,
    MutationDisabled,
    MutationState,
    Proposal,
    RequestContext,
    StateConflict,
    digest,
)
from .service import MutationCoordinator
from .store import InMemoryMutationStore

__all__ = [
    "MutationCoordinator",
    "InMemoryMutationStore",
    "RequestContext",
    "Proposal",
    "MutationState",
    "JournalEntry",
    "digest",
    "MutationDisabled",
    "StateConflict",
    "BeforeImageConflict",
    "ExecutionFailed",
]
