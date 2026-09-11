"""The coordinator: propose -> approve -> execute, with the guarantees that make
it safe to let an agent (or anyone) request changes.

* **Idempotency.** Proposing the identical change twice returns the same open
  proposal instead of a duplicate.
* **Separation of duties.** Only internal reviewers approve, and nobody approves
  their own proposal.
* **Before-image check.** If the resource changed since the proposal was made,
  execution refuses rather than clobbering the newer state (optimistic
  concurrency).
* **Idempotent execution.** Executing an already-executed proposal returns the
  stored result; the applier runs at most once.
* **Audit.** Every transition is journaled.
"""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Iterable, Optional

from .contracts import (
    BeforeImageConflict,
    ExecutionFailed,
    MutationDisabled,
    MutationState,
    Proposal,
    RequestContext,
    StateConflict,
    digest,
)
from .store import InMemoryMutationStore

Applier = Callable[[Proposal], Any]
BeforeImageReader = Callable[[Proposal], Any]


class MutationCoordinator:
    def __init__(
        self,
        store: Optional[InMemoryMutationStore] = None,
        enabled_domains: Optional[Iterable[str]] = None,
    ) -> None:
        self.store = store or InMemoryMutationStore()
        # None means "all domains enabled"; otherwise only the listed ones.
        self._enabled = set(enabled_domains) if enabled_domains is not None else None

    def _check_enabled(self, domain: str) -> None:
        if self._enabled is not None and domain not in self._enabled:
            raise MutationDisabled(f"mutations are disabled for domain '{domain}'")

    def propose(
        self,
        context: RequestContext,
        domain: str,
        action: str,
        payload: Dict[str, Any],
        before_image: Any = None,
    ) -> Proposal:
        self._check_enabled(domain)
        key = digest({"domain": domain, "action": action, "payload": payload})

        existing = self.store.find_open_by_key(key)
        if existing is not None:
            return existing  # idempotent: same change already pending

        proposal = Proposal(
            proposal_id=str(uuid.uuid4()),
            domain=domain,
            action=action,
            payload=payload,
            requested_by=context.actor,
            idempotency_key=key,
            before_hash=digest(before_image) if before_image is not None else None,
        )
        self.store.put(proposal)
        self.store.transition(proposal, MutationState.PROPOSED, context.actor)
        return proposal

    def approve(self, context: RequestContext, proposal_id: str) -> Proposal:
        proposal = self._require(proposal_id)
        if not context.is_internal:
            raise PermissionError("only internal reviewers may approve mutations")
        if context.actor == proposal.requested_by:
            raise PermissionError("the requester cannot approve their own proposal")
        if proposal.state is not MutationState.PROPOSED:
            raise StateConflict(f"cannot approve a proposal in state '{proposal.state.value}'")
        proposal.approved_by = context.actor
        self.store.transition(proposal, MutationState.APPROVED, context.actor)
        return proposal

    def reject(self, context: RequestContext, proposal_id: str) -> Proposal:
        proposal = self._require(proposal_id)
        if not context.is_internal:
            raise PermissionError("only internal reviewers may reject mutations")
        if proposal.state is not MutationState.PROPOSED:
            raise StateConflict(f"cannot reject a proposal in state '{proposal.state.value}'")
        self.store.transition(proposal, MutationState.REJECTED, context.actor)
        return proposal

    def execute(
        self,
        proposal_id: str,
        applier: Applier,
        before_image_reader: Optional[BeforeImageReader] = None,
    ) -> Any:
        proposal = self._require(proposal_id)
        if proposal.state is MutationState.EXECUTED:
            return proposal.result  # idempotent replay
        if proposal.state is not MutationState.APPROVED:
            raise StateConflict(f"cannot execute a proposal in state '{proposal.state.value}'")

        if before_image_reader is not None and proposal.before_hash is not None:
            current = before_image_reader(proposal)
            if digest(current) != proposal.before_hash:
                raise BeforeImageConflict(
                    f"resource for proposal {proposal_id} changed since it was proposed"
                )

        try:
            result = applier(proposal)
        except Exception as exc:  # applier failed: record and surface
            self.store.transition(proposal, MutationState.FAILED, "executor")
            raise ExecutionFailed(str(exc)) from exc

        proposal.result = result
        self.store.transition(proposal, MutationState.EXECUTED, "executor")
        return result

    def _require(self, proposal_id: str) -> Proposal:
        proposal = self.store.get(proposal_id)
        if proposal is None:
            raise StateConflict(f"no such proposal: {proposal_id}")
        return proposal
