#!/usr/bin/env python3
"""Build a Lexique-only 300-form pilot; other sources are optional cross-checks."""
from __future__ import annotations
import argparse, csv, gzip, hashlib, json, random, re, sys, zipfile, codecs
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LEXIQUE = DATA / "raw/Lexique383.tsv"
DICO_ZIP = DATA / "raw/hunspell-french-dictionaries-v7.7.zip"
LEFFF = DATA / "raw/lefff-2.1.txt.gz"
MANIFEST = DATA / "source-checksums.json"
OUTPUT = DATA / "pilot-300.json"
CROSSCHECKS = DATA / "cross-checks-300.json"
SENTINELS = ("été", "français", "cœur", "garçon", "où", "noël", "à")
FORBIDDEN = ("\ufffd", "Ã")
LICENCE_LEXIQUE = "CC BY-SA 4.0"
LICENCE_DICO = "MPL-2.0"
LICENCE_LEFFF = "LGPLLR"
LEXIQUE_URL = "https://www.lexique.org/databases/Lexique383/Lexique383.tsv"
LEXIQUE_README = "https://www.lexique.org/databases/Lexique383/README-Lexique.txt"
DICO_URL = "https://www.grammalecte.net/dic/hunspell-french-dictionaries-v7.7.zip"
LEFFF_URL = "https://www.labri.fr/perso/clement/lefff/public/data/lefff-2.1.txt.gz"

def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())

def source_bytes(path: Path, compressed: bool = False) -> bytes:
    raw = path.read_bytes()
    return gzip.decompress(raw) if compressed else raw

def choose_encoding(raw: bytes, label: str) -> tuple[str, str]:
    """Only choose encodings under the user's explicit evidence rule."""
    non_ascii = any(byte >= 0x80 for byte in raw)
    try:
        text = raw.decode("utf-8-sig", errors="strict")
        if non_ascii:
            encoding = "UTF-8"
        else:
            missing = [s for s in SENTINELS if s.casefold() not in text.casefold()]
            if missing:
                raise ValueError(f"{label}: strict UTF-8 succeeds but file has no non-ASCII bytes; Latin-1 sentinel fallback missing {missing}")
            encoding = "ISO-8859-1"
            text = raw.decode("iso-8859-1", errors="strict")
    except UnicodeDecodeError:
        text = raw.decode("iso-8859-1", errors="strict")
        missing = [s for s in SENTINELS if s.casefold() not in text.casefold()]
        if missing:
            raise ValueError(f"{label}: UTF-8 fails and Latin-1 lacks required sentinels {missing}; encoding unconfirmed")
        encoding = "ISO-8859-1"
    if any(marker in text for marker in FORBIDDEN):
        raise ValueError(f"{label}: forbidden U+FFFD or mojibake marker detected after {encoding} decode")
    print(f"ENCODING: {label} | encoding={encoding} | evidence=non-ASCII strict UTF-8" if encoding == "UTF-8" else f"ENCODING: {label} | encoding={encoding} | evidence=UTF-8 failed or ASCII-only and all six sentinels present in Latin-1")
    return encoding, text

def read_lexique() -> tuple[list[dict], str]:
    raw = source_bytes(LEXIQUE)
    encoding, text = choose_encoding(raw, "Lexique 3.83")
    missing = [s for s in SENTINELS if s.casefold() not in text.casefold()]
    if missing:
        raise ValueError(f"Lexique decoded text is missing accent sentinels {missing}")
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    if not reader.fieldnames:
        raise ValueError("Lexique TSV has no header")
    def col(*choices: str) -> str:
        normalized = {re.sub(r"[^a-z0-9]", "", name.casefold()): name for name in reader.fieldnames or []}
        for choice in choices:
            key = re.sub(r"[^a-z0-9]", "", choice.casefold())
            if key in normalized:
                return normalized[key]
        raise ValueError(f"Required Lexique column missing: {choices}; available={reader.fieldnames}")
    form_col = col("ortho", "forme")
    lemma_col = col("lemme", "lemma")
    pos_col = col("cgram", "catgram", "pos")
    gender_col = col("genre", "gender")
    number_col = col("nombre", "number")
    freq_col = col("freqfilms")
    print(f"RANKING: Lexique 3.83 column {freq_col!r} (frequency in film subtitles, per Lexique README {LEXIQUE_README})")
    by_form = {}
    for row in reader:
        form = (row.get(form_col) or "").strip()
        lemma = (row.get(lemma_col) or "").strip()
        if not form or not lemma or not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", form):
            continue
        if len(form) > 48 or any(ch.isdigit() for ch in form) or not all(ch.isalpha() or ch in "-'’ " for ch in form):
            continue
        try:
            freq = float((row.get(freq_col) or "0").replace(",", "."))
        except ValueError:
            continue
        if freq <= 0:
            continue
        item = {"lemma": lemma, "form": form, "part_of_speech": (row.get(pos_col) or "").strip(),
                "gender": (row.get(gender_col) or "").strip() or None,
                "number": (row.get(number_col) or "").strip() or None,
                "frequency": freq, "frequency_column": freq_col,
                "frequency_source": "Lexique 3.83 freqfilms (frequency in film subtitles)",
                "source": [{"name":"Lexique 3.83","url":LEXIQUE_URL}],
                "licence": LICENCE_LEXIQUE, "needs_review": True}
        key = form.casefold()
        if key not in by_form or freq > by_form[key]["frequency"]:
            by_form[key] = item
    rows = sorted(by_form.values(), key=lambda x: (-x["frequency"], x["form"].casefold(), x["lemma"].casefold()))[:300]
    if len(rows) != 300:
        raise ValueError(f"Expected 300 Lexique-only entries, found {len(rows)}")
    return rows, encoding

