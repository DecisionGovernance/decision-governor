# Decision Governor

**Risk governance for AI outputs and actions: allow / scale / abstain.**

Decision Governor stands between an AI system's outputs and their consequences.
Every output or proposed action passes through gates that return one of three
verdicts — **ALLOW** (execute as proposed), **SCALE** (execute in constrained
form), **ABSTAIN** (decline, with reasons) — decided by a risk policy over
costs *you* define in your domain's own units, with every governance decision
logged in an auditable, independently re-verifiable record.

Decision Governor governs **decisions**, not documents. v0.1 ships check
libraries for text, structured, and HTML outputs; the engine gates any output
or action through the same verdict, policy, and audit machinery, and the
`Check` protocol is how you bring your domain.

**Design invariant:** the core is deterministic and reproducible. Learned
models participate only in roles that can *tighten* a verdict, never loosen
one — an LLM hallucination inside the Governor can cost a false abstention,
but can never authorize a bad execution.

Non-deterministic checks are full participants in every verdict, restricted in
direction rather than in weight: they can be why you stopped, never why you
proceeded, and only a gate with no deterministic evidence at all is capped
below ALLOW.

> **Status: pre-release scaffold (v0.1.0.dev0).** Public contracts are frozen;
> the engine, risk interface, checks, instrumentation, adversarial toolkit,
> and examples land card by card ahead of the v0.1.0 release. See
> `docs/G0-checklist.md` for the build order and `CHANGELOG.md` for progress.

## Install (dev)

    pip install -e ".[dev]"
    pytest

## License

Apache-2.0
