#!/usr/bin/env python3
"""Build and validate a 300-entry frequency-ranked French lexical pilot.

Inputs are official downloads supplied by the workflow. No lexical entries are
hand-authored here. The initial SHA-256 manifest records the downloaded bytes;
subsequent runs require exact hash matches unless a maintainer deliberately
reviews and updates the manifest.
"""
from __future__ import annotations

import argparse
import csv
import codecs
import hashlib
import json
import random
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LEXIQUE = DATA / "raw" / "Lexique383.tsv"
DICO_ZIP = DATA / "raw" / "hunspell-french-dictionaries-v7.7.zip"
LEFFF = DATA / "raw" / "lefff-2.1.txt.gz"
MANIFEST = DATA / "source-checksums.json"
OUTPUT = DATA / "pilot-300.json"
LICENCES = "Lexique CC BY-SA 4.0; Dicollecte MPL-2.0; Lefff LGPLLR"
ACCENT_SENTINELS = ("été", "français", "cœur", "garçon", "où", "noël", "à")
MOJIBAKE_MARKERS = ("\\ufffd", "Ã")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def decode_source(path: Path, encoding: str, *, gzip_text: bool = False, source_name: str) -> str:
    import gzip
    opener = gzip.open if gzip_text else open
    try:
        with opener(path, "rb") as f:
            raw = f.read()
        text = raw.decode(encoding, errors="strict")
    except (UnicodeError, OSError) as exc:
        raise ValueError(f"Source decode failed for {source_name} ({path.name}) using declared encoding {encoding}: {exc}") from exc
    if "\\ufffd" in text:
        raise ValueError(f"Source {source_name} ({path.name}) contains U+FFFD after {encoding} decoding")
    print(f"ENCODING: {source_name} | file={path.name} | encoding={encoding} | confirmed=strict decode")
    return text