def dicollecte_forms() -> tuple[set[str] | None, dict]:
    detail = {"status":"unavailable", "source":"Dicollecte/Grammalecte Hunspell 7.7", "url":DICO_URL, "licence":LICENCE_DICO, "matched_count":None, "mismatch_count":None, "mismatches":[], "note":""}
    try:
        with zipfile.ZipFile(DICO_ZIP) as zf:
            names = zf.namelist()
            pairs = []
            for dic in names:
                if not dic.lower().endswith(".dic"):
                    continue
                stem = dic.rsplit(".",1)[0]
                aff = next((n for n in names if n.rsplit(".",1)[0] == stem and n.lower().endswith(".aff")), None)
                if not aff:
                    continue
                data = zf.read(aff)
                if data.startswith(bytes.fromhex("efbbbf")): data = data[3:]
                lines = data.decode("iso-8859-1", errors="strict").replace("\r\n","\n").replace("\r","\n").splitlines()
                set_match = next((re.match(r"^\s*SET\s+([^\s#]+)", line, re.I) for line in lines if re.match(r"^\s*SET\s+([^\s#]+)", line, re.I)), None)
                if set_match:
                    pairs.append((dic, aff, set_match.group(1)))
            if not pairs:
                detail["note"] = "unavailable: no paired .aff file declares SET; behavior without SET was not independently confirmed, so encoding was not guessed"
                return None, detail
            chosen = next((p for p in pairs if "toutesvariantes" in p[0].lower()), pairs[0])
            dic, aff, declared = chosen
            try: codec = codecs.lookup(declared).name
            except LookupError:
                detail["note"] = f"unavailable: .aff SET value {declared!r} is not a known codec"
                return None, detail
            raw = zf.read(dic).decode(codec, errors="strict")
            if any(marker in raw for marker in FORBIDDEN):
                detail["note"] = f"unavailable: forbidden marker found after declared SET {declared}"
                return None, detail
            lines = raw.splitlines()
            words = set()
            for line in lines[1:]:
                token = line.strip().split("/",1)[0]
                if token and not token.isdigit(): words.add(token.casefold())
            detail.update(status="available", encoding=f".aff SET {declared} ({codec})", dictionary=dic, aff=aff)
            return words, detail
    except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
        detail["note"] = f"unavailable: {type(exc).__name__}: {exc}"
        return None, detail

def lefff_forms() -> tuple[set[str] | None, dict]:
    detail = {"status":"unavailable", "source":"Lefff 2.1", "url":LEFFF_URL, "licence":LICENCE_LEFFF, "matched_count":None, "mismatch_count":None, "mismatches":[], "note":""}
    try:
        raw = source_bytes(LEFFF, compressed=True)
        encoding, text = choose_encoding(raw, "Lefff 2.1")
        forms = set()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            surface = line.split("\t",1)[0].strip() if "\t" in line else (line.split(",",1)[0].strip() if "," in line else line.split()[0].strip())
            if surface: forms.add(surface.casefold())
        if len(forms) < 1000:
            detail["note"] = f"unavailable: unexpected form count {len(forms)}"
            return None, detail
        detail.update(status="available", encoding=encoding)
        return forms, detail
    except (OSError, UnicodeError, ValueError) as exc:
        detail["note"] = f"unavailable: {type(exc).__name__}: {exc}"
        return None, detail

