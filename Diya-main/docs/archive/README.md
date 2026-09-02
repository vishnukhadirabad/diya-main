# Archive

Retired material, kept for reference rather than deleted. See
`docs/responsibilities.md` for current scope and architecture.

- **`PROJECT.md`, `FAQ.md`** — describe an earlier, abandoned architecture
  (in-app QuestPDF report generation, `CalibrationView`/`MeditationView`/
  `ReportView` screens, `ISensorSource`/`ICameraSource`/`IMotorController`
  hardware interfaces, partner referred to as "IITH team"). None of that
  exists in the current code.
- **`server/`, `registration/`, `render.yaml`** — the Node/Express/Postgres
  backend and static web pages (session QR, visitor self-registration, admin
  roster upload, per-person login links) that powered the QR/phone-claim
  identification flow. Superseded by face recognition: the kiosk now
  identifies visitors directly via camera, calling the face-recognition
  team's identify backend (see `Services/IdentifyRunner.cs` +
  `scripts/identify/identify.py`). There is no Diya-owned backend in the
  current architecture. `server/node_modules` was not archived — reinstall
  with `npm install` if this code is ever revived.
