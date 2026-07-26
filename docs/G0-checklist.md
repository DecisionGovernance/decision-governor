# Card G-0 — execution record

Steps executed in order:
1. Module map created as typed packages (core, risk, controls, checks,
   instrumentation, adversarial, inclusive, integrations).
2. pyproject.toml: extras [llm]/[fastapi]/[a11y], dev toolchain, mypy strict
   scoped to core/ and risk/, pytest+coverage, `governor` console script
   reserved for the G-4 CLI.
3. Frozen contracts committed as code: Decision (ALLOW/SCALE/ABSTAIN),
   CheckResult (bounds enforced), Check protocol with output: Any.
4. risk/ruin.py stub: pre-descoped v0.2 card visible in code.
5. Contract tests (tests/test_contracts.py) incl. runtime protocol check.
6. CI matrix 3.10–3.12: ruff, mypy, pytest. Pre-commit hooks.
7. CITATION.cff, CHANGELOG.md, .gitignore, README with the honest
   pre-release status block.
8. `git init`, first commit, push to the real repository;
9. Add LICENSE file (Apache-2.0 full text via GitHub's license picker).
10. Add CODE_OF_CONDUCT.md and .github/ISSUE_TEMPLATE/ (bug, feature, question).

