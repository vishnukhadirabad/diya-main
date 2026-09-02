# Plan — Write docs/responsibilities.md for Diya-main (current state + target direction)

## Context
Started as "summarize what Diya-main is responsible for" from `docs/Diya-Codebase-Overview.pdf`. That surfaced two problems worth fixing together:

1. **`PROJECT.md` is stale.** It describes an earlier architecture (in-app `QuestPDF` report generation, `CalibrationView`/`MeditationView`/`ReportView` screens, `ISensorSource`/`ICameraSource`/`IMotorController` hardware interfaces, partner called "IITH team"). None of that exists in the current code — verified against `Views/`, `Services/`, and `DiyaMeditation.csproj`. The current code matches the PDF: single `HomeView`, `scripts/run1.sh` orchestrates camera/CV steps then launches an external `meditation-app` (.deb, separate "hardware team" repo) which writes the report PDF; the kiosk only renders it (`PDFtoImage`).
2. **The PDF itself is now also out of date relative to where the project is actually headed.** The user clarified the target design, informed by two sibling repos on disk (`am-mock-client`, `am-mock-server`) that prototype a face-recognition identify flow:
   - **`am-mock-server`** — FastAPI mock of `am-master-server`: register a face photo → embedding stored; `/api/v1/identify/` matches a submitted face vector against stored embeddings.
   - **`am-mock-client`** — the edge/kiosk-side client (`Am-FaceRecognition-Client`): captures a camera frame, detects + embeds the face (YuNet + sface/auraface), calls the server's identify endpoint.

**Confirmed decisions from the user for the target architecture:**
- Face recognition **replaces** the current QR-on-kiosk / phone-scan / admin-roster-link identification flow **entirely** — no phone step. Visitor stands at the kiosk, camera captures + identifies them directly.
- The **one backend** for Diya-main going forward should follow the **FastAPI pattern** (`am-mock-server`-style), not stay as the current Node/Express `server/`.
- **Face registration/enrollment is explicitly out of scope for Diya-main** — another team owns it (the `am-mock-server` registration flow is their reference/mechanism). Diya-main's backend only needs to *consume* an identify capability, not build registration.
- **Report delivery by email/SMS is a real, confirmed requirement but deferred** — noted as a known future phase, not designed in detail now.

**Target end-to-end flow (marked as target/planned, not yet built):**
```
Kiosk camera captures face → identify call (FastAPI backend, face-recognition identify)
  → match found → visitor identified (no phone/QR step)
  → calibration runs (scripts/run1.sh: HOME1 → SHOOT1 → CHEST1 → EYE1, existing, unchanged)
  → launches external meditation-app (hardware team, existing, unchanged)
  → meditation-app writes report PDF to /opt/meditation-app/data (unchanged)
  → kiosk renders report on-screen (existing ReportRenderer/PDFtoImage, unchanged)
  → [future phase] report emailed/texted to visitor
  → reset for next visitor
```

This plan documents **both** the current implemented state and this target direction, clearly separated, so the doc doesn't go stale the moment work starts on the face-recognition pivot. It intentionally does **not** implement the pivot itself (no code changes to swap the identify flow or the backend) — that's a separate, much larger implementation task not yet requested.

## Content written into `docs/responsibilities.md`

1. **Header** — one-line description: Diya-main covers "our side" of a kiosk with three collaborating parties (us, the hardware/CV team, and the face-recognition/registration team).
2. **Current state — what we own today** (matches PDF + verified code):
   - Kiosk desktop app (`DiyaMeditation/`) — session creation, QR display, poll/claim, auto-run pipeline, render report PDF, reset.
   - Backend + web (`server/`, `registration/`) — Node/Express/Postgres: sessions, visitor self-registration, admin roster upload, per-person login links.
   - Packaging & deployment (`deploy/`, `render.yaml`).
3. **Current state — explicitly not ours** (hardware team): CV/servo Python scripts (`HOME1/SHOOT1/CHEST1/EYE1`), the external `meditation-app` .deb. Boundary: `scripts/run1.sh` + `/opt/meditation-app/data`.
4. **Target direction (planned, not yet built)**:
   - Face recognition replaces the QR/phone-claim flow entirely — cite `am-mock-client`/`am-mock-server` as the working reference pattern for the identify call shape (`POST /api/v1/identify/`, face vector, sface 128-dim/auraface 512-dim).
   - Backend consolidates onto a FastAPI-style service (replacing `server/`'s Node/Express) — single backend for the kiosk.
   - Calibration → meditation-app → on-screen report stay as-is (unchanged pipeline, just triggered by face-identify instead of QR-claim).
   - Report delivery via email/SMS — noted as a confirmed future requirement, deferred, not designed yet.
5. **Ownership boundaries for the target direction** (three parties, stated explicitly so nobody assumes scope by default):
   - **Diya-main (us):** kiosk app, the identify-*consuming* integration, calibration trigger, meditation-app launch, report render, packaging.
   - **Hardware team:** CV/servo scripts, `meditation-app`.
   - **Face-recognition/registration team:** face enrollment/registration backend (`am-master-server` in production; `am-mock-server` is the local mock/reference) — Diya-main only calls its identify endpoint, does not build or own registration.
6. **Stale-docs callout** — flags `PROJECT.md` as describing an abandoned earlier architecture (QuestPDF/in-app hardware interfaces/"IITH team" naming); points readers to `responsibilities.md` + the PDF instead, until `PROJECT.md` is separately updated or retired.
7. **Open items** carried over from the PDF (§11) that remain relevant regardless of the pivot: window management handoff to meditation-app, no timeout on `run1.sh` retry loop, no consent/privacy screen, no inactivity auto-reset — plus the new deferred item (report email/SMS delivery).

## File edited
- `docs/responsibilities.md` — written per above, in Markdown, matching the tone/style of `PROJECT.md`/`FAQ.md` (headers, short bullets, no fluff). "Current state" and "Target direction" are clearly separated so it can't be misread as already-built.

## Out of scope for this task
- No code changes — documentation-only.
- Not rewriting `PROJECT.md` itself (flagged only, not fixed).
- Not designing the report email/SMS mechanism (explicitly deferred per user).
- Not designing the face-registration/enrollment backend (explicitly another team's).

## Status
- [x] Read and verified `docs/Diya-Codebase-Overview.pdf` against actual code (Views/, Services/, .csproj).
- [x] Identified `PROJECT.md` as stale relative to current code.
- [x] Clarified target architecture (face recognition, FastAPI backend, deferred email/SMS) with the user, referencing `am-mock-client`/`am-mock-server`.
- [x] Wrote `docs/responsibilities.md`.
- [ ] Not yet done: updating/retiring `PROJECT.md`, implementing the face-recognition pivot, designing report delivery.

## Next steps (not started)
1. Decide whether to rewrite or retire `PROJECT.md` (currently just flagged as stale).
2. Design the actual identify integration: how the kiosk swaps its QR/claim flow for a camera-capture + identify call against the face-recognition team's backend.
3. Design the FastAPI backend that replaces `server/` (Node/Express) — likely needs to keep session/pipeline-trigger responsibilities that `server/` currently owns, in addition to consuming face-identify.
4. Design report delivery (email/SMS) once contact info sourcing is settled with the face-recognition/registration team.
