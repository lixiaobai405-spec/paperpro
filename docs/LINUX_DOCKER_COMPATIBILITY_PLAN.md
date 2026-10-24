# Linux document conversion and Docker delivery implementation plan

**Goal:** Prepare PaperPro locally for a root-managed, independent Docker Compose deployment without changing the existing server or committing changes.

**Approved architecture:** Keep Windows Word conversion available. On Linux, convert legacy DOC to DOCX using LibreOffice, then reuse the existing bounded DOCX/OCR parser. Generate PDF from the same DOCX template using LibreOffice with installed Chinese fonts. Package one application image (built React assets plus FastAPI), an independent `paperpro` Compose project and deployment instructions.

**Tech stack:** Python 3.12/uv, existing FastAPI/python-docx/PyMuPDF/ReportLab, LibreOffice Writer, Chinese fonts, Node 22/Vite build stage, Docker Compose.

**Workspace constraints:** Work in the current `main` checkout as requested. Preserve the pre-existing `start-paperpro.cmd` modification and `output/` test PDF. No commit, push, server login, deployment, paid API call or real credential read. The target directory proposed for delivery is `/opt/MT-jianlizengqiangzhinengti/`.

## Task 1: Document converter and parser

Files: create `app/document_converter.py`, `tests/test_document_converter.py`; modify `app/parser.py`.

- [x] Add behavioral tests for valid conversion, missing executable, queue saturation, timeout/process cleanup, missing/invalid/oversize output, independent profiles, secret-free child environment and DOCX expansion limits.
- [x] Implement `convert_document(data: bytes, source_format: str, target_format: str) -> bytes` for DOC/DOCX input and DOCX/PDF output. Use fixed temporary filenames, `shell=False`, two conversion slots, a five-second queue limit, a 45-second process timeout and process-group termination on Linux.
- [x] Disable macros/active embedded content and automatic link/field updates in each fresh LibreOffice profile; suppress document-bearing stdout/stderr and do not pass provider credentials to the converter process.
- [x] Share DOCX archive limits between original DOCX and converted DOC. Retain the Windows Word route and return conversion/OCR warnings for Linux DOC input.

Verification:

```powershell
uv run --locked --python 3.12 python -m pytest tests/test_document_converter.py -q
```

## Task 2: PDF conversion and fonts

Files: modify `app/exporter.py`; create `tests/test_linux_documents.py`.

- [x] Add tests for Linux DOC ingestion preserving tables/images, invalid converted archives, LibreOffice PDF routing, strict-mode failures, controlled ReportLab fallback and template font selection.
- [x] Use an OS-appropriate template font, overridable by `PAPERPRO_RESUME_FONT`. Prefer LibreOffice on Linux and retain Word on Windows in automatic mode.
- [x] Add `PAPERPRO_PDF_ENGINE=auto|libreoffice|reportlab|word`; strict LibreOffice mode must propagate a conversion error. Keep explicit fallback limitations for unsupported characters and use an embedded Chinese TrueType font on Linux when available.

Verification:

```powershell
uv run --locked --python 3.12 python -m pytest tests/test_document_converter.py tests/test_linux_documents.py -q
```

## Task 3: Docker and handoff

Files: create `Dockerfile`, `compose.yaml`, `.dockerignore`, `.env.example`, `docs/DEPLOYMENT_LINUX.md`, `scripts/smoke_linux_documents.py`, `scripts/package_deployment.py`; update `README.md`.

- [x] Build React in a Node stage and a locked Python environment in a separate stage. Install LibreOffice Writer and Chinese fonts only in the runtime image; explicitly copy application/public settings/built assets, never real environment files.
- [x] Configure the independent Compose project `paperpro`, host binding `127.0.0.1:8766`, restart policy, health check, resource and log limits. Treat Docker CLI administration by root separately from an unprivileged application process inside the container.
- [x] Write instructions for existing-project/Nginx preflight, archive or Git installation, private configuration, startup, DOC/OCR/PDF verification, HTTPS/access restrictions, update backups, image rollback and cleanup. Do not overwrite existing site or server-wide Docker settings.
- [x] Create an allowlisted archive packager: reject symlinks/junctions, include only source/deployment docs/lock files/public configuration, exclude credentials before file reads, write a separate handoff ZIP and report its checksum.

## Task 4: Verification and review

