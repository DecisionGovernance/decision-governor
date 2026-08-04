"""
examples/fastapi_gate.py
============================================================
Decision Governor — Gating a FastAPI Endpoint
============================================================

The G-7 seam that lets a web service gate its AI endpoints:
`GovernorMiddleware` hands every request a FRESH governor
(factory, not instance — correlation ids and per-request
context must not leak across requests), tags each decision
record with the request's correlation id, and serves
GET /governor/health with the gate's *structure* (checks,
policy, sink status) — never record contents.

Run (requires the [fastapi] extra):

    pip install "decision-governor[fastapi]" uvicorn
    uvicorn examples.fastapi_gate:app --reload

    curl -s -X POST localhost:8000/summarize \
         -H 'content-type: application/json' \
         -H 'x-correlation-id: req-42' \
         -d '{"document": "Quarterly revenue grew 12%..."}'
    curl -s localhost:8000/governor/health
"""
from fastapi import Depends, FastAPI
from pydantic import BaseModel

from decision_governor import Decision, Governor
from decision_governor.checks import register_default_checks
from decision_governor.integrations import GovernorMiddleware
from decision_governor.risk import CostStructure, CVaRPolicy


def build_governor() -> Governor:
    """One governor per request scope — logs and context are
    request-specific, so the middleware calls this factory each time."""
    gov = Governor(
        policy=CVaRPolicy(
            alpha=0.05,
            costs=CostStructure(err=100.0, abstention=3.0),
            default_cost="err",
        ),
        log="web_decisions.db",
        deployment="summarizer-svc",  # overwritten by the middleware's value
    )
    register_default_checks(gov)
    return gov


app = FastAPI(title="Governed summarizer")
mw = GovernorMiddleware(app, governor_factory=build_governor, deployment="summarizer-svc")


class SummarizeRequest(BaseModel):
    document: str


def summarize(document: str) -> str:
    """Stand-in for the model call this service actually gates."""
    return f"Summary: {document[:80]}"


@app.post("/summarize")
def summarize_endpoint(
    body: SummarizeRequest,
    gov: Governor = Depends(mw.get_governor),
) -> dict:
    output = summarize(body.document)
    verdict = gov.evaluate(output, context={"gate": "summarize"})
    if verdict.decision is Decision.ABSTAIN:
        return {
            "decision": verdict.decision.value,
            "reasons": verdict.reasons,
            "correlation_id": gov.correlation_id,
        }
    return {
        "decision": verdict.decision.value,
        "summary": output,
        "correlation_id": gov.correlation_id,
    }
