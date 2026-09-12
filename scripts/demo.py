"""Walk a change through propose -> approve -> execute, and show the guards.

    python scripts/demo.py
"""

from __future__ import annotations

from mutation_plane import (
    BeforeImageConflict,
    MutationCoordinator,
    RequestContext,
)

alice = RequestContext(actor="alice")                    # an agent or operator
reviewer = RequestContext(actor="bob", is_internal=True)  # a human reviewer


def main() -> None:
    coord = MutationCoordinator()

    p = coord.propose(alice, "campaign", "set_budget", {"budget": 1000},
                      before_image={"budget": 500})
    print("proposed:", p.proposal_id, p.state.value)

    # Idempotent: the same change does not create a second proposal.
    again = coord.propose(alice, "campaign", "set_budget", {"budget": 1000},
                          before_image={"budget": 500})
    print("same proposal returned:", again.proposal_id == p.proposal_id)

    try:
        coord.approve(RequestContext(actor="alice", is_internal=True), p.proposal_id)
    except PermissionError as exc:
        print("self-approval blocked:", exc)

    coord.approve(reviewer, p.proposal_id)
    print("approved by:", p.approved_by)

    # The live budget drifted since the proposal was made -> refuse.
    try:
        coord.execute(p.proposal_id, applier=lambda pr: "applied",
                      before_image_reader=lambda pr: {"budget": 777})
    except BeforeImageConflict as exc:
        print("stale execute blocked:", exc)

    # Resource is still as proposed -> apply.
    result = coord.execute(p.proposal_id, applier=lambda pr: f"budget set to {pr.payload['budget']}",
                           before_image_reader=lambda pr: {"budget": 500})
    print("executed:", result)

    print("\njournal:")
    for e in coord.store.journal(p.proposal_id):
        print(f"  {e.from_state.value if e.from_state else '-':>9} -> {e.to_state.value:<9} by {e.actor}")


if __name__ == "__main__":
    main()
