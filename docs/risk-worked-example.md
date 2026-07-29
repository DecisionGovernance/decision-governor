# The risk interface, worked by hand

Every number on this page was computed with pencil and calculator before
the code existed, and the test suite (`tests/test_risk.py`) parses this
page and asserts the implementation reproduces every value exactly. If
either the docs or the code drifts, CI fails. "Risk mathematics, not
vibes" is checkable by anyone with a calculator — starting here.

## 1. The CVaR verdict, in domain units

Configuration common to all rows: `alpha = 0.05`, `cost_map` sends the
check `claims_supported` to the error cost `unsupported_claim`,
`scale_mitigation = 0.3` (a constrained execution retains 30% of the
error cost — the human-review or reduced-permission path is assumed to
catch ~70% of harm), `scale_friction = 0.5` (routing through a scale
path costs half an abstention in blocked-work friction), and
`ceiling_fraction = 0.5` (ALLOW is barred outright when the tail loss
exceeds half the full error cost, no matter what the argmin says).

The ceiling deserves a sentence of its own, because it is a different
*kind* of "no" than the cost minimization. The ceiling is a **deontic
bar**: some tail exposures are impermissible regardless of price. The
argmin is the **economic choice** among the verdicts that remain. When
p < alpha, the bar reads p > alpha x ceiling_fraction; with this
example's `ceiling_fraction = 0.5`, that is p > alpha/2, or a violation
probability above 0.05 x 0.5 = **2.5%**. At p >= alpha the Bernoulli
tail is already the full error cost, so it also exceeds this example's
half-cost ceiling. The decision record states which "no" fired
(`allow_barred_by_ceiling`), and the ceiling is a *fraction* of the
error cost rather than an absolute number so it scales with stakes
automatically: re-denominating costs never requires re-tuning it, and
because ceiling and cost scale together, raising a cost raises both the
tail loss and the bar proportionally — which is what keeps the
monotonicity property below provable rather than accidentally true.

The arithmetic, per row:

    p           = score x confidence
    cvar_allow  = cost_err                 if p >= alpha
                = (p / alpha) x cost_err   otherwise
    cost_scale  = scale_mitigation x cvar_allow
                  + abstention x scale_friction
    cost_abstain = abstention
    ALLOW barred when cvar_allow > ceiling_fraction x cost_err
    verdict     = argmin over surviving candidates, ties to the safer

Read row 1 out loud: with alpha = 0.05, a check reporting even 5%
violation probability makes the worst-5%-of-outcomes *entirely* loss —
CVaR refuses to be comforted by the 95%. Here p = 0.036 sits just under
the tail, so the tail is 72% occupied by loss: cvar_allow =
(0.036 / 0.05) x 100 = 72.0.

<!-- table:verdicts -->
| row | cost_err | abstention | score | confidence | p     | cvar_allow | allow_barred | cost_scale | cost_abstain | verdict |
|-----|----------|------------|-------|------------|-------|------------|--------------|------------|--------------|---------|
| 1   | 100.0    | 3.0        | 0.04  | 0.9        | 0.036 | 72.0       | true         | 23.1       | 3.0          | abstain |
| 2   | 100.0    | 50.0       | 0.04  | 0.9        | 0.036 | 72.0       | true         | 46.6       | 50.0         | scale   |
| 3   | 100.0    | 3.0        | 0.001 | 1.0        | 0.001 | 2.0        | false        | 2.1        | 3.0          | allow   |

Row-by-row, by hand:

- **Row 1** — because `ceiling_fraction = 0.5` and p = 0.036 < alpha =
  0.05, the deontic bar is p > alpha/2 = 0.025. It fires here;
  equivalently cvar_allow = (0.036/0.05) x 100 = 72.0 > 50, so **ALLOW
  is barred by the ceiling** and only SCALE and ABSTAIN get priced.
  cost_scale = 0.3 x 72.0 + 3.0 x 0.5 = 21.6 + 1.5 = 23.1.
  argmin(23.1, 3.0) → **ABSTAIN**: with abstention nearly free, refusing
  beats a still-risky constrained execution.
- **Row 2** — same evidence, so the bar fires identically (72.0 > 50);
  but abstention now costs 50 (think: a blocked medical-triage answer is
  genuinely expensive). cost_scale = 21.6 + 50.0 x 0.5 = 21.6 + 25.0 =
  46.6. argmin(46.6, 50.0) → **SCALE**: the costs, not the evidence,
  moved the verdict.
- **Row 3** — p = 0.001 < 0.025, the bar does not fire: cvar_allow =
  (0.001/0.05) x 100 = 2.0 ≤ 50, and all three candidates are priced.
  cost_scale = 0.3 x 2.0 + 1.5 = 2.1. argmin(2.0, 2.1, 3.0) → **ALLOW**.

Two footnotes the docstrings repeat: v0.1 computes *per-check Bernoulli*
CVaR (a single check result is a Bernoulli loss: `cost_err` with
probability p, else zero); joint-distribution CVaR across correlated
checks is exactly what the G-5 Clayton cascade stress-tests, and richer
loss models are the ruin-theory stub's territory. And the tie-break is
CVaR's asymmetry expressed at the boundary: a policy indifferent between
two verdicts takes the safer one.

