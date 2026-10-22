#!/usr/bin/env python3
"""Build 300 distinct Lexique lemmas; Dicollecte and Lefff are optional cross-checks."""
from __future__ import annotations
import argparse, codecs, csv, gzip, hashlib, json, random, re, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LEXIQUE = DATA / "raw/Lexique383.tsv"
DICO_ZIP = DATA / "raw/hunspell-french-dictionaries-v7.7.zip"
LEFFF = DATA / "raw/lefff-2.1.txt.gz"
MANIFEST = DATA / "source-checksums.json"
OUTPUT = DATA / "pilot-300.json"
CROSSCHECKS = DATA / "cross-checks-300.json"
SENTINELS = ("été", "français", "cœur", "garçon", "où", "noël", "à", "œuf")
ACCENTED = re.compile(r"[éèêàçù]", re.IGNORECASE)
FORBIDDEN = ("\ufffd", "Ã")
LICENCE_LEXIQUE = "CC BY-SA 4.0"
LICENCE_DICO = "MPL-2.0"
LICENCE_LEFFF = "LGPLLR"
LEXIQUE_URL = "https://www.lexique.org/databases/Lexique383/Lexique383.tsv"
LEXIQUE_README = "https://www.lexique.org/databases/Lexique383/README-Lexique.txt"
DICO_URL = "https://www.grammalecte.net/dic/hunspell-french-dictionaries-v7.7.zip"
LEFFF_URL = "https://www.labri.fr/perso/clement/lefff/public/data/lefff-2.1.txt.gz"

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def source_bytes(path: Path, compressed: bool = False) -> bytes:
    raw = path.read_bytes()
    return gzip.decompress(raw) if compressed else raw

def choose_lexique_encoding(raw: bytes) -> tuple[str, str]:
    text = raw.decode("utf-8-sig", errors="strict")
    if not any(byte >= 0x80 for byte in raw):
        raise ValueError("Lexique source unexpectedly contains no non-ASCII bytes; encoding evidence is insufficient")
    if any(marker in text for marker in FORBIDDEN):
        raise ValueError("Lexique source contains forbidden U+FFFD or mojibake marker")
    print("ENCODING: Lexique 3.83 | UTF-8 | strict UTF-8 succeeds and non-ASCII bytes are present")
    return "UTF-8", text

def probe_lefff(raw: bytes) -> tuple[str | None, str, dict]:
    """Probe decompressed Lefff bytes with strict decoders and byte-level œ evidence."""
    codecs_to_test = ("utf-8", "iso-8859-1", "iso-8859-15", "cp1252")
    probe = {"source":"Lefff 2.1 decompressed payload", "tests":{}, "byte_evidence":{}}
    for codec in codecs_to_test:
        try:
            text = raw.decode(codec, errors="strict")
            probe["tests"][codec] = {
                "strict_decode_succeeds": True,
                "coeur_intact": "cœur" in text.casefold(),
                "oeuf_intact": "œuf" in text.casefold(),
                "both_words_intact": "cœur" in text.casefold() and "œuf" in text.casefold()
            }
        except UnicodeDecodeError as exc:
            probe["tests"][codec] = {"strict_decode_succeeds":False, "error":str(exc),
                                     "coeur_intact":False, "oeuf_intact":False, "both_words_intact":False}
    patterns = {
        "UTF-8 cœur": bytes.fromhex("63 c5 93 75 72"),
        "UTF-8 œuf": bytes.fromhex("c5 93 75 66"),
        "ISO-8859-15 cœur": bytes.fromhex("63 bd 75 72"),
        "ISO-8859-15 œuf": bytes.fromhex("bd 75 66"),
        "cp1252 cœur": bytes.fromhex("63 9c 75 72"),
        "cp1252 œuf": bytes.fromhex("9c 75 66")
    }
    for label, pattern in patterns.items():
        probe["byte_evidence"][label] = raw.lower().count(pattern)
    # Decisive evidence requires both spellings in the same encoding and the
    # corresponding byte representation in the decompressed payload.
    candidates = []
    if probe["tests"]["utf-8"].get("both_words_intact"):
        candidates.append("utf-8")
    if (probe["tests"]["iso-8859-15"].get("both_words_intact")
        and probe["byte_evidence"]["ISO-8859-15 cœur"] > 0
        and probe["byte_evidence"]["ISO-8859-15 œuf"] > 0):
        candidates.append("iso-8859-15")
    if (probe["tests"]["cp1252"].get("both_words_intact")
        and probe["byte_evidence"]["cp1252 cœur"] > 0
        and probe["byte_evidence"]["cp1252 œuf"] > 0):
        candidates.append("cp1252")
    # ISO-8859-1 can decode every byte but cannot represent œ; absence of œ
    # in that decoded text is expected and is not evidence against the file.
    probe["tests"]["iso-8859-1"]["note"] = "ISO-8859-1 has no œ character; a missing œ in cœur/œuf is expected."
    if len(candidates) == 1:
        chosen = candidates[0]
        text = raw.decode(chosen, errors="strict")
        if any(marker in text for marker in FORBIDDEN):
            return None, "", {**probe, "decision":"unavailable", "reason":f"candidate {chosen} decoded but output contains forbidden marker"}
        probe["decision"] = chosen
        probe["reason"] = "unique candidate preserves both cœur and œuf and matches its characteristic byte sequences"
        print(f"ENCODING: Lefff 2.1 | {chosen} | {probe['reason']}")
        return chosen, text, probe
    probe["decision"] = "unavailable"
    probe["reason"] = f"encoding not decisive; candidates={candidates!r}"
    print(f"ENCODING: Lefff 2.1 | unavailable | {probe['reason']}")
    return None, "", probe

