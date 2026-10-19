# R7–R10: Candidate Resume Diagnosis (2026-10-19)

## Problem and objective
Extend existing PaperPro from resume cleanup into a candidate-facing five-dimension diagnosis. Input is a reviewed, editable resume plus a role and/or company. Output is an evidence-linked diagnosis, suggestions (>=8, each location/problem/action/example), interview follow-up questions, and a selected-only todo list downloadable as PDF/TXT.

## Reference and limits
- 8m54s HR product video supplied 2026-10-19. The source UI is a *batch HR dashboard*, not a candidate flow. Borrow its navy side rail, spacious white cards, layered summary→table→detail design and status colors. Do not import its bulk list, hiring decisions, applicant ranking or claims of backend capabilities.
- User's R7–R10 message is the feature contract. No authoritative 美太 HR five-output rule implementation was found under accessible E:/company_work project roots. Therefore rubric values and weights are **declared provisional configurable conventions**, not a claim of identical production HR scores. The five category names/shape are aligned; exact numeric parity needs the HR rule owner to provide their source.
- No permissioned 20-real-resume QA corpus is currently available. Do not claim R7-1 >=90% or R8-2 photo >=85% until those sets are explicitly reviewed. No physical iOS/Android device in this Windows setup; Playwright mobile emulation is only partial evidence.

## User journey / states
1 Upload: PDF/DOC/DOCX/PNG/JPEG <=10 MB, or paste text; SHA256 raw evidence fingerprint; progress messages. Upload must not change raw bytes.
2 Review: fixed structured schema with name/contact, education, experience (company, role, start/end), projects, skills, certificates, self-evaluation, additional; every field editable.
3 Target: role and/or company required; optional pasted JD; role autocomplete based on known strings. Empty role+company = no next action.
4 Report: source-based 5-block HR-perspective diagnosis with independently selectable sections, deterministic match coefficients/weights, purely computed employment timeline, provenance/version/time. The AI narrative (when voluntarily configured+authorized) sees only the computed figures and rule table; cannot invent dates. A failed section returns its own status and does not suppress the other four.
5 Action: >=8 prioritized suggestions, each four required fields; issue→interview question; user selects specific suggestions and exports TXT/PDF. No rewriting entire original resume.

Back/forward retains state. New file or meaningful edit invalidates a previous report. The classic resume editing flow remains available at /classic; the new candidate flow is / or /diagnosis.

