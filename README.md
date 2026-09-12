# mutation-approval-plane

A small, domain-agnostic plane for changes that must not be applied blindly.
Instead of mutating a resource directly, you **propose** the change, a reviewer
**approves** it, and only then is it **executed** - with idempotency, an audit
journal, and a guard against concurrent edits.

This is the pattern you want the moment something other than a trusted human can
request a change (an LLM agent, an automation, an external caller). A from-
scratch, neutral rewrite of a production design.

## Guarantees

- **Idempotent proposals.** Proposing the identical change twice returns the
  same open proposal, so a retrying client never creates duplicates.
- **Separation of duties.** Only internal reviewers approve, and nobody may
  approve their own proposal.
- **Before-image check.** A proposal records a digest of the resource as it was.
  At execution the resource is re-read; if it changed in the meantime, execution
  refuses (`BeforeImageConflict`) instead of clobbering the newer state. This is
  optimistic concurrency, by content digest.
- **Idempotent execution.** Executing an already-executed proposal returns the
  stored result; the applier runs at most once.
- **Auditability.** Every state transition is appended to a journal.

## Lifecycle

```
propose ──► PROPOSED ──approve──► APPROVED ──execute──► EXECUTED
                │                                  └─(applier raised)─► FAILED
                └──reject──► REJECTED
```

## Use it

```python
from mutation_plane import MutationCoordinator, RequestContext

coord = MutationCoordinator()
agent    = RequestContext(actor="agent-7")
reviewer = RequestContext(actor="dana", is_internal=True)

p = coord.propose(agent, domain="campaign", action="set_budget",
                  payload={"budget": 1000}, before_image={"budget": 500})

coord.approve(reviewer, p.proposal_id)          # a human signs off

coord.execute(
    p.proposal_id,
    applier=lambda pr: apply_to_system(pr.payload),   # your side effect
    before_image_reader=lambda pr: read_live(pr),     # re-read for the check
)
```

The `applier` is where the real side effect lives (a DB write, an API call); the
plane makes sure it only runs on an approved, still-valid proposal, exactly once.

## Try it

```bash
python scripts/demo.py
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Covers idempotent propose, self-approval and non-reviewer rejection, the
before-image conflict, idempotent execution, and the journal.

## License

MIT.