def read_lexique() -> tuple[list[dict], str, dict]:
    raw = source_bytes(LEXIQUE)
    encoding, text = choose_lexique_encoding(raw)
    reader = csv.DictReader(text.splitlines(), delimiter="\\t")
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
    film_form_col = col("freqfilms2")
    film_lemma_col = col("freqlemfilms2")
    book_lemma_col = col("freqlemlivres")
    print(f"RANKING FORMULA: {film_lemma_col} + {book_lemma_col} (films + books lemma frequencies); forms use {film_form_col}.")
    rows = []
    sentinel_seen = {word: word.casefold() in text.casefold() for word in SENTINELS}
    print("LEXIQUE SOURCE SENTINELS: " + json.dumps(sentinel_seen, ensure_ascii=False, sort_keys=True))
    for row in reader:
        form = (row.get(form_col) or "").strip()
        lemma = (row.get(lemma_col) or "").strip()
        pos = (row.get(pos_col) or "").strip()
        if not form or not lemma or not pos or not re.search(r"[A-Za-zÀ-ÖØ-öø-ÿ]", form):
            continue
        if len(form) > 48 or any(ch.isdigit() for ch in form) or not all(ch.isalpha() or ch in "-'’ " for ch in form):
            continue
        try:
            form_freq = float((row.get(film_form_col) or "0").replace(",", "."))
            film_freq = float((row.get(film_lemma_col) or "0").replace(",", "."))
            book_freq = float((row.get(book_lemma_col) or "0").replace(",", "."))
        except ValueError:
            continue
        if form_freq <= 0 or film_freq < 0 or book_freq < 0:
            continue
        gender = (row.get(gender_col) or "").strip() or None
        number = (row.get(number_col) or "").strip() or None
        rows.append({"lemma":lemma, "form":form, "part_of_speech":pos, "gender":gender,
                     "number":number, "form_frequency":form_freq, "film_lemma_frequency":film_freq,
                     "book_lemma_frequency":book_freq, "combined_frequency":film_freq + book_freq})
    grouped: dict[tuple[str,str], list[dict]] = {}
    for item in rows:
        grouped.setdefault((item["lemma"].casefold(), item["part_of_speech"].casefold()), []).append(item)
    candidates = []
    for key, items in grouped.items():
        lemma = sorted(items, key=lambda x:(x["lemma"].casefold(),x["lemma"]))[0]["lemma"]
        form_map = {}
        for item in items:
            k = item["form"].casefold()
            if k not in form_map or (item["form_frequency"], item["form"]) > (form_map[k]["form_frequency"], form_map[k]["form"]):
                form_map[k] = item
        all_forms = sorted(form_map.values(), key=lambda x:(-x["form_frequency"],x["form"].casefold(),x["form"]))
        candidates.append({"lemma":lemma,"part_of_speech":sorted(items,key=lambda x:(x["part_of_speech"].casefold(),x["part_of_speech"]))[0]["part_of_speech"],
                           "combined_frequency":max(x["combined_frequency"] for x in items),
                           "film_frequency":max(x["film_lemma_frequency"] for x in items),
                           "book_frequency":max(x["book_lemma_frequency"] for x in items),
                           "gender":next((x["gender"] for x in items if x["gender"]),None),
                           "number":next((x["number"] for x in items if x["number"]),None),
                           "forms":all_forms})
    # A surface spelling may be attached to only one (lemma, POS): choose its
    # highest-frequency Lexique row, with deterministic lemma/POS tie-breaks.
    owners: dict[str, dict] = {}
    occurrences: dict[str, list[dict]] = {}
    for candidate in candidates:
        for form in candidate["forms"]:
            occurrences.setdefault(form["form"].casefold(), []).append({"candidate":candidate,"form":form})
    ambiguous = []
    for spelling, options in sorted(occurrences.items()):
        unique = {(o["candidate"]["lemma"].casefold(),o["candidate"]["part_of_speech"].casefold()):o for o in options}
        options = list(unique.values())
        winner = sorted(options,key=lambda o:(-o["form"]["form_frequency"],o["candidate"]["lemma"].casefold(),
                                               o["candidate"]["lemma"],o["candidate"]["part_of_speech"].casefold(),
                                               o["candidate"]["part_of_speech"]))[0]
        owners[spelling] = winner["candidate"]
        if len(options) > 1:
            ambiguous.append({"form":winner["form"]["form"],"assigned_lemma":winner["candidate"]["lemma"],
                              "assigned_pos":winner["candidate"]["part_of_speech"],
                              "assignment_frequency":winner["form"]["form_frequency"],
                              "candidates":[{"lemma":o["candidate"]["lemma"],"pos":o["candidate"]["part_of_speech"],
                                             "frequency":o["form"]["form_frequency"]} for o in sorted(options,key=lambda o:(o["candidate"]["lemma"].casefold(),o["candidate"]["part_of_speech"].casefold()))]})
    mapping_path = DATA / "headword-typography.json"
    typography = json.loads(mapping_path.read_text(encoding="utf-8",errors="strict"))
    output = []
    for candidate in candidates:
        own_forms = [f for f in candidate["forms"] if owners.get(f["form"].casefold()) is candidate]
        common = [f for f in own_forms if f["form_frequency"] >= 1.0]
        rare = [f for f in own_forms if f["form_frequency"] < 1.0]
        common = sorted(common,key=lambda x:(-x["form_frequency"],x["form"].casefold(),x["form"]))
        rare = sorted(rare,key=lambda x:(-x["form_frequency"],x["form"].casefold(),x["form"]))
        if len(common) < 1:
            continue
        pos = candidate["part_of_speech"].upper()
        noun_adj = pos in {"NOM","ADJ"}
        lemma_key = candidate["lemma"].casefold()
        display = typography.get(lemma_key, candidate["lemma"])
        register = "vulgar" if lemma_key == "baiser" else "needs_review"
        output.append({"lemma":candidate["lemma"],"display_headword":display,"part_of_speech":candidate["part_of_speech"],
                       "gender":candidate["gender"] if noun_adj else None,"number":candidate["number"] if noun_adj else None,
                       "lemma_frequency":candidate["combined_frequency"],"freqlemfilms2":candidate["film_frequency"],
                       "freqlemlivres":candidate["book_frequency"],"ranking_formula":"freqlemfilms2 + freqlemlivres",
                       "top_forms":[{"form":f["form"],"frequency":f["form_frequency"]} for f in common[:3]],
                       "rare_forms":[{"form":f["form"],"frequency":f["form_frequency"]} for f in rare],
                       "register":register,"source":{"name":"Lexique 3.83","url":LEXIQUE_URL},
                       "licence":LICENCE_LEXIQUE,"needs_review":register=="needs_review"})
    # Compute old film-only top 300 with the same (lemma, POS) identity for an honest comparison.
    film_ranked = sorted(output,key=lambda x:(-x["freqlemfilms2"],x["lemma"].casefold(),x["lemma"],x["part_of_speech"].casefold()))
    combined_ranked = sorted(output,key=lambda x:(-x["lemma_frequency"],x["lemma"].casefold(),x["lemma"],x["part_of_speech"].casefold()))
    film_keys = {(r["lemma"].casefold(),r["part_of_speech"].casefold()) for r in film_ranked[:300]}
    combined_keys = {(r["lemma"].casefold(),r["part_of_speech"].casefold()) for r in combined_ranked[:300]}
    changed = len(film_keys.symmetric_difference(combined_keys)) // 2
    rows_out = combined_ranked[:300]
    if len(rows_out) != 300:
        raise ValueError(f"Expected at least 300 (lemma, POS) groups; found {len(rows_out)}")
    (DATA / "ambiguous-forms.json").write_text(json.dumps(ambiguous,ensure_ascii=False,indent=2)+"\\n",encoding="utf-8",errors="strict")
    meta = {"source":"Lexique 3.83","licence":LICENCE_LEXIQUE,"encoding":encoding,
            "film_lemma_frequency_column":film_lemma_col,"book_lemma_frequency_column":book_lemma_col,
            "ranking_formula":"freqlemfilms2 + freqlemlivres","top300_changed_vs_film_only":changed,
            "sentinel_presence_in_source":sentinel_seen,"ambiguous_form_count":len(ambiguous)}
    return rows_out, encoding, meta

