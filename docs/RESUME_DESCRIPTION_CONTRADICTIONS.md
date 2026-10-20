# PaperPro | Review-only contradictions in resume descriptions

## Outcome and hard boundary

The existing five-dimension diagnostic report now detects a **narrow,
high-precision subset** of contradictions. It compares actual candidate
assertions, not keyword occurrences. The system must never label a missing
skill, job requirement, a previous learning stage, or another person's ability
as a contradiction.

**Status:** implemented and covered by synthetic counterexample tests; **not
calibrated on authorized real resumes**. All findings are candidates for human
review. Neither the resume, employment history, nor the score is rewritten.

## What is detected

A contradiction needs all of these conditions:
1. A recognized, explicit technical term (shared `rules.json` vocabulary).
2. Opposing statements within a comparable scope: current personal assertions
   in summary/self-evaluation/skills, or statements in one project/experience.
3. Logically incompatible dimensions:
   - Clearly proficient vs cannot use / not familiar.
   - Basic skill listed vs cannot use; NOT a mere claim of unfamiliarity.
   - Explicitly used technology vs explicitly never used it, in the same item.
4. Two exact, traceable statement snippets, each bound to its field path.

Example: `summary: 我熟悉 Python` versus `skills.0: Python：不会`.
This generates a verification issue with two citations, an interview question,
and a selectable, high-priority correction suggestion. Selected TXT exports
retain both snippets and paths. The UI never chooses which statement is true.

## Counterexamples deliberately ignored

- JD says `Kubernetes`, resume never mentions it: **not a contradiction**.
- `Python` in skills and `还没有 Python 商业项目经验`: both may be true.
- `Python` in skills and `不熟悉 Python 的高级优化`: basic skills do
  not imply advanced proficiency.
- `使用 Python` alongside `不熟悉 Python`: using a tool need not
  imply familiarity.
- `团队不熟悉 Docker` and the applicant lists Docker: different actors.
- `以前不会 Python，后来掌握 Python`: change over time.
- `项目初期尚未使用 SQL，后期使用 SQL`: change over time.
- A current skills list and a historical work-project mention: different scope.

Unclear tense, incomplete claims, unknown technology names, number-only
differences and broad semantic paraphrases are **not** solved by this rule.
These require real annotated examples and a separate admission gate, not
increasing the number of keyword patterns.

## Integration and invariants

- Owner: `app/diagnosis/claim_conflicts.py` produces review-only evidence.
- `app/diagnosis/engine.py` adds issues only when verification is enabled,
  creates a matching review question and a targeted, selectable suggestion.
- `app/diagnosis/api.py` includes the second field in selected-only exports.
- `frontend/src/CandidateDiagnosisApp.jsx` shows both claims.
- Candidate editing invalidates stale reports and selected suggestions.
- Existing timeline, score, rules version, AI consent and Classic export gates
  retain their previous owner and behavior.
- No background research database, external AI, or new inference dependency.

## Reproduce

```powershell
uv run --locked --python 3.12 python -m pytest tests/test_description_contradictions.py -q
uv run --locked --python 3.12 python -m pytest -q -k "not legacy_doc_end_to_end"
```

Browser acceptance needs an isolated local FastAPI instance plus frontend build:

```powershell
npm --prefix frontend run build
uv run --locked --python 3.12 python -m uvicorn app.main:app --host 127.0.0.1 --port 18766
# From frontend/ (in another terminal):
$env:PAPERPRO_E2E_BASE_URL="http://127.0.0.1:18766"
npx playwright test --project=chromium
```

The excluded Windows Word COM test is an existing runtime reliability issue,
not evidence that its feature succeeded. An authorized real-resume evaluation
would next track precision, missed explicit contradictions and human corrections
by category, before considering more general semantic models.
