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
    film_form_col = col("freqfilms2")
    book_form_col = col("freqlivres")
    film_lemma_col = col("freqlemfilms2")
    book_lemma_col = col("freqlemlivres")
    print(f"RANKING FORMULA: {film_lemma_col} + {book_lemma_col} (films + books lemma frequencies); form frequency formula: {film_form_col} + {book_form_col}.")
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
            form_freq = float((row.get(film_form_col) or "0").replace(",", ".")) + float((row.get(book_form_col) or "0").replace(",", "."))
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
    # Keep elided spellings as forms, never as headwords.
    elided_targets = {
        "l'": [("le","ART:def"),("la","ART:def")],
        "d'": [("de","PRE")], "s'": [("se","PRO:per")], "t'": [("te","PRO:per")],
        "n'": [("ne","ADV")], "j'": [("je","PRO:per")], "m'": [("me","PRO:per")],
        "c'": [("ce","PRO:dem")], "qu'": [("que","PRO:rel"),("que","CON")]
    }
    elided_rows = []
    ordinary_rows = []
    for item in rows:
        form_key = item["form"].casefold().replace("’", "'")
        lemma_key = item["lemma"].casefold().replace("’", "'")
        if form_key in elided_targets:
            elided_rows.append(item)
        elif lemma_key in elided_targets:
            continue
        else:
            ordinary_rows.append(item)
    rows = ordinary_rows
    grouped: dict[tuple[str,str], list[dict]] = {}
    for item in rows:
        pos_key = item["part_of_speech"].casefold()
        if pos_key in {"ver","aux"}:
            pos_key = "ver"
        grouped.setdefault((item["lemma"].casefold(), pos_key), []).append(item)
    candidates = []
    for key, items in grouped.items():
        lemma = sorted(items, key=lambda x:(x["lemma"].casefold(),x["lemma"]))[0]["lemma"]
        pos_value = "VER" if key[1] == "ver" else sorted(items,key=lambda x:(x["part_of_speech"].casefold(),x["part_of_speech"]))[0]["part_of_speech"]
        form_map = {}
        for item in items:
            k = item["form"].casefold()
            if k not in form_map or (item["form_frequency"], item["form"]) > (form_map[k]["form_frequency"], form_map[k]["form"]):
                form_map[k] = item
        all_forms = sorted(form_map.values(), key=lambda x:(-x["form_frequency"],x["form"].casefold(),x["form"]))
        candidates.append({"lemma":lemma,"part_of_speech":pos_value,
                           "combined_frequency":max(x["combined_frequency"] for x in items),
                           "film_frequency":max(x["film_lemma_frequency"] for x in items),
                           "book_frequency":max(x["book_lemma_frequency"] for x in items),
                           "gender":next((x["gender"] for x in items if x["gender"]),None),
                           "number":next((x["number"] for x in items if x["number"]),None),
                           "forms":all_forms})
    # Attach elisions to base lemmas without letting the elided rows change lemma ranking.
    for alias_row in elided_rows:
        alias = alias_row["form"].casefold().replace("’", "'")
        for base_lemma, base_pos in elided_targets.get(alias, []):
            for candidate in candidates:
                if candidate["lemma"].casefold() == base_lemma and candidate["part_of_speech"].casefold() == base_pos.casefold():
                    candidate["forms"].append({**alias_row, "form":alias_row["form"]})
    mapping_path = DATA / "headword-typography.json"
    typography = json.loads(mapping_path.read_text(encoding="utf-8",errors="strict"))
    overrides_path = DATA / "homograph-overrides.json"
    homograph_overrides = json.loads(overrides_path.read_text(encoding="utf-8",errors="strict"))
    # Normalize VER/AUX and preserve every shared spelling in each lemma's display list.
    occurrences: dict[str, list[dict]] = {}
    for candidate in candidates:
        dedup = {}
        for form in candidate["forms"]:
            k = form["form"].casefold()
            if k not in dedup or form["form_frequency"] > dedup[k]["form_frequency"]:
                dedup[k] = form
        candidate["forms"] = sorted(dedup.values(),key=lambda x:(-x["form_frequency"],x["form"].casefold(),x["form"]))
        for form in candidate["forms"]:
            occurrences.setdefault(form["form"].casefold(), []).append({"candidate":candidate,"form":form})
    ambiguous = []
    for spelling, options in sorted(occurrences.items()):
        unique = {(o["candidate"]["lemma"].casefold(),o["candidate"]["part_of_speech"].casefold()):o for o in options}
        options = list(unique.values())
        override = homograph_overrides.get(spelling)
        override_options = [o for o in options if o["candidate"]["lemma"].casefold() == str(override).casefold()]
        if override_options:
            winner = sorted(override_options,key=lambda o:(-o["candidate"]["combined_frequency"],o["candidate"]["lemma"].casefold(),o["candidate"]["part_of_speech"].casefold()))[0]
            decision = "committed_override"
        else:
            winner = sorted(options,key=lambda o:(-o["form"]["form_frequency"],-o["candidate"]["combined_frequency"],o["candidate"]["lemma"].casefold(),o["candidate"]["part_of_speech"].casefold()))[0]
            decision = "highest_form_frequency_then_lemma_frequency"
        for option in options:
            option["form"]["shared_form"] = len(options) > 1
            option["form"]["frequency_attributed_to"] = winner["candidate"]["lemma"]
        if len(options) > 1 or override:
            ambiguous.append({"form":winner["form"]["form"],"assigned_lemma":winner["candidate"]["lemma"],
                              "assigned_pos":winner["candidate"]["part_of_speech"],"decision":decision,
                              "override":override,"assignment_frequency":round(winner["form"]["form_frequency"],2),
                              "candidates":[{"lemma":o["candidate"]["lemma"],"pos":o["candidate"]["part_of_speech"],
                                             "form_frequency":round(o["form"]["form_frequency"],2),
                                             "lemma_frequency":round(o["candidate"]["combined_frequency"],2)}
                                            for o in sorted(options,key=lambda o:(o["candidate"]["lemma"].casefold(),o["candidate"]["part_of_speech"].casefold()))]})
    output = []
    for candidate in candidates:
        common = [f for f in candidate["forms"] if f["form_frequency"] >= 1.0]
        rare = [f for f in candidate["forms"] if f["form_frequency"] < 1.0]
        common = sorted(common,key=lambda x:(-x["form_frequency"],x["form"].casefold(),x["form"]))
        rare = sorted(rare,key=lambda x:(-x["form_frequency"],x["form"].casefold(),x["form"]))
        if not common:
            continue
        pos = candidate["part_of_speech"].upper()
        noun_adj = pos in {"NOM","ADJ"}
        lemma_key = candidate["lemma"].casefold()
        display = typography.get(lemma_key, candidate["lemma"])
        register = "vulgar" if lemma_key == "baiser" else "unreviewed"
        def form_obj(f):
            form_text = typography.get(f["form"].casefold(), f["form"])
            return {"form":form_text,"frequency":round(f["form_frequency"],2),
                    "shared_form":bool(f.get("shared_form",False)),
                    "frequency_attributed_to":f.get("frequency_attributed_to",candidate["lemma"])}
        output.append({"lemma":candidate["lemma"],"display_headword":display,"part_of_speech":candidate["part_of_speech"],
                       "gender":candidate["gender"] if noun_adj else None,"number":candidate["number"] if noun_adj else None,
                       "lemma_frequency":round(candidate["combined_frequency"],2),"freqlemfilms2":round(candidate["film_frequency"],2),
                       "freqlemlivres":round(candidate["book_frequency"],2),"ranking_formula":"freqlemfilms2 + freqlemlivres",
                       "top_forms":[form_obj(f) for f in common[:3]],
                       "rare_forms":[form_obj(f) for f in rare],
                       "register":register,"source":{"name":"Lexique 3.83","url":LEXIQUE_URL},
                       "licence":LICENCE_LEXIQUE,"needs_review":register=="unreviewed"})
    # Rank by lemma+POS identity; VER/AUX already merged. Elided spellings cannot be headwords.
    film_ranked = sorted(output,key=lambda x:(-x["freqlemfilms2"],x["lemma"].casefold(),x["lemma"],x["part_of_speech"].casefold()))
    combined_ranked = sorted(output,key=lambda x:(-x["lemma_frequency"],x["lemma"].casefold(),x["lemma"],x["part_of_speech"].casefold()))
    film_keys = {(r["lemma"].casefold(),r["part_of_speech"].casefold()) for r in film_ranked[:300]}
    combined_keys = {(r["lemma"].casefold(),r["part_of_speech"].casefold()) for r in combined_ranked[:300]}
    changed = len(film_keys.symmetric_difference(combined_keys)) // 2
    rows_out = combined_ranked[:300]
    if len(rows_out) != 300:
        raise ValueError(f"Expected at least 300 lemma/POS entries; found {len(rows_out)}")
    (DATA / "ambiguous-forms.json").write_text(json.dumps(ambiguous,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",errors="strict")
    meta = {"source":"Lexique 3.83","licence":LICENCE_LEXIQUE,"encoding":encoding,
            "film_lemma_frequency_column":film_lemma_col,"book_lemma_frequency_column":book_lemma_col,
            "ranking_formula":"freqlemfilms2 + freqlemlivres","top300_changed_vs_film_only":changed,
            "sentinel_presence_in_source":sentinel_seen,"ambiguous_form_count":len(ambiguous)}
    return rows_out, encoding, meta

def dicollecte_forms(forms: list[str]) -> tuple[set[str] | None, dict]:
    detail = {"status":"unavailable","source":"Dicollecte/Grammalecte Hunspell 7.7","url":DICO_URL,"licence":LICENCE_DICO,"matched_count":None,"mismatch_count":None,"mismatches":[],"unknown_forms":[],"note":""}
    import shutil, subprocess, tempfile
    hunspell=shutil.which("hunspell")
    dictionary=ROOT/"data/raw/dicollecte/fr-toutesvariantes"
    if not hunspell:
        detail["note"]="unavailable: hunspell executable is not installed"
        return None,detail
    if not dictionary.with_suffix(".dic").is_file() or not dictionary.with_suffix(".aff").is_file():
        detail["note"]="unavailable: extracted fr-toutesvariantes .dic/.aff files are missing"
        return None,detail
    try:
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",errors="strict",delete=False) as handle:
            handle.write("\n".join(forms)+"\n"); input_path=Path(handle.name)
        try:
            proc=subprocess.run([hunspell,"-d",str(dictionary),"-l",str(input_path)],capture_output=True,text=True,encoding="utf-8",errors="strict",check=False,timeout=90)
        finally: input_path.unlink(missing_ok=True)
        if proc.returncode not in (0,1):
            detail["note"]=f"unavailable: hunspell exited {proc.returncode}: {proc.stderr.strip()}"
            return None,detail
        unknown=sorted({x.strip().casefold() for x in proc.stdout.splitlines() if x.strip()},key=lambda x:(x.casefold(),x))
        matched=sorted(set(x.casefold() for x in forms)-set(unknown))
        detail.update(status="available",matched_count=len(matched),mismatch_count=len(unknown),mismatches=unknown,unknown_forms=unknown,dictionary="fr-toutesvariantes.dic",note="unknown forms generated by hunspell -d fr-toutesvariantes -l")
        return set(matched),detail
    except (OSError,UnicodeError,subprocess.TimeoutExpired) as exc:
        detail["note"]=f"unavailable: {type(exc).__name__}: {exc}"
        return None,detail

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
    if len(rows)!=300: raise ValueError(f"Pilot must contain exactly 300 entries; got {len(rows)}")
    keys=[(r["lemma"].casefold(),r["part_of_speech"].casefold()) for r in rows]
    if len(set(keys))!=300: raise ValueError("Pilot has duplicate (lemma, POS) groups")
    if any(r["lemma"].casefold() in {"l'","d'","s'","t'","n'","j'","m'","c'","qu'"} for r in rows): raise ValueError("Elided form cannot be a headword")
    if any(marker in serialized for marker in FORBIDDEN): raise ValueError("Output contains forbidden U+FFFD or mojibake marker")
    if rows!=sorted(rows,key=lambda x:(-x["lemma_frequency"],x["lemma"].casefold(),x["lemma"],x["part_of_speech"].casefold())): raise ValueError("Pilot ranking validation failed")
    for row in rows:
        if row["part_of_speech"].upper() not in {"NOM","ADJ"} and (row["gender"] is not None or row["number"] is not None): raise ValueError(f"Non-nominal gender/number must be null: {row['lemma']}")
        if row["register"] not in {"neutral","informal","vulgar","unreviewed"}: raise ValueError("Invalid register")
        if row["lemma"].casefold()=="baiser" and row["register"]!="vulgar": raise ValueError("baiser must be vulgar")
        if any(float(f["frequency"])<1.0 for f in row["top_forms"]): raise ValueError("Rare form in top_forms")
        if row["top_forms"]!=sorted(row["top_forms"],key=lambda x:(-x["frequency"],x["form"].casefold(),x["form"])): raise ValueError("Top forms ordering invalid")

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--print-random",type=int,default=40)
    args=parser.parse_args()
    DATA.mkdir(parents=True,exist_ok=True)
    rows,encoding,meta=read_lexique()
    forms=sorted({f["form"] for r in rows for f in r["top_forms"]+r["rare_forms"]},key=lambda x:(x.casefold(),x))
    dico,dico_detail=dicollecte_forms(forms)
    probe={}
    lefff,lefff_detail=lefff_forms(probe)
    pilot_forms=sorted({f["form"].casefold() for r in rows for f in r["top_forms"]+r["rare_forms"]})
    if lefff is not None:
        missing=sorted(set(pilot_forms)-lefff,key=lambda x:(x.casefold(),x))
        lefff_detail.update(matched_count=len(set(pilot_forms)&lefff),mismatch_count=len(missing),mismatches=missing)
    cross={"pilot_source":"Lexique 3.83","pilot_licence":LICENCE_LEXIQUE,"ranking_formula":meta["ranking_formula"],"top300_changed_vs_film_only":meta["top300_changed_vs_film_only"],
           "sources":{"Dicollecte":dico_detail,"Lefff":lefff_detail},"lefff_encoding_probe":probe,
           "summary":{"pilot_entries":len(rows),"pilot_distinct_forms":len(pilot_forms),"Dicollecte_matched_forms":dico_detail["matched_count"],"Dicollecte_unknown_forms":dico_detail["mismatch_count"],"Lefff_matched_forms":lefff_detail["matched_count"],"Lefff_mismatches":lefff_detail["mismatch_count"]}}
    CROSSCHECKS.write_text(json.dumps(cross,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",errors="strict")
    output_text=json.dumps(rows,ensure_ascii=False,indent=2)+"\n"
    validate_output(rows,output_text)
    OUTPUT.write_text(output_text,encoding="utf-8",errors="strict")
    validate_output(json.loads(OUTPUT.read_text(encoding="utf-8",errors="strict")),output_text)
    (DATA/"review-sheet.md").write_text(build_review_sheet(rows),encoding="utf-8",errors="strict")
    manifest_files={"Lexique383.tsv":{"sha256":sha256_file(LEXIQUE),"url":LEXIQUE_URL},"hunspell-french-dictionaries-v7.7.zip":{"sha256":sha256_file(DICO_ZIP),"url":DICO_URL}}
    if LEFFF.is_file(): manifest_files["lefff-2.1.txt.gz"]={"sha256":sha256_file(LEFFF),"url":LEFFF_URL}
    elif MANIFEST.exists():
        prior=json.loads(MANIFEST.read_text(encoding="utf-8",errors="strict"))
        if prior.get("files",{}).get("lefff-2.1.txt.gz"): manifest_files["lefff-2.1.txt.gz"]=prior["files"]["lefff-2.1.txt.gz"]
    manifest={"algorithm":"SHA-256","files":manifest_files}
    if MANIFEST.exists():
        prior=json.loads(MANIFEST.read_text(encoding="utf-8",errors="strict"))
        for name,value in manifest_files.items():
            if prior.get("files",{}).get(name)!=value: raise ValueError(f"Source checksum mismatch for {name}; review before updating.")
    else: MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",errors="strict")
    sample=random.Random(42).sample(rows,min(max(0,args.print_random),len(rows)))
    print(f"VALID: entries={len(rows)}; formula={meta['ranking_formula']}; top300_changed_vs_film_only={meta['top300_changed_vs_film_only']}; ambiguous_forms={meta['ambiguous_form_count']}")
    print(f"DICOLLECTE HUNSPELL: status={dico_detail['status']} matched={dico_detail['matched_count']} unknown={dico_detail['mismatch_count']}")
    print("FIRST 20 UNKNOWN FORMS: "+json.dumps(dico_detail["unknown_forms"][:20],ensure_ascii=False))
    print(f"LEFFF: status={lefff_detail['status']} note={lefff_detail['note']}")
    print(f"RANDOM REVIEW SAMPLE (seed=42, count={len(sample)})")
    for r in sample: print(f"{r['display_headword']} | POS={r['part_of_speech']} | register={r['register']} | top_forms={json.dumps(r['top_forms'],ensure_ascii=False)}")
    return 0

def build_review_sheet(rows: list[dict]) -> str:
    lines=["# French Engine Data — Teacher Review Sheet","","Confirm POS for quoi, peu, voilà, bonjour, and entries coded ADJ:ind, ADJ:int, or ONO.","The review column is intentionally empty.","","| # | Headword | Gender | POS (Lexique code) | POS note | Forms | Teacher register | OK/Wrong/Fix |","|---:|---|---|---|---|---|---|---|"]
    pos_note_lemmas={"quoi","peu","voilà","bonjour"}
    for i,r in enumerate(rows,1):
        head=r["display_headword"]
        if r["part_of_speech"].upper()=="NOM":
            article="la" if (r.get("gender") or "").casefold() in {"f","fem","féminin","feminine"} else "le"
            head=f"{article} {head}"
        gender=r.get("gender") or "—"
        note="Confirm Lexique POS" if r["lemma"].casefold() in pos_note_lemmas or r["part_of_speech"].upper() in {"ADJ:IND","ADJ:INT","ONO"} else ""
        forms=", ".join(f["form"] for f in r["top_forms"]).replace("|","\\|")
        lines.append(f"| {i} | {head} | {gender} | {r['part_of_speech']} | {note} | {forms} | {r['register']} |  |")
    return "\n".join(lines)+"\n"

if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