def dicollecte_forms() -> tuple[set[str] | None, dict]:
    detail = {"status":"unavailable", "source":"Dicollecte/Grammalecte Hunspell 7.7", "url":DICO_URL, "licence":LICENCE_DICO, "matched_count":None, "mismatch_count":None, "mismatches":[], "note":""}
    try:
        with zipfile.ZipFile(DICO_ZIP) as zf:
            names = zf.namelist()
            pairs = []
            for dic in names:
                if not dic.lower().endswith(".dic"): continue
                stem = dic.rsplit(".",1)[0]
                aff = next((n for n in names if n.rsplit(".",1)[0] == stem and n.lower().endswith(".aff")), None)
                if not aff: continue
                data = zf.read(aff)
                if data.startswith(bytes.fromhex("efbbbf")): data = data[3:]
                aff_text = data.decode("utf-8-sig", errors="strict")
                lines = aff_text.replace("\r\n","\n").replace("\r","\n").splitlines()
                match = next((re.match(r"^\s*SET\s+([^\s#]+)", line, re.I) for line in lines if re.match(r"^\s*SET\s+([^\s#]+)", line, re.I)), None)
                if match: pairs.append((dic, aff, match.group(1)))
            if not pairs:
                detail["note"] = "unavailable: no paired .aff file declares SET; behavior without SET was not independently confirmed"
                return None, detail
            dic, aff, declared = next((p for p in pairs if "toutesvariantes" in p[0].lower()), pairs[0])
            try: codec = codecs.lookup(declared).name
            except LookupError:
                detail["note"] = f"unavailable: unknown codec in .aff SET {declared!r}"
                return None, detail
            raw = zf.read(dic).decode(codec, errors="strict")
            if any(marker in raw for marker in FORBIDDEN):
                detail["note"] = f"unavailable: forbidden marker after declared SET {declared}"
                return None, detail
            words = set()
            for line in raw.splitlines()[1:]:
                token = line.strip().split("/",1)[0]
                if token and not token.isdigit(): words.add(token.casefold())
            detail.update(status="available", encoding=f".aff SET {declared} ({codec})", dictionary=dic, aff=aff)
            return words, detail
    except (OSError, zipfile.BadZipFile, UnicodeError) as exc:
        detail["note"] = f"unavailable: {type(exc).__name__}: {exc}"
        return None, detail

