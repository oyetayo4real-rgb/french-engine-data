# French Engine Data

Source-controlled pilot for auditable French lexical data imports. This repository is intentionally separate from French Academy.

## Pilot policy

- Source data is downloaded only from the official Dicollecte/Grammalecte, Lefff, and Lexique distribution endpoints.
- Lexique provides the frequency ranking and lexical metadata; Dicollecte is used as a spelling-resource cross-check; Lefff is used as a lexical-form cross-check.
- The pilot output is 300 distinct lemmas from Lexique 3.83, ranked by `freqlemfilms2` (lemma frequency in film subtitles). Each lemma includes its part of speech, gender, and three most frequent forms ranked by `freqfilms2`. Tie-break: descending top-form frequency, then case-folded lemma ascending, then original lemma ascending. Every row is marked `needs_review: true` and retains Lexique CC BY-SA 4.0 attribution.\n- Dicollecte and Lefff are optional cross-checks only. Their results, source/licence tags, match counts, and mismatch lists are written separately to `data/cross-checks-300.json`; an unconfirmed encoding marks that source unavailable instead of blocking the Lexique pilot.\n- Every workflow attempt writes and commits `diagnostics/last-run.txt`, including source byte diagnostics, Hunspell archive inventory/SET evidence, encoding decisions, and (when available) 40 random pilot entries. The diagnostics commit uses `[skip ci]`.
- The workflow writes SHA-256 digests for the exact source downloads. The first run establishes a baseline; later runs fail if upstream bytes differ until the checksum manifest is deliberately reviewed and updated.
- Nothing in this repository is automatically imported into French Academy.

Run the workflow manually from **Actions → Import and validate 300-entry pilot → Run workflow**. The workflow also runs when importer/licence/workflow documentation changes on `main`, then commits only the generated pilot and source checksum manifest.


## Data provenance, licence, and permitted scope

`data/pilot-300.json` and the teacher review sheet are derived from Lexique 3.83 by Boris New and Christophe Pallier ([lexique.org](https://www.lexique.org/)). They retain the source data's CC BY-SA 4.0 licence and must be distributed with attribution and under the same licence. See [LICENSE-DATA.md](LICENSE-DATA.md) and [CREDITS.md](CREDITS.md).

These two files are restricted to Lexique-derived lexical data and the documented transformations of that data. **Do not mix in other content**—including definitions or meanings, example sentences, audio, or grammar rules—into `data/pilot-300.json` or the review sheet. Keep such content in separate, appropriately sourced and licensed files.

### Modified from Lexique

The Lexique-derived data was modified by selecting 300 lemmas, grouping compatible lexical rows/forms, and applying spelling and typography fixes. These changes do not replace the source attribution or CC BY-SA 4.0 obligations.