## Engineering model and invariant
**Objects:** immutable upload bytes (not stored) → extracted source text/hash → human-corrected profile → target → deterministic rule-engine report → human-selected suggestion IDs → todo export.
**Authority:** app/parser.py owns extraction; app/diagnosis/schema.py owns structured input contract; app/diagnosis/rules.json is the only source of thresholds, keyword sets and scoring rules; app/diagnosis/engine.py owns calculations; /api/diagnosis/* owns validation/export; frontend/src/CandidateDiagnosisApp.jsx owns wizard state. app/settings.py remains sole credential owner.
**Invariant:** no source bytes are modified; no fabricated employment dates, company facts or metrics; absence of evidence must be marked as "简历未体现", not proof of incompetence; score is reproducible for the same normalized input/rules version; suggestions and issues point to visible reviewed field paths; TODO export contains selected IDs only; toggles and partial failures never remove unrelated completed sections.

## Testing and acceptance strategy
- Parser API tests: supported file kinds, 10MB cutoff, text pasting, SHA fingerprint, editable key fields and unchanged original.
- Rule engine unit: 0–1 coefficients, weights, >=6 items, same input => same score; gap days, overlap and total employment periods checked manually on known dates; 5 outputs, three potential evidence entries, 8 four-field suggestions, selection check.
- Endpoint smoke: upload/paste→review→target→diagnostics→selected PDF/TXT and interview questions; disabled dimension fails independently.
- Browser Chrome: upload, edit, target disabled when blank, 5-stage backward movement, report all dimensions, 8 suggestions, export selected; invalid file and no hanging state >10sec.
- Source evidence validation and independent adversarial stage review. Do not claim production calibrated match scores or target-company private knowledge without JD/company data.

## Phase plan
- P0-A: schema+parser adapter+paste endpoint with tests.
- P0-B: deterministic common rule source and complete 5-section report with tests.
- P0-C: Mantine new candidate wizard, video-derived visual hierarchy, responsive use and actual browser smoke.
- P1-D: optional DeepSeek narrative bound to computed facts and same rule table; independent failure containment.
- P1-E: model adversarial tests, long docs, edge cases, user-data QA gates. Current deterministic and Chrome regression evidence exists; real HR outcomes and sample-quality gates remain outstanding.

## 2026-10-19 checkpoint
- Candidate flow at `/` and legacy editor at `/classic`, with source hash and human-controlled exports.
- Related employment months computed only from dated role/duty evidence, using the union of calendar months (no overlapping double-count).
- Asynchronous diagnosis results are invalidated by target/resume edits or navigation back; stale results cannot override newer user intentions.
- Role-specific routing and negative evidence tests prevent generic engineering aliases and explicit negations from inflating weights. Employment duration and role families are tested against civil engineering, software and data roles; ambiguous claims remain insufficient rather than affirmative evidence.
- Optional AI authority is limited to selecting `narrative_codes` and existing `evidence_paths` from rules.json; all displayed narration is rendered locally, and invalid provider URLs or unsupported claims fail closed to deterministic output.
- Input-generation generations invalidate when target, résumé or pasted source changes; enabled-section checkbox event values are captured synchronously. HR label duplicate checks ignore contact-only changes.
- Added rule version 0.3.0 synthetic counterfactual validation: 1,680 pairs over 3 fixed seeds × 4 job families × 7 invariants × 20 JD variations; all expected monotonicity/invariance constraints pass. New failures actually found and fixed: duplicate project claims, duplicate work periods boosting project score, and Git JD keyword missing from the shared factor vocabulary. This is not external HR validity.
- Core backend/diagnosis and 25 Chrome E2E tests green as of 2026-10-19. Full Python suite ran to completion with 90% coverage but emitted legacy Windows Word COM RPC exceptions; this remains a platform observation, not a claim of fault-free native COM operation.
- Watchdog registration was attempted via controlled API; its observed state is `connected=false`, `persistent_turn_identity_unavailable` and must not be portrayed as live supervision.
- Extended R7/R8 simulated format QA: 20 DOCX/PDF ×13 fields => 260/260; 4 synthetic scan images ×13 fields => 49/52 after safe OCR text normalization. Actual iOS/Android gallery hardware remains unvalidated; see docs/SYNTHETIC_PARSER_QA.md.
- R7-5/R7-6 advice now separates actual evidence gaps (`需要修正`) from optional improvements (`可选深化`). A fully dated, well-evidenced résumé no longer receives unsupported allegations of missing dates or metric baselines; exports retain each advice category. At least 8 suggestions and no rewriting of the original file remain enforced.
- R7-2 PDF 工作职位几何关系经过红→绿实验：同行三段文本能提出候选，但独立外部样本中的唯一候选与 GT 不一致，故彻底禁止自动写入角色或参与评分。只返回 `review_hints` 并让用户在第二步明确采纳/忽略；未经采纳的提示不得出现在角色或年限中。测试见 `tests/test_work_relation_geometry.py` 和 `frontend/e2e/candidate.spec.js`，外部反例审计见 `scripts/profile_work_relation_gates.py`。外部 20 份 PDF 的固定结构化基准保持 167/276（60.51%），没有虚报提升。
- No external DeepSeek expense was incurred for this development slice; do not push GitHub until explicitly requested.

Do not push GitHub until explicitly requested. Use branch feat/r7-r10-candidate-diagnostics.