- [x] Run local regression tests and frontend build. Record any unchanged Windows Word COM baseline failure separately.
- [x] Build the actual Linux image locally. Exercise real DOC/DOCX conversion, Chinese one/multiple-page PDF export, concurrent conversions and API upload/export; render and visually inspect representative pages. Use synthetic data and no external AI calls.
- [x] Validate Compose configuration without printing real environment values. Run the packaged image with placeholder credentials on a separate local test port and confirm health/static frontend/API behavior.
- [x] Request an independent code review using the `requesting-code-review` skill; resolve important findings and rerun affected checks.
- [x] Update this checklist and deployment evidence, inspect the final diff, produce the clean handoff archive, and report limitations. Leave everything uncommitted for the user.

## Local verification, 2026-10-24

- Linux image: Docker Desktop Linux engine 29.8.0, Compose 5.5.1, `linux/amd64`, Python 3.12, LibreOffice 25.2.3.2. The uncompressed image is about 2.0 GB. Build from the allowlisted source ZIP is also checked; this is a source delivery, not an offline image bundle.
- Container: independent project `paperpro-local-validation`, host `127.0.0.1:18766`, placeholder `.env.example`, no provider keys; production read-only root, 256 MiB tmpfs, uid 65534, 2 GiB memory, 1.5 CPU and 256 pids restrictions are active. Health and both frontend routes pass.
- Actual Linux acceptance: **11 checks passed**, including real binary DOC conversion, preserved tables and embedded-image OCR, one-page and two-page Chinese PDFs, supplementary CJK, three concurrent conversions, real timeout child-process cleanup, installed policy/profile readback, a local HTTP probe confirming an external DOCX image was not fetched, and upload/export APIs. AI calls: **0**.
- Visual inspection: single-page resume, both pages of the 64-item resume and the supplementary-CJK name are readable, with no observed missing glyph, overlap or clipping. This is sample-based validation, not Word pixel equivalence or general font coverage.
- Browser: **33 existing Chromium tests passed** against the Linux container, including real PNG OCR, edited-name DOCX/PDF downloads, diagnosis, human-review gates and mobile overflow checks. Browser plugin not available; used the repository Playwright workflow. Desktop 1280x720 and mobile 390x844 screenshots were inspected; simulated phone-picker tests are not real-device verification.
- Offline Windows regression: **286 passed, 3 deselected**, 90% application coverage. The mode explicitly uses ReportLab to avoid unstable host Word automation. Excluded: `test_legacy_doc_end_to_end`, `test_pdf_word_engine_preserves_extended_han_character`, and the external real-dataset CLI benchmark (GitHub rate limiting). These three are not claimed as passing. After making the OCR configuration test portable to a one-core host, its final focused test module passed **6 tests**.
- Frontend production build, Compose config validation, Python compilation and `git diff --check` pass. The existing Vite chunk-size advisory and Starlette TestClient deprecation warning remain.
- Independent review found and confirmed fixes for the LibreOffice profile path, shared PyMuPDF serialization and Windows junction exclusion. A follow-up review confirmed actual ONNX intra/inter thread settings and found no remaining production blocker in the OCR correction.
- Real acceptance initially exposed PID exhaustion: automatic OCR thread sizing hit `pids.events max=11`, failed concurrent conversion and timed out one browser scan upload. The image now caps OCR/OpenCV/numerical-library threads and serializes OCR initialization/inference. The repeated complete Linux/browser runs pass, and the container counter remains **max=0**. Resource limits were not removed to make the tests pass.
- Logs and rendered synthetic fixtures are local ignored artifacts under `artifacts/visual/`; browser captures use the repository's existing ignored `frontend/test-results/`. The handoff excludes these artifacts, credentials, private evaluation data, local dependencies and user resume PDFs, and includes a SHA-256 file manifest.
- Existing user changes in `start-paperpro.cmd` and `output/pdf/paperpro-test-resume.pdf` were preserved. No server deployment, Git commit/push or paid AI API call was performed.

## Baseline evidence

- Before edits, targeted Windows tests reached a failure in `tests/test_integration.py::test_legacy_doc_end_to_end`: Word COM/RPC errors during the fixture's own DOC generation/cleanup. This is an existing host integration failure and is not evidence about Linux conversion.
- Docker CLI/Desktop is installed locally; its Linux engine was initially stopped. Docker Desktop was started solely for local verification.

## Acceptance boundary

LibreOffice output is not promised to be pixel-identical to Microsoft Word. Acceptance requires readable Chinese, retained facts, supported characters, proper A4 pagination, clear failure paths and a reproducible local Linux image. No server deployment is part of this change.
