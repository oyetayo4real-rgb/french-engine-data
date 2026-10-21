# French Engine Data

Source-controlled pilot for auditable French lexical data imports. This repository is intentionally separate from French Academy.

## Pilot policy

- Source data is downloaded only from the official Dicollecte/Grammalecte, Lefff, and Lexique distribution endpoints.
- Lexique provides the frequency ranking and lexical metadata; Dicollecte is used as a spelling-resource cross-check; Lefff is used as a lexical-form cross-check.
- The pilot output is the 300 highest-frequency unique forms from Lexique 3.83, ranked by `freqfilms2` (form frequency in film subtitles); every row is marked `needs_review: true` and retains Lexique CC BY-SA 4.0 attribution.\n- Dicollecte and Lefff are optional cross-checks only. Their results, source/licence tags, match counts, and mismatch lists are written separately to `data/cross-checks-300.json`; an unconfirmed encoding marks that source unavailable instead of blocking the Lexique pilot.\n- Every workflow attempt writes and commits `diagnostics/last-run.txt`, including source byte diagnostics, Hunspell archive inventory/SET evidence, encoding decisions, and (when available) 40 random pilot entries. The diagnostics commit uses `[skip ci]`.
- The workflow writes SHA-256 digests for the exact source downloads. The first run establishes a baseline; later runs fail if upstream bytes differ until the checksum manifest is deliberately reviewed and updated.
- Nothing in this repository is automatically imported into French Academy.

Run the workflow manually from **Actions → Import and validate 300-entry pilot → Run workflow**. The workflow also runs when importer/licence/workflow documentation changes on `main`, then commits only the generated pilot and source checksum manifest.
