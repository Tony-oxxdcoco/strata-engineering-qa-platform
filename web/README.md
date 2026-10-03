# Engineering QA workspace

The UI uses native ES modules and CSS and is served by FastAPI from the same origin as `/api/v1`. It requires the backend; opening `index.html` as a local file or uploading it alone to static hosting is unsupported.

Routes are visual tabs, not separate server pages: Workspace, Knowledge, Review, Versions and Audit trail. Source uploads use authenticated requests; source and report downloads are fetched with the session token and opened as local Blob URLs. User/source strings are escaped before HTML rendering. Selection changes clear the displayed run, while the original remains in server history.

First-time setup → create project → Load example → select input/task → Run review → inspect findings, citations and tool trace → reviewer confirmation → HTML print-to-PDF or JSON export. Upload real supporting documents without the auto-snapshot checkbox, create a draft rule from an exact excerpt, and approve it with the reviewer role. Spreadsheet/PDF extraction that needs a mapping stays explicit; it is not inferred into engineering data by the UI.

Native JavaScript is retained for this bounded workspace to avoid maintaining a second build/runtime during the storage migration. React/TypeScript remains a future maintainability choice if team UI complexity warrants it; it is not a claimed implemented dependency. See the architecture decision record in `docs/plans/README.md`.
