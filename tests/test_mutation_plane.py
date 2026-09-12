import pytest

from mutation_plane import (
    BeforeImageConflict,
    MutationCoordinator,
    MutationDisabled,
    MutationState,
    RequestContext,
    StateConflict,
)

ALICE = RequestContext(actor="alice")                 # requester
REVIEWER = RequestContext(actor="bob", is_internal=True)


def _proposal(coord, payload=None, before_image=None):
    return coord.propose(
        ALICE, domain="campaign", action="set_budget",
        payload=payload or {"budget": 1000}, before_image=before_image,
    )


def test_identical_proposal_is_idempotent():
    coord = MutationCoordinator()
    first = _proposal(coord)
    second = _proposal(coord)
    assert first.proposal_id == second.proposal_id


def test_requester_cannot_approve_own_proposal():
    coord = MutationCoordinator()
    p = _proposal(coord)
    with pytest.raises(PermissionError):
        coord.approve(RequestContext(actor="alice", is_internal=True), p.proposal_id)


def test_non_internal_cannot_approve():
    coord = MutationCoordinator()
    p = _proposal(coord)
    with pytest.raises(PermissionError):
        coord.approve(RequestContext(actor="carol"), p.proposal_id)


def test_happy_path_executes_and_journals():
    coord = MutationCoordinator()
    p = _proposal(coord)
    coord.approve(REVIEWER, p.proposal_id)
    result = coord.execute(p.proposal_id, applier=lambda pr: pr.payload["budget"])
    assert result == 1000
    assert coord.store.get(p.proposal_id).state is MutationState.EXECUTED
    states = [e.to_state for e in coord.store.journal(p.proposal_id)]
    assert states == [MutationState.PROPOSED, MutationState.APPROVED, MutationState.EXECUTED]


def test_execute_is_idempotent():
    coord = MutationCoordinator()
    p = _proposal(coord)
    coord.approve(REVIEWER, p.proposal_id)
    calls = []

    def applier(pr):
        calls.append(1)
        return "done"

    assert coord.execute(p.proposal_id, applier) == "done"
    assert coord.execute(p.proposal_id, applier) == "done"  # replay
    assert len(calls) == 1                                    # applier ran once


def test_cannot_execute_before_approval():
    coord = MutationCoordinator()
    p = _proposal(coord)
    with pytest.raises(StateConflict):
        coord.execute(p.proposal_id, applier=lambda pr: None)


def test_before_image_conflict_blocks_stale_execute():
    coord = MutationCoordinator()
    # Proposed against budget=500; the live value drifts before execution.
    p = _proposal(coord, before_image={"budget": 500})
    coord.approve(REVIEWER, p.proposal_id)
    with pytest.raises(BeforeImageConflict):
        coord.execute(
            p.proposal_id,
            applier=lambda pr: "applied",
            before_image_reader=lambda pr: {"budget": 900},  # changed underneath
        )


def test_disabled_domain_refuses():
    coord = MutationCoordinator(enabled_domains={"other"})
    with pytest.raises(MutationDisabled):
        _proposal(coord)
