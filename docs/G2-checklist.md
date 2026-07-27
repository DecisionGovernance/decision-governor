# Card G-2 — execution record

Steps executed in order:
1. CostStructure (risk/costs.py): arbitrary named costs in user-chosen
   units, frozen; every cost strictly positive (a zero cost makes an
   error invisible); abstention mandatory — a policy where refusing is
   free will always refuse. Exposes get(), names, abstention,
   total_exposure (error costs only).
2. Check-to-cost bridge: cost_map {check_name: cost_name} given to the
   policy; expected_loss = score × confidence × cost; unmapped checks
   require an explicit default_cost or raise UnmappedCheck — silent
   defaults hide misconfiguration.
3. CVaRPolicy (risk/cvar.py): same Policy.judge() protocol as
   ThresholdPolicy — the engine did not change; that was G-1's seam.
   Verdict = argmin over candidate costs (allow / scale / abstain) in
   domain units, CVaR bound as a hard ceiling on ALLOW
   (ceiling_fraction=0.5), scale_mitigation=0.3, scale_friction=0.5,
   ties break toward the safer verdict.
4. Bernoulli tail computation, kept honest: closed-form CVaR of a
   single check's Bernoulli loss — p >= alpha means the tail is pure
   loss; else (p/alpha) × cost. Docstring states the v0.1 boundary:
   per-check Bernoulli only; joint CVaR is what the G-5 Clayton cascade
   stress-tests; richer loss models are the ruin stub's territory.
5. Bühlmann–Straub (risk/credibility.py): standard moment estimators
   (m, s² as weighted binomial variance, a floored at 0, k = s²/a,
   Z = n/(n+k)); the factors ship in CredibilityEstimate — never a bare
   rate. Deliberate edges: zero observations → Z=0 collective mean;
   a≈0 → k=∞, everyone collective; single context → raw rate,
   Z=1, degenerate=True.
6. Dynamic thresholds: optional rate_provider; credibility rate scales
   effective violation probability, tighten-biased (a good record
   relaxes at most to baseline, never below); adjustment factor written
   into the context risk block — no invisible numbers.
7. Acceptance gate: docs/risk-worked-example.md written FIRST, fully
   hand-calculated (three verdict rows: ABSTAIN / SCALE-because-costs /
   ALLOW; credibility table through m=0.12, s²=0.10, a=0.005625,
   k=17.777778, each Z). tests/test_risk.py parses the page's tables
   and asserts the implementation reproduces every value exactly, so
   docs and code cannot drift. Degenerate-case tests (zero
   observations, single context, all-costs-equal → safer) plus the
   monotonicity property at 200 examples: raising any error cost never
   moves the verdict toward ALLOW.

Design decision (mid-card, July 25, 2026): cvar_ceiling was
underspecified in the walkthrough pseudocode; resolved as
ceiling_fraction=0.5, a *fraction of the error cost* rather than an
absolute number. Rationale: cost-magnitude invariance — the ceiling
scales with stakes automatically, and because ceiling and cost scale
together, raising a cost raises both the tail loss and the bar
proportionally, which preserves the monotonicity property provably
rather than accidentally. Semantic layering made explicit in docs and
docstring: the ceiling is a deontic bar (in probability space, ALLOW
barred when p > alpha x ceiling_fraction — 2.5% at the defaults), the
argmin is the economic choice among the permitted; the risk block
records which "no" fired (allow_barred_by_ceiling). Worked example
updated to show the bar firing in rows 1-2 (p = 0.036 > 0.025), and a
ceiling-monotonicity property test added: lowering ceiling_fraction
never moves any verdict toward ALLOW.

Review finding addressed (July 26, 2026): per-check judge() alone could
not price aggregate exposure — two checks each individually cheap enough
to ALLOW can jointly carry a tail worth constraining (two p=0.001 checks
against a 100-cost error: each cvar 2.0 → ALLOW; the gate's joint tail
is 4.0 → SCALE at 2.7). Resolved with an aggregate policy boundary:
Policy may define judge_gate(records, context); the engine calls it
after per-check composition and composes the aggregate opinion
TIGHTEN-ONLY (it can escalate, never relax — enforced by the engine,
not trusted to the policy). CVaRPolicy.judge_gate enumerates the exact
joint Bernoulli loss distribution (independence assumed — G-5's Clayton
cascade stress-tests that) up to 12 active checks, then falls back to
the comonotonic bound Σ individual CVaRs, conservative under any
dependence by subadditivity. The deontic ceiling deliberately stays
per-check: in probability space it is cost-free (p > α × f), so adding
a clean check can never dilute aggregate exposure into un-barring
ALLOW; composition carries per-check bars to the gate. Worked example
gained section 3 (parsed as a fixture like the others); new tests:
aggregate escalation reproducing the docs, the >12-check conservative
bound, and a 200-example property that adding a learned check never
loosens the gate verdict with the aggregate stage in play.

Review close-out (July 26, 2026): P1 aggregate tighten-only implemented
as specified: the engine independently evaluates judge_gate() over the
deterministic subset and all records, then takes their severity maximum
with per-check composition; the EvilPolicy regression proves a learned
record cannot relax a deterministic ABSTAIN. P1 audit visibility
implemented: aggregate escalation now records gate_cvar and
decided_by="aggregate", and Verdict.reasons renders the gate tail-cost
line. P2 requirement amended: exact enumeration remains at <=12 active
checks and the requested Poisson fallback is replaced with the
comonotonic upper bound, explicitly because its error is one-sided and
tighten-biased. P2 property corrected and implemented: adding any check
cannot loosen a gate that already has deterministic evidence; a separate
ceiling-lift test records that clean deterministic evidence may
legitimately move a learned-only gate from SCALE to ALLOW. The
single-check aggregate-reduction property also now guards arithmetic
continuity with the original Bernoulli path.

Review close-out, round 3 (July 26, 2026): P2 accepted — the
"adding any check" property's strategy hardcoded the added check as
deterministic (extra tuple pinned True), so the stated universal quietly
narrowed to deterministic additions only. Broadened per reviewer with an
extra_deterministic boolean strategy; passed on 200 randomized examples
ranging over all four quadrants (clean/dirty × deterministic/learned
additions against mixed existing populations). The universal property —
adding any check never loosens a gate that already holds deterministic
evidence — is now verified over both kinds of addition.

Gate result (July 26, 2026): 43 tests passed (full suite), coverage
100% on decision_governor/, ruff clean, mypy strict on core/ and risk/
clean. The worked example reproduces the hand-calculated values to the
last decimal — "risk mathematics, not vibes" is now checkable by anyone
with a calculator. Card G-2 complete; G-3 checks can map into cost_map
and G-5 gets its stress-test target.
