"""Embedding infrastructure and model pinning.

Embedding consumers use the deliberately small :class:`Embedder` seam:
``embed()`` supplies vectors while checks retain all distance and scoring
semantics, and ``describe()`` carries the embedder's pin block into audit
bundles. There is intentionally no batching or similarity API here: a swapped
embedder must not be able to quietly change a check's scoring semantics.

NLI is deliberately excluded. Entailment is text-native in v0.1 and has no
cross-modal analogue worth pretending to support.

Pins carry the repo, the *revision* (commit SHA — Hub repos mutate), and
the sha256 digest of the weight files. Mismatch is a hard error naming
both hashes. `revision`/`sha256` ship as None until frozen by the
one-time `python -m decision_governor.checks._models freeze <name>` run,
which downloads the model and prints the pin block to commit — digests
are computed from real weights, never invented.
"""
from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from decision_governor.core.errors import GovernorError

PINS: dict[str, dict[str, str | None]] = {
    "nli": {
        "repo": "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli",
        # Frozen July 27, 2026 via the freeze tool; digest computed from
        # the downloaded weights.
        "revision": "6f5cf0a2b59cabb106aca4c287eed12e357e90eb",
        "sha256": "bc0c491784bb51080bd5044f0326bcac8b87fd2ffe8dea36f7628de8bb5448e5",
    },
    "embedding": {
        "repo": "sentence-transformers/all-MiniLM-L6-v2",
        # Frozen July 27, 2026 via the freeze tool; digest computed from
        # the downloaded weights.
        "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41",
        "sha256": "6c86ea69c9c2077930fcac4cc72b642a06ffae52396043401ceeb95769e0d338",
    },
}

_WEIGHT_GLOBS = ("*.safetensors", "*.bin")
_cache: dict[str, Any] = {}


class Embedder(Protocol):
    """Internal embedding seam; ``describe`` is required for auditability."""

    modality: str

    def embed(self, items: list[Any]) -> NDArray[np.float64]:
        """Return one fixed-dimensional vector for each supplied item."""

    def describe(self) -> dict[str, str | None]:
        """Return the pin block carried into the consuming check's audit data."""


class PinnedTextEmbedder:
    """The shipped text embedder, loaded lazily through the frozen pin path."""

    modality = "text"

    def embed(self, items: list[Any]) -> NDArray[np.float64]:
        model = load("embedding")
        return np.asarray(model.encode(items), dtype=float)

    def describe(self) -> dict[str, str | None]:
        return {**describe("embedding"), "modality": self.modality}


# Both shipped embedding checks share this stateless lazy instance, so the
# pinned model is loaded and memoized exactly once by ``load``.
DEFAULT_TEXT_EMBEDDER = PinnedTextEmbedder()


def require_default_backend(name: str) -> None:
    """Constructor-time guard for checks whose backend was NOT injected.

    Until the one-time pin-freeze run commits real revision/sha256 values,
    the shipped defaults are explicitly unavailable — a check relying on
    them must fail loud at construction, not mid-evaluation. This is the
    recorded v0.1 posture (G-3 execution record): inject a backend, or
    freeze the pins.
    """
    pin = PINS[name]
    if pin["revision"] is None or pin["sha256"] is None:
        raise PinNotFrozen(name)


class ModelDepsMissing(GovernorError):
    def __init__(self, name: str, missing: str) -> None:
        super().__init__(
            f"loading the {name!r} model requires {missing!r}, which is not "
            "installed. Install the model extras with: "
            'pip install "decision-governor[llm]"'
        )


class PinNotFrozen(GovernorError):
    def __init__(self, name: str) -> None:
        super().__init__(
            f"model pin {name!r} has no frozen revision/digest yet. Run "
            f"`python -m decision_governor.checks._models freeze {name}` once "
            "(downloads the model, prints the pin block to commit), or pass "
            "an injected backend (embedder=/nli=) to the check; loading "
            "without a frozen pin is refused so an unverified model can "
            "never participate in a verdict."
        )