def lefff_forms(probe_out: dict) -> tuple[set[str] | None, dict]:
    detail = {"status":"unavailable", "source":"Lefff 2.1", "url":LEFFF_URL, "licence":LICENCE_LEFFF, "matched_count":None, "mismatch_count":None, "mismatches":[], "note":""}
    try:
        raw = source_bytes(LEFFF, compressed=True)
        encoding, text, probe = probe_lefff(raw)
        probe_out.update(probe)
        if encoding is None:
            detail["note"] = probe["reason"]
            return None, detail
        forms = set()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"): continue
            fields = line.split("\t")
            surface = fields[0].strip() if fields else ""
            if surface: forms.add(surface.casefold())
        if len(forms) < 1000:
            detail["note"] = f"unavailable: unexpected surface-form count {len(forms)}"
            return None, detail
        detail.update(status="available", encoding=encoding, parsed_forms=len(forms))
        return forms, detail
    except (OSError, UnicodeError, ValueError) as exc:
        status_file = DATA / "raw/lefff-download-status.txt"
        if not LEFFF.is_file() and status_file.is_file():
            detail["note"] = status_file.read_text(encoding="utf-8", errors="strict").strip()
        else:
            detail["note"] = f"unavailable: {type(exc).__name__}: {exc}"
        return None, detail