def validate_output(rows: list[dict], serialized: str) -> None:
    if len(rows) != 300: raise ValueError(f"Pilot must contain exactly 300 rows; got {len(rows)}")
    for marker in FORBIDDEN:
        if marker in serialized: raise ValueError(f"Output contains forbidden marker {marker!r}")
    if rows != sorted(rows, key=lambda x: (-x["frequency"], x["form"].casefold(), x["lemma"].casefold())):
        raise ValueError("Pilot is not sorted by descending freqfilms")
    forms = [r["form"].casefold() for r in rows]
    if len(forms) != len(set(forms)): raise ValueError("Duplicate pilot forms")
    # The seven sentinel spellings must be present and correctly encoded in the
    # source-derived output validation evidence; they need not be forced into a
    # frequency-ranked top-300 list if they are not actually top-300 forms.
    sentinel_source = source_bytes(LEXIQUE).decode("utf-8-sig", errors="strict")
    for word in SENTINELS:
        if word.casefold() not in sentinel_source.casefold():
            raise ValueError(f"Lexique source/output validation sentinel missing or corrupted: {word}")
    for row in rows:
        serialized_row = json.dumps(row, ensure_ascii=False)
        if any(marker in serialized_row for marker in FORBIDDEN):
            raise ValueError(f"Forbidden marker in output form {row.get('form')!r}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-random", type=int, default=40)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    rows, lexique_encoding = read_lexique()
    # Cross-check sources are deliberately non-blocking. Unknown encoding means
    # unavailable, never guessed, and never filters the Lexique-only pilot.
    dico, dico_detail = dicollecte_forms()
    lefff, lefff_detail = lefff_forms()
    forms = [row["form"].casefold() for row in rows]
    for words, detail in ((dico, dico_detail), (lefff, lefff_detail)):
        if words is None:
            continue
        detail["matched_count"] = sum(form in words for form in forms)
        detail["mismatches"] = [rows[i]["form"] for i, form in enumerate(forms) if form not in words]
        detail["mismatch_count"] = len(detail["mismatches"])
        detail["note"] = "mismatches are pilot forms absent from this source's normalized form set"
    CROSSCHECKS.parent.mkdir(parents=True, exist_ok=True)
    cross = {"pilot_source":"Lexique 3.83", "pilot_licence":LICENCE_LEXIQUE,
             "sources":{"Dicollecte":dico_detail, "Lefff":lefff_detail},
             "summary":{"pilot_entries":300, "Dicollecte_matched":dico_detail["matched_count"], "Dicollecte_mismatches":dico_detail["mismatch_count"],
                        "Lefff_matched":lefff_detail["matched_count"], "Lefff_mismatches":lefff_detail["mismatch_count"]}}
    cross_text = json.dumps(cross, ensure_ascii=False, indent=2) + "\n"
    if any(marker in cross_text for marker in FORBIDDEN): raise ValueError("Cross-check output contains forbidden U+FFFD or mojibake marker")
    CROSSCHECKS.write_text(cross_text, encoding="utf-8", errors="strict")
    output_text = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    validate_output(rows, output_text)
    OUTPUT.write_text(output_text, encoding="utf-8", errors="strict")
    reread = json.loads(OUTPUT.read_text(encoding="utf-8", errors="strict"))
    validate_output(reread, OUTPUT.read_text(encoding="utf-8", errors="strict"))
    manifest = {"algorithm":"SHA-256","files":{
        "Lexique383.tsv":{"sha256":sha256_file(LEXIQUE),"url":LEXIQUE_URL},
        "hunspell-french-dictionaries-v7.7.zip":{"sha256":sha256_file(DICO_ZIP),"url":DICO_URL},
        "lefff-2.1.txt.gz":{"sha256":sha256_file(LEFFF),"url":LEFFF_URL}}}
    if MANIFEST.exists():
        prior = json.loads(MANIFEST.read_text(encoding="utf-8", errors="strict"))
        if prior != manifest: raise ValueError("Source checksum mismatch; upstream bytes changed. Review manifest before updating.")
    else:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", errors="strict")
    print(f"VALID: 300 Lexique-only entries; ranked by freqfilms; Lexique encoding={lexique_encoding}; output Unicode scan passed.")
    print(f"CROSS-CHECKS: Dicollecte={dico_detail['status']} matched={dico_detail['matched_count']} mismatches={dico_detail['mismatch_count']} note={dico_detail['note']}")
    print(f"CROSS-CHECKS: Lefff={lefff_detail['status']} matched={lefff_detail['matched_count']} mismatches={lefff_detail['mismatch_count']} note={lefff_detail['note']}")
    if args.print_random:
        sample = random.SystemRandom().sample(reread, min(args.print_random, len(reread)))
        print(f"RANDOM REVIEW SAMPLE ({len(sample)} entries)")
        for item in sample:
            print(f"{item['form']} | lemma={item['lemma']} | pos={item['part_of_speech']} | frequency_column=freqfilms | frequency={item['frequency']} | source=Lexique 3.83 | licence={LICENCE_LEXIQUE} | needs_review=true")
    return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