class PinVerificationError(GovernorError):
    def __init__(self, name: str, expected: str, actual: str) -> None:
        super().__init__(
            f"model {name!r} failed hash verification: pinned sha256 "
            f"{expected} but downloaded weights hash to {actual}. The "
            "cached download does not match the pinned release — delete the "
            "cache and re-download, or investigate before trusting it."
        )
        self.expected = expected
        self.actual = actual


def weight_files(model_dir: str | Path) -> list[Path]:
    root = Path(model_dir)
    found: list[Path] = []
    for pattern in _WEIGHT_GLOBS:
        found.extend(root.rglob(pattern))
    return sorted(found)


def hash_files(paths: Sequence[str | Path]) -> str:
    """sha256 over the concatenated file contents, in sorted-name order
    so the digest is stable across filesystems."""
    digest = hashlib.sha256()
    for path in sorted(Path(p) for p in paths):
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    return digest.hexdigest()


def verify(name: str, model_dir: str | Path) -> str:
    """Hash the downloaded weights and compare against the pin.
    Returns the digest on success; raises naming both hashes on mismatch."""
    pin = PINS[name]
    if pin["sha256"] is None or pin["revision"] is None:
        raise PinNotFrozen(name)
    files = weight_files(model_dir)
    if not files:
        raise PinVerificationError(name, str(pin["sha256"]), "<no weight files found>")
    actual = hash_files(files)
    if actual != pin["sha256"]:
        raise PinVerificationError(name, str(pin["sha256"]), actual)
    return actual


def describe(name: str) -> dict[str, str | None]:
    """The pin block verbatim, for audit bundles."""
    return dict(PINS[name])


def _snapshot(repo: str, revision: str | None) -> str:
    """Download (or reuse the cache) and return the local directory."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise ModelDepsMissing(repo, "huggingface_hub") from exc
    return str(snapshot_download(repo_id=repo, revision=revision))


def _load_backend(name: str, model_dir: str) -> Any:
    if name == "embedding":
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ModelDepsMissing(name, "sentence-transformers") from exc
        return SentenceTransformer(model_dir)
    if name == "nli":
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise ModelDepsMissing(name, "transformers") from exc
        return pipeline("text-classification", model=model_dir, top_k=None)
    raise KeyError(f"unknown model pin {name!r}; known: {sorted(PINS)}")


def load(name: str) -> Any:
    """Download if absent -> verify hash -> load -> memoize."""
    if name in _cache:
        return _cache[name]
    if name not in PINS:
        raise KeyError(f"unknown model pin {name!r}; known: {sorted(PINS)}")
    pin = PINS[name]
    if pin["revision"] is None or pin["sha256"] is None:
        raise PinNotFrozen(name)
    model_dir = _snapshot(str(pin["repo"]), pin["revision"])
    verify(name, model_dir)
    _cache[name] = _load_backend(name, model_dir)
    return _cache[name]


def freeze(name: str, resolve_revision: Callable[[str], str] | None = None) -> dict[str, str]:
    """Download the model at its current head, compute the real digest,
    and return the pin block to commit into PINS. Never guesses."""
    if name not in PINS:
        raise KeyError(f"unknown model pin {name!r}; known: {sorted(PINS)}")
    repo = str(PINS[name]["repo"])
    if resolve_revision is None:
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise ModelDepsMissing(name, "huggingface_hub") from exc

        def resolve_revision(r: str) -> str:
            return str(HfApi().model_info(r).sha)

    revision = resolve_revision(repo)
    model_dir = _snapshot(repo, revision)
    files = weight_files(model_dir)
    if not files:
        raise PinVerificationError(name, "<freeze>", "<no weight files found>")
    return {"repo": repo, "revision": revision, "sha256": hash_files(files)}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "freeze":
        block = freeze(args[1])
        print(f'"{args[1]}": {block!r},')
        return 0
    print("usage: python -m decision_governor.checks._models freeze <nli|embedding>")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