## 2. Bühlmann–Straub credibility, worked through the factors

Three contexts, per-context trials `n` and failures `x`:

<!-- table:credibility-contexts -->
| context | n  | x | raw_rate | Z        | credibility_rate |
|---------|----|----|----------|----------|------------------|
| medical | 40 | 8  | 0.2      | 0.692308 | 0.175385         |
| finance | 40 | 4  | 0.1      | 0.692308 | 0.106154         |
| general | 20 | 0  | 0.0      | 0.529412 | 0.056471         |

The collective quantities, in the order you compute them by hand:

<!-- table:credibility-collective -->
| quantity | value     |
|----------|-----------|
| m        | 0.12      |
| s2       | 0.10      |
| a        | 0.005625  |
| k        | 17.777778 |

- Collective mean: m = (8 + 4 + 0) / (40 + 40 + 20) = 12/100 = **0.12**.
- Within-variance (weighted average of per-context binomial variance):
  s² = [40(0.2)(0.8) + 40(0.1)(0.9) + 20(0.0)(1.0)] / 100
     = [6.4 + 3.6 + 0] / 100 = **0.10**.
- Between-variance (Bühlmann–Straub moment estimator, floored at 0):
  weighted squared deviations = 40(0.2−0.12)² + 40(0.1−0.12)² +
  20(0.0−0.12)² = 0.256 + 0.016 + 0.288 = 0.56;
  numerator = 0.56 − (3−1)(0.10) = 0.36;
  denominator = 100 − (40² + 40² + 20²)/100 = 100 − 36 = 64;
  a = 0.36/64 = **0.005625**.
- Credibility coefficient: k = s²/a = 0.10/0.005625 = **17.777778**.
- Per context, Z = n/(n + k) and rate = Z·(x/n) + (1−Z)·m:
  - medical: Z = 40/57.777778 = **0.692308**;
    rate = 0.692308 x 0.2 + 0.307692 x 0.12 = **0.175385**.
  - finance: Z = **0.692308**;
    rate = 0.692308 x 0.1 + 0.307692 x 0.12 = **0.106154**.
  - general: Z = 20/37.777778 = **0.529412**;
    rate = 0.529412 x 0.0 + 0.470588 x 0.12 = **0.056471**.

The factors ship in the output object: an auditor sees Z = n/(n+k) with
its ingredients (n, k, m, the raw rate), never a bare number. A bad
track record earns high Z and pulls the estimate toward the context's
own history; a thin one keeps it near the collective.

## 3. The gate-level verdict: aggregate exposure

Per-check judging alone cannot price a gate: two checks each cheap
enough to ALLOW individually can jointly carry a tail worth
constraining. So the policy also judges the gate as a whole
(`judge_gate`), from the combined loss distribution of all selected
checks — independence assumed in v0.1, which is exactly the assumption
the G-5 Clayton cascade stress-tests. Beyond 12 active checks the exact
enumeration gives way to the comonotonic bound (the sum of individual
CVaRs); CVaR is subadditive, so that bound is conservative under any
dependence — the fallback tightens, never loosens.

This is a deliberate requirement amendment: the original Poisson
fallback was replaced by the comonotonic upper bound because a Poisson
approximation can under-price the tail. The bound is intentionally
pessimistic, so gates with more than 12 active checks can receive
stricter verdicts than independent exact mathematics would produce.

Two deterministic checks, each score 0.001 x confidence 1.0 against a
100-unit error cost, with alpha = 0.05, abstention = 3,
`scale_mitigation = 0.3`, and `scale_friction = 0.5`. The latter is a
concrete 0.5 x 3 = 1.5-unit scale-path friction in this fixture:

- Each check alone: cvar = (0.001/0.05) x 100 = 2.0; argmin(2.0, 2.1,
  3.0) → **ALLOW**, twice.
- The gate: the joint loss distribution is 200 with probability
  0.001² = 0.000001, 100 with probability 2 x 0.001 x 0.999 = 0.001998,
  else 0. The worst 5% of outcomes holds all of that mass:
  cvar_gate = (0.000001 x 200 + 0.001998 x 100) / 0.05 = 0.2/0.05 =
  **4.0**. cost_scale = 0.3 x 4.0 + 1.5 = **2.7**; abstention = 3.0.
  argmin(4.0, 2.7, 3.0) → **SCALE**.

The gate escalates from two individual ALLOWs to SCALE — aggregate
exposure, visible only at the gate level, made the constrained path the
cheapest honest option. Composition remains tighten-only: the aggregate
opinion can escalate the per-check composition, never relax it, and the
deontic ceiling stays per-check (in probability space it is cost-free —
p > alpha x ceiling_fraction — so adding a clean check can never dilute
total exposure into un-barring ALLOW).

<!-- table:aggregate -->
| quantity        | value |
|-----------------|-------|
| p_each          | 0.001 |
| cvar_each       | 2.0   |
| verdict_each    | allow |
| cvar_gate       | 4.0   |
| cost_scale_gate | 2.7   |
| cost_abstain    | 3.0   |
| verdict_gate    | scale |
