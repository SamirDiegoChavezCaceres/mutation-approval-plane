"""In-memory store for proposals and the audit journal.

The storage is deliberately simple so the state machine stays the focus; a SQL
store would implement the same methods (the journal becomes an append-only
table, `find_open_by_key` a unique index on the idempotency key).
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .contracts import JournalEntry, MutationState, Proposal

# States from which no further transition is allowed.
_TERMINAL = {MutationState.REJECTED, MutationState.EXECUTED}


class InMemoryMutationStore:
    def __init__(self) -> None:
        self._proposals: Dict[str, Proposal] = {}
        self._journal: List[JournalEntry] = []

    def get(self, proposal_id: str) -> Optional[Proposal]:
        return self._proposals.get(proposal_id)

    def find_open_by_key(self, idempotency_key: str) -> Optional[Proposal]:
        """Return a non-terminal proposal with this key, if any (idempotency)."""
        for proposal in self._proposals.values():
            if proposal.idempotency_key == idempotency_key and proposal.state not in _TERMINAL:
                return proposal
        return None

    def put(self, proposal: Proposal) -> None:
        self._proposals[proposal.proposal_id] = proposal

    def transition(self, proposal: Proposal, to_state: MutationState, actor: str) -> None:
        self._journal.append(
            JournalEntry(proposal.proposal_id, proposal.state, to_state, actor)
        )
        proposal.state = to_state
        self._proposals[proposal.proposal_id] = proposal

    def journal(self, proposal_id: Optional[str] = None) -> List[JournalEntry]:
        if proposal_id is None:
            return list(self._journal)
        return [e for e in self._journal if e.proposal_id == proposal_id]
