# GitHub preparation evidence

Prepared on 15 November 2026 for the user-supplied GitHub remote, branch `main`. The exact remote remains in local Git configuration.

The workspace had no local Git repository. The supplied remote was reachable and had no advertised branches, tags or other refs before initialization, so there was no existing reachable commit history to rewrite. A new local `main` branch was initialized without replacing project files. The configured Git author identity is preserved.

The credential audit checks all candidate files, the actual staged blob contents, reachable Git history blobs and commit/tag messages. It compares configured local credential values in memory and checks high-confidence credential patterns. Findings print paths/categories only, never matched values. Empty configuration examples and deliberately invalid unit-test placeholders were reviewed as false positives; regression tests cover empty values, staged/worktree differences, historical credentials and redaction. No actual credential finding was identified in the completed pre-staging scan. The workflow repeats the audit against the staged snapshot and new commit before pushing. Automated pattern checks cannot guarantee detection of every unknown secret format.

Ignore checks confirmed that local `.env` variants, credential files, logs, dependency/virtual-environment folders, cached satellite data, deployment test copies, generated PDFs and temporary files are excluded. The four explicitly simulated source images remain included, totaling 2,063,207 bytes. The existing validated NISAR COG remains local and unchanged; it is not uploaded.

Validation completed: **192 backend tests passed, 1 optional integration test skipped; 26 frontend tests passed; production build passed**. The build used `https://forestpulse-api.example` solely as a compile-time validation origin; it is not a deployed backend. `dist/` is ignored. Set `VITE_API_BASE_URL` to the actual Render HTTPS origin in Vercel before deployment. Warnings were the existing Vite bundle-size advisory and upstream Starlette/httpx TestClient deprecation.

`HARMONY_PROCESSING_ENABLED` remains false. No NASA processing job was submitted. This GitHub publication does not establish that Vercel or Render has been publicly deployed. See [the manual deployment guide](deployment.md).