def validate_output(rows: list[dict], serialized: str) -> None:
    if len(rows) != 300: raise ValueError(f"Pilot must contain exactly 300 lemmas; got {len(rows)}")
    if len({r["lemma"].casefold() for r in rows}) != 300: raise ValueError("Pilot has duplicate lemmas")
    if any(marker in serialized for marker in FORBIDDEN): raise ValueError("Output contains forbidden U+FFFD or mojibake marker")
    expected = sorted(rows, key=lambda x:(-x["lemma_frequency"], -x["top_forms"][0]["frequency"], x["lemma"].casefold(), x["lemma"]))
    if rows != expected: raise ValueError("Pilot ordering/tie-break validation failed")
    for row in rows:
        if len(row["top_forms"]) != 3: raise ValueError(f"Lemma {row['lemma']!r} does not have exactly three forms")
        if any(marker in json.dumps(row, ensure_ascii=False) for marker in FORBIDDEN):
            raise ValueError(f"Forbidden marker in lemma {row['lemma']!r}")
        forms = row["top_forms"]
        if forms != sorted(forms, key=lambda x:(-x["frequency"], x["form"].casefold(), x["form"])):
            raise ValueError(f"Top forms are not correctly ranked for lemma {row['lemma']!r}")

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-random", type=int, default=40)
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    rows, lexique_encoding, lexique_meta = read_lexique()
    dico, dico_detail = dicollecte_forms()
    probe = {}
    lefff, lefff_detail = lefff_forms(probe)
    # Cross-check is at lemma level by comparing each lemma's three surface forms.
    pilot_forms = [form["form"].casefold() for row in rows for form in row["top_forms"]]
    for words, detail in ((dico, dico_detail), (lefff, lefff_detail)):
        if words is None: continue
        missing = sorted({form for form in pilot_forms if form not in words}, key=lambda x:(x.casefold(), x))
        detail["matched_count"] = len(set(pilot_forms) & words)
        detail["mismatch_count"] = len(missing)
        detail["mismatches"] = missing
        detail["note"] = "mismatches are distinct pilot surface forms absent from the cross-check source"
    cross = {"pilot_source":"Lexique 3.83", "pilot_licence":LICENCE_LEXIQUE,
             "sources":{"Dicollecte":dico_detail, "Lefff":lefff_detail}, "lefff_encoding_probe":probe,
             "summary":{"pilot_lemmas":300, "pilot_distinct_forms":len(set(pilot_forms)),
                        "Dicollecte_matched_forms":dico_detail["matched_count"], "Dicollecte_mismatches":dico_detail["mismatch_count"],
                        "Lefff_matched_forms":lefff_detail["matched_count"], "Lefff_mismatches":lefff_detail["mismatch_count"]}}
    cross_text = json.dumps(cross, ensure_ascii=False, indent=2) + "\n"
    if any(marker in cross_text for marker in FORBIDDEN): raise ValueError("Cross-check output contains forbidden U+FFFD or mojibake marker")
    CROSSCHECKS.write_text(cross_text, encoding="utf-8", errors="strict")
    output_text = json.dumps(rows, ensure_ascii=False, indent=2) + "\n"
    validate_output(rows, output_text)
    OUTPUT.write_text(output_text, encoding="utf-8", errors="strict")
    reread_text = OUTPUT.read_text(encoding="utf-8", errors="strict")
    reread = json.loads(reread_text)
    validate_output(reread, reread_text)
    manifest_files = {
        "Lexique383.tsv":{"sha256":sha256_file(LEXIQUE),"url":LEXIQUE_URL},
        "hunspell-french-dictionaries-v7.7.zip":{"sha256":sha256_file(DICO_ZIP),"url":DICO_URL}
    }
    if LEFFF.is_file():
        manifest_files["lefff-2.1.txt.gz"] = {"sha256":sha256_file(LEFFF),"url":LEFFF_URL}
    elif MANIFEST.exists():
        # Preserve the last known Lefff checksum while the optional source is unavailable.
        prior_manifest = json.loads(MANIFEST.read_text(encoding="utf-8", errors="strict"))
        prior_lefff = prior_manifest.get("files", {}).get("lefff-2.1.txt.gz")
        if prior_lefff:
            manifest_files["lefff-2.1.txt.gz"] = prior_lefff
    manifest = {"algorithm":"SHA-256","files":manifest_files}
    if MANIFEST.exists():
        prior = json.loads(MANIFEST.read_text(encoding="utf-8", errors="strict"))
        for name, current in manifest_files.items():
            if prior.get("files", {}).get(name) != current:
                raise ValueError(f"Source checksum mismatch for {name}; upstream bytes changed. Review manifest before updating.")
    else:
        MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8", errors="strict")
    accented_count = sum(1 for row in reread if ACCENTED.search(row["lemma"]) or any(ACCENTED.search(form["form"]) for form in row["top_forms"]))
    print(f"VALID: 300 distinct Lexique lemmas; ranked by {lexique_meta['lemma_frequency_column']}; tie-break: descending top-form freqfilms2, lemma casefold ascending, original lemma ascending.")
    print(f"ACCENTED OUTPUT VALIDATION: {accented_count} of 300 entries contain at least one of é, è, ê, à, ç, ù; no U+FFFD or \"Ã\" found in output.")
    print(f"CROSS-CHECKS: Dicollecte status={dico_detail['status']} matched_forms={dico_detail['matched_count']} mismatches={dico_detail['mismatch_count']} note={dico_detail['note']}")
    print(f"CROSS-CHECKS: Lefff status={lefff_detail['status']} matched_forms={lefff_detail['matched_count']} mismatches={lefff_detail['mismatch_count']} note={lefff_detail['note']}")
    print("TOP 20 RANKED LEMMAS")
    for i, row in enumerate(reread[:20], 1):
        forms = ", ".join(f"{x['form']}({x['frequency']})" for x in row["top_forms"])
        print(f"{i}. {row['lemma']} | lemma_frequency={row['lemma_frequency']} | column={row['lemma_frequency_column']} | POS={row['part_of_speech']} | gender={row['gender']} | top_forms={forms}")
    if args.print_random:
        sample = random.SystemRandom().sample(reread, min(args.print_random, len(reread)))
        print(f"RANDOM REVIEW SAMPLE ({len(sample)} lemmas)")
        for item in sample:
            forms = ", ".join(f"{x['form']}({x['frequency']})" for x in item["top_forms"])
            print(f"{item['lemma']} | lemma_frequency={item['lemma_frequency']} | POS={item['part_of_speech']} | gender={item['gender']} | top_forms={forms} | source=Lexique 3.83 | licence={LICENCE_LEXIQUE}")
    return 0

if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