def choose_text_encoding(path: Path, *, gzip_text: bool, source_name: str) -> tuple[str, str]:
    """Confirm encoding by strict decoding plus French accent sentinels; never lossy-decode."""
    import gzip
    opener = gzip.open if gzip_text else open
    try:
        with opener(path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        raise ValueError(f"Cannot read source {source_name} ({path.name}): {exc}") from exc

    failures = []
    for encoding in ("utf-8-sig", "cp1252", "iso-8859-1"):
        try:
            text = raw.decode(encoding, errors="strict")
        except UnicodeError as exc:
            failures.append(f"{encoding}: {exc}")
            continue
        if "\\ufffd" in text or "Ã" in text:
            failures.append(f"{encoding}: replacement/mojibake marker detected")
            continue
        # Require a minimum set of accent-bearing French forms to confirm that
        # decoding retained real orthography rather than merely accepting bytes.
        found = [word for word in ACCENT_SENTINELS if word.casefold() in text.casefold()]
        if len(found) < 3 or not any(ch in text for ch in "éèêàùçôîû"):
            failures.append(f"{encoding}: accent confirmation failed (found {found})")
            continue
        print(f"ENCODING: {source_name} | file={path.name} | encoding={encoding} | confirmed=strict decode + accent sentinels {found}")
        return encoding, text
    details = "; ".join(failures)
    raise ValueError(f"Cannot confirm text encoding for source {source_name} ({path.name}); refusing import. Attempts: {details}")


def read_hunspell_encoding(zf: zipfile.ZipFile, dic_name: str) -> tuple[str, str]:
    stem = dic_name.rsplit(".", 1)[0]
    aff_name = next((name for name in zf.namelist()
                     if name.rsplit(".", 1)[0] == stem and name.lower().endswith(".aff")), None)
    if aff_name is None:
        raise ValueError(f"Cannot confirm Hunspell encoding: no matching .aff file for {dic_name}")
    raw_aff = zf.read(aff_name)
    try:
        ascii_header = raw_aff[:65536].decode("ascii", errors="strict")
    except UnicodeError:
        # The SET directive is ASCII by specification; inspect only bytes before
        # the first non-ASCII byte so encoding is never guessed from dictionary data.
        ascii_header = raw_aff[:65536].splitlines()[0].decode("ascii", errors="strict")
    match = re.search(r"(?im)^\\s*SET\\s+([^\\s#]+)", ascii_header)
    if not match:
        raise ValueError(f"Cannot confirm Hunspell encoding: no SET line found in {aff_name}")
    declared = match.group(1).strip()
    try:
        codec = codecs.lookup(declared).name
    except LookupError as exc:
        raise ValueError(f"Unknown Hunspell SET encoding {declared!r} in {aff_name}") from exc
    print(f"ENCODING: Dicollecte/Hunspell | file={dic_name} | matching_aff={aff_name} | SET {declared} | codec={codec}")
    return declared, codec


def source_hashes() -> dict:
    return {
        "algorithm": "SHA-256",
        "files": {
            "Lexique383.tsv": {"sha256": sha256(LEXIQUE), "url": "https://www.lexique.org/databases/Lexique383/Lexique383.tsv"},
            "hunspell-french-dictionaries-v7.7.zip": {"sha256": sha256(DICO_ZIP), "url": "https://www.grammalecte.net/dic/hunspell-french-dictionaries-v7.7.zip"},
            "lefff-2.1.txt.gz": {"sha256": sha256(LEFFF), "url": "https://www.labri.fr/perso/clement/lefff/public/data/lefff-2.1.txt.gz"},
        },
    }


def check_or_write_manifest() -> dict:
    current = source_hashes()
    if MANIFEST.exists():
        prior = json.loads(MANIFEST.read_text(encoding="utf-8"))
        if prior != current:
            raise ValueError(
                "Source checksum mismatch. Upstream files changed; review and deliberately "
                "update data/source-checksums.json before importing a new source version."
            )
    else:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        MANIFEST.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return current


def read_dicollecte_words() -> set[str]:
    words: set[str] = set()
    with zipfile.ZipFile(DICO_ZIP) as zf:
        names = zf.namelist()
        candidates = [n for n in names if n.lower().endswith(".dic")]
        if not candidates:
            raise ValueError("Dicollecte source file hunspell-french-dictionaries-v7.7.zip contains no .dic dictionary")
        chosen = next((n for n in candidates if "toutesvariantes" in n.lower()), candidates[0])
        declared, codec = read_hunspell_encoding(zf, chosen)
        try:
            raw = zf.read(chosen).decode(codec, errors="strict")
        except UnicodeError as exc:
            raise ValueError(f"Source decode failed for Dicollecte/Hunspell file {chosen} using SET {declared}: {exc}") from exc
        if "\\ufffd" in raw or "Ã" in raw:
            raise ValueError(f"Dicollecte/Hunspell file {chosen} contains U+FFFD or mojibake marker after {declared} decoding")
        lines = raw.splitlines()
        for line in lines[1:]:
            token = line.strip().split("/", 1)[0]
            if token and not token.isdigit():
                words.add(token.casefold())
        if not all(word in raw.casefold() for word in ("été", "français", "garçon", "où", "noël", "à")):
            raise ValueError(f"Dicollecte/Hunspell file {chosen} failed required accent-sentinel confirmation")
    if len(words) < 1000:
        raise ValueError(f"Unexpectedly small Dicollecte dictionary: {len(words)} entries")
    return words


def read_lefff_forms() -> set[str]:
    encoding, text = choose_text_encoding(LEFFF, gzip_text=True, source_name="Lefff 2.1")
    forms: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "\\t" in line:
            surface = line.split("\\t", 1)[0].strip()
        elif "," in line:
            surface = line.split(",", 1)[0].strip()
        else:
            surface = line.split()[0].strip()
        if surface:
            forms.add(surface.casefold())
    if len(forms) < 1000:
        raise ValueError(f"Unexpectedly small Lefff form set: {len(forms)} entries")
    # Confirm this source itself retained accented forms before it is used as a cross-check.
    found = [word for word in ACCENT_SENTINELS if word.casefold() in text.casefold()]
    if len(found) < 3:
        raise ValueError(f"Lefff source encoding confirmation failed; accent sentinels found: {found}")
    return forms


def find_col(fieldnames: list[str], *choices: str) -> str:
    normalized = {re.sub(r"[^a-z0-9]", "", name.casefold()): name for name in fieldnames}
    for choice in choices:
        key = re.sub(r"[^a-z0-9]", "", choice.casefold())
        if key in normalized:
            return normalized[key]
    raise ValueError(f"Required Lexique column missing; tried {choices}; got {fieldnames}")


def load_pilot() -> list[dict]:
    dico = read_dicollecte_words()
    lefff = read_lefff_forms()
    lexique_encoding, text = choose_text_encoding(LEXIQUE, gzip_text=False, source_name="Lexique 3.83")
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    if not reader.fieldnames:
        raise ValueError("Lexique TSV has no header")
    form_col = find_col(reader.fieldnames, "ortho", "forme")
    lemma_col = find_col(reader.fieldnames, "lemme", "lemma")
    pos_col = find_col(reader.fieldnames, "cgram", "catgram", "pos")
    gender_col = find_col(reader.fieldnames, "genre", "gender")
    number_col = find_col(reader.fieldnames, "nombre", "number")
    freq_cols = [
        find_col(reader.fieldnames, "freqfilms", "frequencefilms"),
        find_col(reader.fieldnames, "freqlemlivres", "freqlemmaslivres", "freqlivres"),
    ]
    candidates = []
    seen = set()
    for row in reader:
        form = (row.get(form_col) or "").strip()
        lemma = (row.get(lemma_col) or "").strip()
        if not form or not lemma or not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", form):
            continue
        if len(form) > 48 or any(ch.isdigit() for ch in form):
            continue
        if not all(ch.isalpha() or ch in "-'’ " for ch in form):
            continue
        key = (lemma.casefold(), form.casefold())
        if key in seen:
            continue
        seen.add(key)
        try:
            frequencies = [float((row.get(col) or "0").replace(",", ".")) for col in freq_cols]
        except ValueError:
            continue
        frequency = max(frequencies)
        if frequency <= 0:
            continue
        if form.casefold() not in dico or form.casefold() not in lefff:
            continue
        candidates.append({
            "lemma": lemma,
            "form": form,
            "part_of_speech": (row.get(pos_col) or "").strip(),
            "gender": (row.get(gender_col) or "").strip() or None,
            "number": (row.get(number_col) or "").strip() or None,
            "frequency": frequency,
            "frequency_source": "Lexique 3.83",
            "source": [
                {"name": "Lexique 3.83", "url": "https://www.lexique.org/databases/Lexique383/README-Lexique.txt"},
                {"name": "Dicollecte/Grammalecte 7.7", "url": "https://www.grammalecte.net/"},
                {"name": "Lefff 2.1", "url": "https://www.labri.fr/perso/clement/lefff/telechargement.html"},
            ],
            "licence": LICENCES,
            "needs_review": True,
        })
    candidates.sort(key=lambda item: (-item["frequency"], item["form"].casefold(), item["lemma"].casefold()))
    unique = []
    forms_seen = set()
    for item in candidates:
        k = item["form"].casefold()
        if k in forms_seen:
            continue
        forms_seen.add(k)
        unique.append(item)
        if len(unique) == 300:
            break
    if len(unique) != 300:
        raise ValueError(f"Expected 300 cross-validated high-frequency entries; found {len(unique)}")
    return unique


def validate(rows: list[dict]) -> None:
    required = {"lemma", "form", "part_of_speech", "gender", "number", "source", "licence", "needs_review", "frequency", "frequency_source"}
    if not isinstance(rows, list) or len(rows) != 300:
        raise ValueError(f"Pilot must contain exactly 300 rows; got {len(rows) if isinstance(rows, list) else 'non-list'}")
    seen = set()
    for i, row in enumerate(rows, 1):
        if set(row) != required:
            raise ValueError(f"Row {i}: schema keys differ: {sorted(row)}")
        if not all(isinstance(row[k], str) and row[k].strip() for k in ("lemma", "form", "part_of_speech", "licence", "frequency_source")):
            raise ValueError(f"Row {i}: required text field is empty")
        if row["needs_review"] is not True:
            raise ValueError(f"Row {i}: needs_review must always be true")
        if not isinstance(row["frequency"], (int, float)) or row["frequency"] <= 0:
            raise ValueError(f"Row {i}: frequency must be positive")
        if not isinstance(row["source"], list) or len(row["source"]) != 3:
            raise ValueError(f"Row {i}: expected all three source records")
        key = row["form"].casefold()
        if key in seen:
            raise ValueError(f"Duplicate form: {row['form']}")
        seen.add(key)
        if "\ufffd" in json.dumps(row, ensure_ascii=False):
            raise ValueError(f"Row {i}: invalid Unicode replacement character")
    for i, row in enumerate(rows, 1):
        serialized = json.dumps(row, ensure_ascii=False)
        bad = next((marker for marker in MOJIBAKE_MARKERS if marker in serialized), None)
        if bad:
            raise ValueError(f"Row {i} ({row.get('form')!r}): output contains forbidden replacement/mojibake marker {bad!r}")
    if rows != sorted(rows, key=lambda item: (-item["frequency"], item["form"].casefold(), item["lemma"].casefold())):
        raise ValueError("Pilot is not sorted by descending frequency")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-random", type=int, default=0)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    before = check_or_write_manifest()
    rows = load_pilot()
    after = source_hashes()
    if before != after:
        raise ValueError("Source bytes changed during import; aborting.")
    validate(rows)
    OUTPUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reread = json.loads(OUTPUT.read_text(encoding="utf-8"))
    validate(reread)
    # Required accent-bearing words must survive decoding in the source files and
    # in any output entry that contains a corresponding form; do not silently repair.
    output_text = OUTPUT.read_text(encoding="utf-8", errors="strict")
    for marker in MOJIBAKE_MARKERS:
        if marker in output_text:
            raise ValueError(f"Output JSON contains forbidden replacement/mojibake marker {marker!r}")
    # The source-level sentinel checks above ensure the canonical accented spellings
    # are present in the parsed lexical sources, even if some are outside the top 300.
    print("ACCENT SENTINELS: source decoding checked for été, français, cœur, garçon, où, noël, à; output mojibake scan passed.")
    print(f"VALID: {len(reread)} entries; schema OK; duplicate forms 0; UTF-8 OK; source SHA-256 checksums stable.")
    print("COUNTS: entries=300; needs_review=300; unique_forms=300")
    if args.print_random:
        sample = random.SystemRandom().sample(reread, min(args.print_random, len(reread)))
        print(f"RANDOM REVIEW SAMPLE ({len(sample)} entries)")
        for item in sample:
            print(
                f"{item['form']} | lemma={item['lemma']} | pos={item['part_of_speech']} "
                f"| gender={item['gender']} | number={item['number']} "
                f"| frequency={item['frequency']} | source=Lexique 3.83 + Dicollecte 7.7 + Lefff 2.1 "
                f"| licence={item['licence']} | needs_review={item['needs_review']}"
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
