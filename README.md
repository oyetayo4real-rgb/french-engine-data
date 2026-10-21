# French Engine Data

Source-controlled pilot for auditable French lexical data imports. This repository is intentionally separate from French Academy.

## Pilot policy

- Source data is downloaded only from the official Dicollecte/Grammalecte, Lefff, and Lexique distribution endpoints.
- Lexique provides the frequency ranking and lexical metadata; Dicollecte is used as a spelling-resource cross-check; Lefff is used as a lexical-form cross-check.
- The pilot output is capped at 300 high-frequency entries. Every row is marked `needs_review: true`.
- The workflow writes SHA-256 digests for the exact source downloads. The first run establishes a baseline; later runs fail if upstream bytes differ until the checksum manifest is deliberately reviewed and updated.
- Nothing in this repository is automatically imported into French Academy.

Run the workflow manually from **Actions → Import and validate 300-entry pilot → Run workflow**. The workflow also runs when importer/licence/workflow documentation changes on `main`, then commits only the generated pilot and source checksum manifest.
