"""Card G-7 Step 1 — the FastAPI seam (`[fastapi]` extra).

The extras discipline, enforced here: NOTHING FastAPI-touching is
imported at module top level. A user who never installs `[fastapi]` can
import this module (and the whole package) without an ImportError; the
optional dependency is touched only inside `GovernorMiddleware.__init__`,
and even there its absence is tolerated so the class stays testable
against duck-typed apps and requests.

Design decisions, stated where they bind:

- **Factory, not instance.** Each request gets a FRESH governor from
  `governor_factory`, because logs and context are request-specific: a
  shared instance would let one request's correlation id or bound
  context leak into another's records.
- **The correlation id tags every record.** It is injected into every
  evaluation context (so the context digest covers it) AND stamped onto
  the stored record as a top-level ``correlation_id`` key by a
  decorating sink, so a web request maps to its governance decisions in
  the audit bundle. Schema v1.0 validates required keys only; the extra
  key rides along and survives export/verify untouched.
- **The health route exposes structure, never record contents.** Which
  checks are registered, which policy class judges, whether the sink
  answers a query — and nothing else. A health endpoint that leaked
  decision data would be an audit-trail hole.
"""
from __future__ import annotations

import functools
import uuid
from collections.abc import Callable, Iterator, Mapping
from typing import TYPE_CHECKING, Any

from decision_governor.core.engine import Governor

if TYPE_CHECKING:  # pragma: no cover — the runtime import happens in __init__
    from fastapi import Request

HEALTH_PATH = "/governor/health"


def _publish_request_annotation() -> None:
    """Make `Request` resolvable in this module's namespace so FastAPI's
    dependency machinery can evaluate `get_governor`'s annotation. Called
    from __init__ — by the time a route depends on the governor, the app
    exists, so fastapi is installed and this succeeds. Absence is not an
    error: duck-typed test doubles never trigger annotation resolution."""
    try:
        from fastapi import Request as _Request
    except ModuleNotFoundError:
        return
    globals()["Request"] = _Request


class _CorrelatedSink:
    """Sink decorator: stamps the request's correlation id onto each
    stored record. Read/query pass through untouched."""

    def __init__(self, inner: Any, correlation_id: str) -> None:
        self.inner = inner
        self.correlation_id = correlation_id

    def write(self, record: Mapping[str, Any]) -> None:
        tagged = dict(record)
        tagged["correlation_id"] = self.correlation_id
        self.inner.write(tagged)

    def read(self, record_id: str) -> dict[str, Any]:
        result: dict[str, Any] = self.inner.read(record_id)
        return result

    def query(self, *args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        result: Iterator[dict[str, Any]] = self.inner.query(*args, **kwargs)
        return result


def _bind_context(gov: Governor, extras: Mapping[str, Any]) -> None:
    """Merge `extras` into every evaluate() context on this instance.
    setdefault, not overwrite: an endpoint that explicitly sets a key
    wins over the middleware's ambient value."""
    original = gov.evaluate

    @functools.wraps(original)
    def evaluate(
        output: Any,
        context: Mapping[str, Any] | None = None,
        scale_path: str | None = None,
        *,
        checks: Any = None,
    ) -> Any:
        ctx = dict(context) if context is not None else {}
        for key, value in extras.items():
            ctx.setdefault(key, value)
        return original(output, ctx, scale_path, checks=checks)

    gov.evaluate = evaluate  # type: ignore[method-assign]


class GovernorMiddleware:
    """Request-scoped governance for a FastAPI app.

    Usage::

        mw = GovernorMiddleware(app, governor_factory=build_gov,
                                deployment="summarizer-svc")

        @app.post("/summarize")
        def summarize(body: Body, gov: Governor = Depends(mw.get_governor)):
            verdict = gov.evaluate(generate(body), context={"gate": "summarize"})
            ...
    """

    def __init__(
        self,
        app: Any,
        governor_factory: Callable[[], Governor],
        deployment: str,
        health_route: bool = True,
    ) -> None:
        self.app = app
        self.factory = governor_factory
        self.deployment = deployment
        _publish_request_annotation()
        if health_route:
            self._install_health_route(app)

    # ------------------------------------------------- request scoping
    def get_governor(self, request: Request) -> Governor:
        """The `Depends` target: a fresh governor bound to this request.

        One governor per request scope — correlation ids and per-request
        context must not leak across requests. The correlation id comes
        from the caller's ``x-correlation-id`` header when present (so an
        upstream trace id flows into the audit trail) and is minted fresh
        otherwise; it is exposed as ``gov.correlation_id`` so the
        endpoint can echo it in a response header.
        """
        gov = self.factory()
        gov.deployment = self.deployment
        correlation_id = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        gov.correlation_id = correlation_id  # type: ignore[attr-defined]
        _bind_context(gov, {"deployment": self.deployment, "correlation_id": correlation_id})
        if gov.log is not None:
            gov.log = _CorrelatedSink(gov.log, correlation_id)
        return gov

    # ------------------------------------------------------ health route
    def health(self) -> dict[str, Any]:
        """Registry + policy + sink status. Structure ONLY — no record
        contents, ever: a health endpoint that leaked decision data
        would be an audit-trail hole."""
        gov = self.factory()
        if gov.log is None:
            sink = "none"
        else:
            try:
                # Can the sink answer a query at all? The result is
                # discarded — only liveness leaves this function.
                next(iter(gov.log.query()), None)
                sink = "ok"
            except Exception as exc:  # noqa: BLE001 — status, not control flow
                sink = f"error: {type(exc).__name__}"
        return {
            "deployment": self.deployment,
            "checks": sorted(gov._registry),
            "policy": type(gov.policy).__name__,
            "sink": sink,
        }

    def _install_health_route(self, app: Any) -> None:
        add_api_route = getattr(app, "add_api_route", None)
        if callable(add_api_route):
            add_api_route(HEALTH_PATH, self.health, methods=["GET"])
            return
        get = getattr(app, "get", None)
        if callable(get):
            get(HEALTH_PATH)(self.health)
