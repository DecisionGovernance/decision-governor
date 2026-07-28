"""G-3 gate: known-good/known-bad fixture pairs per check, the
adversarial claims fixtures, masked PII evidence, pin verification, the
disparity monitor, the compliance family, and the integration fixture.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from decision_governor import Decision, Governor
from decision_governor.checks import (
    ChecklistItem,
    ClaimsSupported,
    OutputDomain,
    PIILeak,
    ProtectedAttributeLeak,
    StyleDrift,
    _models,
    claims,
    clamp01,
    default_checks,
    evaluate_checklist,
    nist_ai_rmf_profile,
    register_default_checks,
    verdict_disparity,
)
from decision_governor.checks.monitors import chi2_sf

# ------------------------------------------------------------ test doubles


class FakeEmbedder:
    """Deterministic embedder: known texts map to fixed vectors; unknown
    texts hash to a stable pseudo-vector."""

    def __init__(self, table=None, modality="text", pin=None):
        self.table = dict(table or {})
        self.modality = modality
        self.pin = pin or {
            "repo": "tests/fake-embedder",
            "revision": "fixture",
            "sha256": "fixture-digest",
            "modality": modality,
        }

    def embed(self, items):
        out = []
        for t in items:
            if t in self.table:
                out.append(np.asarray(self.table[t], dtype=float))
            else:
                rng = np.random.default_rng(abs(hash(t)) % (2**32))
                out.append(rng.normal(size=8))
        return np.vstack(out)

    def describe(self):
        return dict(self.pin)


@dataclass(frozen=True)
class AudioOutput:
    data: bytes
    modality: str = "audio"


def keyword_nli(rules, default=("entailed", 0.9)):
    """NLI double: first rule whose keyword appears in the hypothesis wins."""

    def nli(premise, hypothesis):
        for keyword, label, prob in rules:
            if keyword.lower() in hypothesis.lower():
                return label, prob
        return default

    return nli


# ------------------------------------------------------------------- base


def test_base_plumbing():
    check = PIILeak(custom_terms=["Initech"])
    described = check.describe()
    assert described["name"] == "pii_leak" and described["deterministic"] is True
    assert "Initech" not in str(described)  # config ships masked
    skipped = check.skip("not text")
    assert skipped.score == 0.0 and skipped.evidence == ["n/a: not text"]
    assert clamp01(-3.0) == 0.0 and clamp01(7.0) == 1.0 and clamp01(0.4) == 0.4


# ---------------------------------------------------------------- pii_leak


def test_pii_clean_text_passes():
    result = PIILeak().run("I improved throughput by 40% over two years.", {})
    assert result.score == 0.0 and result.evidence == []


def test_pii_dirty_text_flags_and_masks():
    text = (
        "Reach me at jane.doe@example.com or 555-867-5309. "
        "SSN 123-45-6789, home 42 Elm Street."
    )
    result = PIILeak().run(text, {})
    assert result.score == 1.0 and result.confidence == 1.0
    joined = " ".join(result.evidence)
    assert "email:" in joined and "phone:" in joined
    assert "ssn:" in joined and "address:" in joined
    assert "offset" in joined
    # The log must never contain the PII it caught.
    for secret in ("jane.doe@example.com", "555-867-5309", "123-45-6789", "42 Elm Street"):
        assert secret not in joined
    assert "j***@***.com" in joined


def test_pii_custom_terms_from_config_and_context():
    check = PIILeak(custom_terms=["Initech"])
    result = check.run(
        "Currently at Initech, previously Globex.",
        {"custom_terms": ["Globex"]},
    )
    joined = " ".join(result.evidence)
    assert result.score == 1.0
    assert joined.count("custom-term:") == 2
    assert "Initech" not in joined and "Globex" not in joined


# ------------------------------------------------------------ output_domain


def test_domain_no_rules_skips():
    result = OutputDomain().run("anything", {})
    assert result.score == 0.0
    assert result.evidence == ["n/a: no domain rules configured"]


def test_domain_score_is_fraction_of_rules_violated():
    check = OutputDomain(
        min_length=10,
        max_length=1000,
        required_sections=("experience", "education"),
    )
    result = check.run("A letter about my experience only.", {})
    # 4 rules, 1 violated (education missing) -> 0.25, rule named.
    assert result.score == 0.25
    assert result.evidence == ["required section missing: 'education'"]


def test_domain_json_schema_subset_and_context_rules():
    check = OutputDomain()
    schema = {"required": ["name", "amount"], "properties": {"amount": {"type": "number"}}}
    result = check.run(
        '{"name": "refund"}', {"domain_rules": {"json_schema": schema}}
    )
    assert result.score == 1.0  # the schema rule is violated
    assert "required property missing: 'amount'" in " ".join(result.evidence)
    clean = check.run(
        '{"name": "refund", "amount": 12.5}',
        {"domain_rules": {"json_schema": schema}},
    )
    assert clean.score == 0.0


# ----------------------------------------------- protected_attribute_leak


def test_protected_clean_letter_passes():
    text = "I bring six years of backend experience and a love of testing."
    assert ProtectedAttributeLeak().run(text, {}).score == 0.0


def test_protected_flags_name_the_category_not_just_the_term():
    text = "As a mother of three, class of 1998, I bring perspective."
    result = ProtectedAttributeLeak().run(text, {})
    assert result.score == 1.0
    joined = " ".join(result.evidence)
    assert "family-status inference: 'As a mother of'" in joined
    assert "age term: 'class of 1998'" in joined


def test_protected_categories_are_configurable_but_strict_by_default():
    text = "My church community taught me service."
    assert ProtectedAttributeLeak().run(text, {}).score == 1.0  # strict default
    narrowed = ProtectedAttributeLeak(categories=["age", "health"])
    assert narrowed.run(text, {}).score == 0.0
    with pytest.raises(ValueError, match="unknown protected categories"):
        ProtectedAttributeLeak(categories=["zodiac"])


# ------------------------------------------------------------ model pins


def test_hash_files_is_stable_and_order_independent(tmp_path):
    a = tmp_path / "a.bin"
    b = tmp_path / "b.safetensors"
    a.write_bytes(b"alpha")
    b.write_bytes(b"beta")
    assert _models.hash_files([a, b]) == _models.hash_files([b, a])


def test_verify_success_and_mismatch_names_both_hashes(tmp_path, monkeypatch):
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"weights")
    digest = _models.hash_files([weights])
    monkeypatch.setitem(
        _models.PINS, "nli",
        {"repo": "test/repo", "revision": "abc123", "sha256": digest},
    )
    assert _models.verify("nli", tmp_path) == digest

    monkeypatch.setitem(
        _models.PINS, "nli",
        {"repo": "test/repo", "revision": "abc123", "sha256": "deadbeef"},
    )
    with pytest.raises(_models.PinVerificationError) as excinfo:
        _models.verify("nli", tmp_path)
    assert "deadbeef" in str(excinfo.value) and digest in str(excinfo.value)


_UNFROZEN = {"repo": "test/repo", "revision": None, "sha256": None}


def test_unfrozen_pin_refuses_to_load_with_actionable_message(monkeypatch):
    monkeypatch.setitem(_models.PINS, "nli", dict(_UNFROZEN))
    with pytest.raises(_models.PinNotFrozen, match="freeze nli"):
        _models.load("nli")
    with pytest.raises(KeyError, match="unknown model pin"):
        _models.load("mystery")


def test_default_backends_fail_loud_at_construction_while_pins_unfrozen(monkeypatch):
    # The guard behavior, pinned independently of the shipped pin state:
    # non-injected defaults are unavailable while pins are unfrozen, and
    # the failure happens at construction, never mid-evaluation.
    monkeypatch.setitem(_models.PINS, "embedding", dict(_UNFROZEN))
    monkeypatch.setitem(_models.PINS, "nli", dict(_UNFROZEN))
    with pytest.raises(_models.PinNotFrozen, match="embedder=/nli="):
        StyleDrift()
    with pytest.raises(_models.PinNotFrozen):
        ClaimsSupported(embedder=FakeEmbedder())  # nli left as default
    with pytest.raises(_models.PinNotFrozen):
        ClaimsSupported(nli=keyword_nli([]))  # embedder left as default


def test_shipped_embedding_pin_is_frozen_with_real_digest():
    # The July 27 freeze run: real revision + sha256, never None, and the
    # digest has sha256 shape. StyleDrift() default construction works.
    pin = _models.describe("embedding")
    assert pin["revision"] and pin["sha256"]
    assert len(pin["sha256"]) == 64
    assert StyleDrift().embedder is _models.DEFAULT_TEXT_EMBEDDER


def test_frozen_pins_allow_default_construction(monkeypatch):
    frozen = {"repo": "r", "revision": "sha", "sha256": "digest"}
    monkeypatch.setitem(_models.PINS, "embedding", dict(frozen))
    monkeypatch.setitem(_models.PINS, "nli", dict(frozen))
    # Construction succeeds without loading anything; loading stays lazy.
    assert StyleDrift().embedder is _models.DEFAULT_TEXT_EMBEDDER
    assert ClaimsSupported().top_k == ClaimsSupported.TOP_K


def test_load_verifies_then_memoizes(tmp_path, monkeypatch):
    weights = tmp_path / "model.bin"
    weights.write_bytes(b"pinned-weights")
    digest = _models.hash_files([weights])
    monkeypatch.setitem(
        _models.PINS, "embedding",
        {"repo": "test/repo", "revision": "abc123", "sha256": digest},
    )
    monkeypatch.setattr(_models, "_snapshot", lambda repo, revision: str(tmp_path))
    monkeypatch.setattr(_models, "_load_backend", lambda name, d: f"loaded:{d}")
    monkeypatch.setattr(_models, "_cache", {})
    assert _models.load("embedding") == f"loaded:{tmp_path}"
    monkeypatch.setattr(
        _models, "_snapshot",
        lambda repo, revision: pytest.fail("second load must be memoized"),
    )
    assert _models.load("embedding") == f"loaded:{tmp_path}"


def test_freeze_computes_real_digest_from_download(tmp_path, monkeypatch):
    weights = tmp_path / "model.bin"
    weights.write_bytes(b"fresh-weights")
    monkeypatch.setattr(_models, "_snapshot", lambda repo, revision: str(tmp_path))
    block = _models.freeze("nli", resolve_revision=lambda repo: "sha-at-head")
    assert block["revision"] == "sha-at-head"
    assert block["sha256"] == _models.hash_files([weights])
    assert _models.describe("nli")["repo"] == block["repo"]


# ------------------------------------------------------------ style_drift


# Unit vectors at angles 0/10/20 degrees; "same author" sits at 5 degrees
# (inside the refs' own spread), the drifted output at 120 degrees.
STYLE_TABLE = {
    "ref one": [1.0, 0.0],
    "ref two": [0.9848, 0.1736],
    "ref three": [0.9397, 0.3420],
    "same author, new topic": [0.9962, 0.0872],
    "SYNERGISTIC LEVERAGED PARADIGM DELIVERABLES": [-0.5, 0.8660],
}


def _style_check():
    return StyleDrift(embedder=FakeEmbedder(STYLE_TABLE))


def test_style_needs_a_baseline():
    result = _style_check().run("anything", {"style_refs": ["ref one"]})
    assert result.evidence == ["n/a: need at least 2 style_refs for a personal baseline"]


def test_unknown_modality_caps_at_scale():
    gov = Governor()
    gov.register(StyleDrift(embedder=FakeEmbedder()))
    verdict = gov.evaluate(b"unclassified output", {"style_refs": ["ref one"]})
    assert verdict.decision is Decision.SCALE
    assert verdict.records[0].result.evidence == [
        "n/a: output modality 'unknown' != embedder modality 'text'"
    ]


def test_declared_audio_output_runs_through_custom_embedder():
    pin = {
        "repo": "acme/audio-embedding",
        "revision": "audio-fixture",
        "sha256": "audio-digest",
        "modality": "audio",
    }
    output = AudioOutput(b"candidate audio")
    refs = [b"audio ref one", b"audio ref two"]
    table = {
        refs[0]: [1.0, 0.0],
        refs[1]: [0.9848, 0.1736],
        output: [0.9962, 0.0872],
    }
    check = StyleDrift(embedder=FakeEmbedder(table, modality="audio", pin=pin))
    gov = Governor()
    gov.register(check)
    verdict = gov.evaluate(output, {"style_refs": refs})
    assert verdict.decision is Decision.SCALE
    assert verdict.records[0].result.evidence[0].startswith("distance ")
    assert check.describe()["config"]["embedder"] == pin


def test_context_declared_audio_bytes_run_through_custom_embedder():
    output = b"candidate audio"
    refs = [b"audio ref one", b"audio ref two"]
    table = {
        refs[0]: [1.0, 0.0],
        refs[1]: [0.9848, 0.1736],
        output: [0.9962, 0.0872],
    }
    result = StyleDrift(embedder=FakeEmbedder(table, modality="audio")).run(
        output,
        {"output_modality": "audio", "style_refs": refs},
    )
    assert result.evidence[0].startswith("distance ")


def test_custom_text_embedder_can_produce_allow():
    gov = Governor()
    gov.register(PIILeak())  # clean deterministic evidence authorizes ALLOW
    gov.register(StyleDrift(embedder=FakeEmbedder(STYLE_TABLE)))

    verdict = gov.evaluate(
        "same author, new topic",
        {"style_refs": ["ref one", "ref two", "ref three"]},
    )

    assert verdict.decision is Decision.ALLOW


def test_style_text_score_equivalence_after_embedder_seam():
    refs = ["ref one", "ref two", "ref three"]
    output = "same author, new topic"
    embedder = FakeEmbedder(STYLE_TABLE)
    result = StyleDrift(embedder=embedder).run(output, {"style_refs": refs})

    vectors = embedder.embed(refs + [output])
    ref_vectors, out_vector = vectors[:-1], vectors[-1]
    centroid = ref_vectors.mean(axis=0)
    baseline = np.array([
        1.0 - np.dot(vector, centroid) /
        (np.linalg.norm(vector) * np.linalg.norm(centroid))
        for vector in ref_vectors
    ])
    base_mean = float(baseline.mean())
    mad = float(np.abs(baseline - base_mean).mean())
    old_score = max(
        0.0,
        min(
            1.0,
            (
                (1.0 - np.dot(out_vector, centroid) /
                 (np.linalg.norm(out_vector) * np.linalg.norm(centroid)))
                - base_mean
            ) / (StyleDrift.K_MAD * max(mad, 1e-9)),
        ),
    )
    assert result.score == pytest.approx(old_score)


def test_style_same_author_different_topic_passes():
    context = {"style_refs": ["ref one", "ref two", "ref three"]}
    result = _style_check().run("same author, new topic", context)
    assert result.score < 0.5
    assert "vs personal baseline" in result.evidence[0]


def test_style_drifted_output_flags_and_confidence_tracks_sample_count():
    context = {"style_refs": ["ref one", "ref two", "ref three"]}
    result = _style_check().run(
        "SYNERGISTIC LEVERAGED PARADIGM DELIVERABLES", context
    )
    assert result.score == 1.0
    assert result.confidence == pytest.approx(3 / 5)  # 3 refs of MIN_REFS=5


# -------------------------------------------------------- claims_supported


FACTS = [
    "Worked as a senior developer from 2021 to 2023.",
    "Contributed to a team that reduced API latency by 40%.",
    "Holds a BSc in Computer Science.",
]


def test_claim_detection_is_biased_toward_over_detection():
    assert claims.is_claim("I led a team of five engineers in 2022.")
    assert claims.is_claim("My work reduced costs by 30%.")
    assert not claims.is_claim("I hope to grow with your company.")
    assert not claims.is_claim("Would you consider a fall start date?")


def test_claims_skips_without_facts():
    check = ClaimsSupported(nli=keyword_nli([]), embedder=FakeEmbedder())
    assert check.run("I led five teams.", {}).evidence == [
        "n/a: no facts provided in context['facts']"
    ]


def test_claims_exaggeration_lands_neutral_or_worse():
    # The product's honesty in miniature: "led" vs the profile's
    # "contributed to" must not pass as supported.
    check = ClaimsSupported(
        nli=keyword_nli([("led a team", "neutral", 0.71)]),
        embedder=FakeEmbedder(),
    )
    result = check.run(
        "I led a team of five that shipped the billing system.",
        {"facts": FACTS},
    )
    assert result.score == pytest.approx(0.6 * 0.71)
    assert result.confidence == pytest.approx(0.71)
    assert any("NEUTRAL 0.71" in line for line in result.evidence)
    assert any("nearest facts:" in line for line in result.evidence)


def test_claims_compositional_smuggle_is_caught():
    check = ClaimsSupported(
        nli=keyword_nli([("drove our 40% latency win", "contradicted", 0.83)]),
        embedder=FakeEmbedder(),
    )
    result = check.run(
        "I bring the rigor that drove our 40% latency win.",
        {"facts": FACTS},
    )
    assert result.score == pytest.approx(0.83)  # contradicted, weight 1.0


def test_claims_clean_paraphrase_passes():
    # Guarding against over-zealousness: supported rephrasing scores 0.
    check = ClaimsSupported(
        nli=keyword_nli([], default=("entailed", 0.94)),
        embedder=FakeEmbedder(),
    )
    result = check.run(
        "I contributed to reducing API latency by 40% as a senior developer.",
        {"facts": FACTS},
    )
    assert result.score == 0.0
    assert result.confidence == pytest.approx(0.94)


def test_claims_worst_claim_wins_not_the_mean():
    check = ClaimsSupported(
        nli=keyword_nli(
            [("fabricated", "contradicted", 0.9)], default=("entailed", 0.95)
        ),
        embedder=FakeEmbedder(),
    )
    result = check.run(
        "I hold a BSc in Computer Science. I invented the fabricated award in 2020.",
        {"facts": FACTS},
    )
    assert result.score == pytest.approx(0.9)  # one bad claim dominates


def test_claims_retrieval_selects_nearest_facts():
    table = {
        "fact near": [1.0, 0.0], "fact far": [0.0, 1.0],
        "I managed the near thing in 2022.": [0.99, 0.01],
    }
    seen = {}

    def spy_nli(premise, hypothesis):
        seen["premise"] = premise
        return "entailed", 0.9

    check = ClaimsSupported(nli=spy_nli, embedder=FakeEmbedder(table), top_k=1)
    check.run(
        "I managed the near thing in 2022.",
        {"facts": ["fact near", "fact far"]},
    )
    assert seen["premise"] == "fact near"


def test_claims_no_verifiable_claims_is_clean():
    check = ClaimsSupported(nli=keyword_nli([]), embedder=FakeEmbedder())
    result = check.run("I hope to grow. I would love to join.", {"facts": FACTS})
    assert result.score == 0.0
    assert result.evidence == ["no verifiable claims detected"]


# -------------------------------------------------------- verdict_disparity


def test_disparity_flags_a_real_gap():
    records = [("A", Decision.ALLOW)] * 40 + [("A", Decision.ABSTAIN)] * 10
    records += [("B", Decision.ALLOW)] * 25 + [("B", Decision.ABSTAIN)] * 25
    report = verdict_disparity(records)
    assert report.flagged and report.p_value < 0.05
    assert report.rate_gap > 0.1
    assert any("DISPARITY FLAGGED" in line for line in report.lines)


def test_disparity_credibility_shrinks_tiny_cohorts():
    records = [("big", Decision.ALLOW)] * 60 + [("big", Decision.ABSTAIN)] * 12
    records += [("tiny", Decision.ABSTAIN)] * 2 + [("tiny", Decision.ALLOW)]
    report = verdict_disparity(records)
    tiny = next(c for c in report.cohorts if c.cohort == "tiny")
    # Raw rate 2/3 screams; the credibility-weighted rate is pulled back
    # toward the collective mean (~0.19), and Z ships with it.
    assert tiny.constrained_rate == pytest.approx(2 / 3)
    assert tiny.credibility_rate < tiny.constrained_rate - 0.1
    assert tiny.credibility_rate > 0.19  # shrunk toward, not past, the mean
    assert 0.0 < tiny.Z < 1.0


def test_disparity_no_gap_is_not_flagged():
    records = ([("A", Decision.ALLOW)] * 30 + [("A", Decision.SCALE)] * 10
               + [("B", Decision.ALLOW)] * 30 + [("B", Decision.SCALE)] * 10)
    report = verdict_disparity(records)
    assert not report.flagged and report.p_value > 0.9


def test_chi2_survival_function_matches_known_critical_values():
    assert chi2_sf(3.841, 1) == pytest.approx(0.05, abs=5e-4)
    assert chi2_sf(5.991, 2) == pytest.approx(0.05, abs=5e-4)
    assert chi2_sf(0.0, 1) == 1.0


def test_disparity_requires_records():
    with pytest.raises(ValueError, match="at least one"):
        verdict_disparity([])


# --------------------------------------------------------------- compliance


def test_checklist_runner_statuses():
    items = [
        ChecklistItem("A-1", "tighten-only enforced", "automated",
                      "tighten_only_composition"),
        ChecklistItem("A-2", "time travel implemented", "automated",
                      "flux_capacitor"),
        ChecklistItem("B-1", "owner assigned", "attested"),
        ChecklistItem("B-2", "reviewed quarterly", "attested"),
    ]
    report = evaluate_checklist(items, attestations={"B-1": True})
    assert [i.id for i in report.covered] == ["A-1"]
    assert [i.id for i in report.attested] == ["B-1"]
    assert [i.id for i in report.not_covered] == ["A-2", "B-2"]
    assert report.coverage == 0.5
    assert any("[not_covered] A-2" in line for line in report.lines)


def test_checklist_item_validation():
    with pytest.raises(ValueError, match="check_type"):
        ChecklistItem("X", "req", "vibes")
    with pytest.raises(ValueError, match="must name the SDK capability"):
        ChecklistItem("X", "req", "automated")


def test_nist_rmf_profile_loads_and_is_honest():
    items = nist_ai_rmf_profile()
    assert len(items) >= 10
    report = evaluate_checklist(items)
    # The honesty test: capabilities that don't exist yet render
    # not_covered — decision_logging rows stay red until G-4 lands.
    not_covered_capabilities = {i.capability for i in report.not_covered}
    assert "decision_logging" in not_covered_capabilities
    assert "adversarial_toolkit" in not_covered_capabilities
    assert len(report.covered) >= 5  # and the real capabilities show green
    assert 0.0 < report.coverage < 1.0


# --------------------------------------------------------------- integration


def _governed(extra_checks=()):
    gov = Governor()
    register_default_checks(gov)
    for check in extra_checks:
        gov.register(check)
    return gov


def test_integration_good_document_allows_end_to_end():
    style = StyleDrift(embedder=FakeEmbedder(STYLE_TABLE))
    claims_check = ClaimsSupported(
        nli=keyword_nli([], default=("entailed", 0.95)), embedder=FakeEmbedder()
    )
    gov = _governed([style, claims_check])
    verdict = gov.evaluate(
        "same author, new topic",
        {
            "style_refs": ["ref one", "ref two", "ref three"],
            "facts": FACTS,
        },
    )
    assert verdict.decision is Decision.ALLOW
    assert verdict.reasons == []


def test_integration_bad_document_abstains_with_the_check_named():
    gov = _governed()
    verdict = gov.evaluate(
        "Contact me at jane.doe@example.com about the role.", {}
    )
    assert verdict.decision is Decision.ABSTAIN
    assert any(line.startswith("pii_leak") for line in verdict.reasons)
    assert "jane.doe@example.com" not in " ".join(verdict.reasons)


def test_default_checks_are_the_deterministic_trio():
    names = sorted(check.name for check in default_checks())
    assert names == ["output_domain", "pii_leak", "protected_attribute_leak"]
    assert all(check.deterministic for check in default_checks())


# ------------------------------------------------------- branch coverage


def test_extract_text_handles_objects_and_fallback():
    from decision_governor.checks import extract_text

    class WithText:
        text = "the text attribute"

    class Action:
        def __str__(self):
            return "tool_call(delete)"

    assert extract_text("plain") == "plain"
    assert extract_text(WithText()) == "the text attribute"
    assert extract_text(Action()) == "tool_call(delete)"


def test_domain_remaining_rule_branches():
    check = OutputDomain(max_length=5, forbidden_sections=("salary",))
    result = check.run("my salary expectations are high", {})
    joined = " ".join(result.evidence)
    assert "max_length:" in joined and "forbidden section present:" in joined
    assert result.score == 1.0
    assert check._config() == {"max_length": 5, "forbidden_sections": ("salary",)}

    schema = {"required": [], "properties": {"n": {"type": "integer"}}}
    assert OutputDomain._schema_violations("not json {", schema) == [
        "json_schema: output is not valid JSON"
    ]
    assert OutputDomain._schema_violations("[1, 2]", schema) == [
        "json_schema: output is not a JSON object"
    ]
    assert OutputDomain._schema_violations({"n": True}, schema) == [
        "json_schema: property 'n' is not of type 'integer'"
    ]


def test_fairness_extra_terms_screen():
    check = ProtectedAttributeLeak(extra_terms=[("age", r"\bsilver generation\b")])
    result = check.run("Proud member of the silver generation.", {})
    assert result.score == 1.0
    assert "age term: 'silver generation'" in " ".join(result.evidence)


def test_monitor_accepts_string_decisions_and_degenerate_tables():
    # Strings from a serialized log work like Decision members.
    report = verdict_disparity([("A", "allow"), ("A", "abstain"), ("B", "allow")])
    assert report.cohorts[0].n == 2
    # All-allowed table: no evidence of disparity, never a divide-by-zero.
    calm = verdict_disparity([("A", "allow")] * 5 + [("B", "allow")] * 5)
    assert calm.chi2 == 0.0 and calm.p_value == 1.0 and not calm.flagged


def test_chi2_sf_small_x_series_branch():
    # x < a + 1 exercises the series expansion rather than the
    # continued fraction; sf(1.145, 3) ~ 0.766 (table value).
    assert chi2_sf(1.145, 3) == pytest.approx(0.766, abs=5e-3)


def test_compliance_json_checklist_and_empty_report(tmp_path):
    from decision_governor.checks import evaluate_checklist, load_checklist

    path = tmp_path / "items.json"
    path.write_text(
        '[{"id": "J-1", "requirement": "logged", "check_type": "automated",'
        ' "capability": "audit_reasons"}]',
        encoding="utf-8",
    )
    items = load_checklist(path)
    assert items[0].capability == "audit_reasons"
    bad = tmp_path / "bad.json"
    bad.write_text('{"not": "a list"}', encoding="utf-8")
    with pytest.raises(TypeError, match="list of items"):
        load_checklist(bad)
    assert evaluate_checklist([]).coverage == 0.0


def test_style_zero_vector_is_maximal_distance_and_config_reports():
    table = {"a": [1.0, 0.0], "b": [0.9, 0.1], "zero": [0.0, 0.0]}
    check = StyleDrift(embedder=FakeEmbedder(table))
    result = check.run("zero", {"style_refs": ["a", "b"]})
    assert result.score == 1.0  # zero-norm output: nothing in common
    assert check._config()["embedder"]["repo"] == "tests/fake-embedder"
