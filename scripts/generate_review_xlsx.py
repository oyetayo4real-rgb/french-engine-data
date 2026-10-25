#!/usr/bin/env python3
"""Generate the French teacher workbook from the canonical review-sheet CSV."""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "review-sheet.csv"
XLSX_PATH = ROOT / "data" / "review-sheet.xlsx"

CATEGORY_NAMES = {
    "VER": "verbe",
    "NOM": "nom",
    "PRE": "préposition",
    "ADV": "adverbe",
    "CON": "conjonction",
    "ART:def": "article défini",
    "ART:ind": "article indéfini",
    "PRO:per": "pronom personnel",
    "PRO:int": "pronom interrogatif",
    "PRO:rel": "pronom relatif",
    "PRO:dem": "pronom démonstratif",
    "PRO:ind": "pronom indéfini",
    "PRO:pos": "pronom possessif",
    "ADJ:pos": "adjectif possessif",
    "ADJ:ind": "adjectif indéfini",
    "ADJ:dem": "adjectif démonstratif",
    "ADJ:num": "adjectif numéral",
    "ADJ:int": "adjectif interrogatif",
    "ADJ": "adjectif",
    "ONO": "onomatopée",
    "LOC:int": "locution interrogative",
}
REGISTER_NAMES = {
    "unreviewed": "courant",
    "needs_review": "courant",
    "common": "courant",
    "familiar": "familier",
    "familier": "familier",
    "vulgar": "vulgaire",
    "vulgaire": "vulgaire",
    "avoid_for_beginners": "à éviter pour débutants",
    "à éviter pour débutants": "à éviter pour débutants",
    "courant": "courant",
}

INSTRUCTIONS = [
    "Lisez chaque mot et vérifiez sa catégorie, ses formes et son registre.",
    "Consultez les formes proposées et corrigez-les si nécessaire.",
    "Dans « Votre avis », choisissez une option dans la liste déroulante.",
    "OK : l’entrée est correcte et peut être conservée.",
    "Faux : l’entrée ou l’information est incorrecte.",
    "À corriger : l’entrée doit être modifiée ; indiquez la correction dans « Correction ».",
]

HEADERS = ["N°", "Mot", "Genre", "Catégorie", "Formes", "Registre", "Votre avis", "Correction"]


def read_rows() -> list[dict[str, str]]:
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            number = (row.get("#") or "").strip()
            if not number.isdigit():
                continue
            if not 1 <= int(number) <= 300:
                continue
            code = (row.get("POS (with Lexique code)") or "").strip()
            category = CATEGORY_NAMES.get(code)
            if category is None:
                prefix = code.split(":", 1)[0]
                generic = {"PRO": "pronom", "ADJ": "adjectif", "ART": "article"}.get(prefix)
                if generic is None:
                    raise ValueError("Lexique POS code has no French label: " + code)
                category = generic
            forms = re.sub(r"\(\+(\d+) more in data/pilot-300\.json\)", r"(+\1 autres formes)", (row.get("Forms") or "").replace("(shared form)", "(forme partagée)"))
            raw_register = (row.get("Teacher register") or "unreviewed").strip().casefold()
            register = REGISTER_NAMES.get(raw_register, "courant")
            rows.append({
                "number": number,
                "word": (row.get("Headword") or "").strip(),
                "gender": (row.get("Gender") or "").strip().replace("—", ""),
                "category": category,
                "pos": code,
                "forms": forms,
                "register": register,
            })
    rows.sort(key=lambda item: int(item["number"]))
    if len(rows) != 300 or [int(row["number"]) for row in rows] != list(range(1, 301)):
        raise ValueError("Expected exactly 300 numbered teacher rows in data/review-sheet.csv; got " + str(len(rows)))
    return rows


def build_workbook(rows: list[dict[str, str]]) -> None:
    wb = Workbook()
    instructions = wb.active
    instructions.title = "Instructions"
    instructions["A1"] = "Guide de relecture"
    instructions["A1"].font = Font(name="Aptos Display", size=16, bold=True, color="FFFFFF")
    instructions["A1"].fill = PatternFill("solid", fgColor="17365D")
    instructions["A1"].alignment = Alignment(vertical="center")
    instructions.row_dimensions[1].height = 30
    for index, line in enumerate(INSTRUCTIONS, 2):
        cell = instructions.cell(row=index, column=1, value=line)
        cell.font = Font(name="Aptos", size=11)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        cell.fill = PatternFill("solid", fgColor="F2F6FA" if index % 2 == 0 else "FFFFFF")
        instructions.row_dimensions[index].height = 32
    instructions.column_dimensions["A"].width = 110
    instructions.freeze_panes = "A2"
    instructions.sheet_view.showGridLines = False

    words = wb.create_sheet("Mots")
    words.append(HEADERS)
    for cell in words[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    words.row_dimensions[1].height = 30

    for row in rows:
        words.append([
            int(row["number"]),
            row["word"],
            row["gender"],
            row["category"],
            row["forms"],
            row["register"],
            None,
            None,
        ])
    widths = {"A": 7, "B": 25, "C": 10, "D": 25, "E": 65, "F": 28, "G": 18, "H": 35}
    for column, width in widths.items():
        words.column_dimensions[column].width = width
    thin_gray = Side(style="thin", color="D9E2F3")
    for row_index in range(2, 302):
        fill_color = "F2F6FA" if row_index % 2 == 0 else "FFFFFF"
        for cell in words[row_index]:
            cell.fill = PatternFill("solid", fgColor=fill_color)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=thin_gray)
        words.row_dimensions[row_index].height = 42
    words.freeze_panes = "A2"
    words.auto_filter.ref = "A1:H301"
    words.sheet_view.showGridLines = False

    opinion = DataValidation(type="list", formula1='"OK,Faux,À corriger"', allow_blank=True)
    opinion.error = "Choisissez OK, Faux ou À corriger dans la liste."
    opinion.errorTitle = "Avis non valide"
    opinion.prompt = "Choisissez votre avis."
    opinion.promptTitle = "Votre avis"
    words.add_data_validation(opinion)
    opinion.add("G2:G301")

    register = DataValidation(type="list", formula1='"courant,familier,vulgaire,à éviter pour débutants"', allow_blank=False)
    register.error = "Choisissez un registre dans la liste."
    register.errorTitle = "Registre non valide"
    words.add_data_validation(register)
    register.add("F2:F301")

    wb.properties.title = "Relecture du vocabulaire français"
    wb.properties.subject = "Fiche pédagogique de validation des 300 mots"
    wb.properties.creator = "French Engine Data"
    # Audit sheet mirrors the exact operations consumed by the importer; overrides remain read-only.
    changes = wb.create_sheet("Changes")
    changes.append(["Op #", "Operation", "Lemma / POS", "Status", "Details"])
    for cell in changes[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    result_path = ROOT / "data" / "teacher-override-results.json"
    result = __import__("json").loads(result_path.read_text(encoding="utf-8", errors="strict"))
    for item in result.get("ops_applied", []):
        op = item.get("operation", {})
        if op.get("op") == "merge":
            identity = ", ".join(str(entry.get("lemma")) + " [" + str(entry.get("pos")) + "]" for entry in op.get("from", [])) + " → " + str(op.get("into", {}).get("lemma")) + " [" + str(op.get("into", {}).get("pos")) + "]"
        else:
            identity = str(op.get("lemma", "")) + " [" + str(op.get("pos", "")) + "]"
        changes.append([item.get("index"), op.get("op", "update"), identity, item.get("status"), __import__("json").dumps(op, ensure_ascii=False, sort_keys=True)])
    for label in result.get("unmatched_ops", []):
        changes.append([None, "unmatched", label, "FAIL", "No row matched lemma + POS"])
    changes.freeze_panes = "A2"
    changes.auto_filter.ref = changes.dimensions
    changes.sheet_view.showGridLines = False
    for col, width in {"A": 9, "B": 16, "C": 48, "D": 14, "E": 100}.items():
        changes.column_dimensions[col].width = width
    for row in changes.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    # Notes holds checks that do not belong in the fixed 300-row CSV.
    notes = wb.create_sheet("Notes")
    notes.append(["Sujet", "Note"])
    for cell in notes[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    notes.append(["Demandes de vérification POS hors des 300 mots classés", "Ces demandes sont conservées ici pour ne pas ajouter de lignes au CSV des 300 mots."])
    pilot_path = ROOT / "data" / "pilot-300.json"
    pilot = __import__("json").loads(pilot_path.read_text(encoding="utf-8", errors="strict"))
    pilot_lemmas = {str(row.get("lemma", "")).casefold() for row in pilot}
    requested_checks = ["quelque", "quelques", "chaque", "oh", "ah", "merci", "voilà", "pourquoi", "peu", "quoi PRO:int", "quoi PRO:rel", "le peu"]
    for item in requested_checks:
        lemma = item.split(" ", 1)[0].casefold()
        pos = item.split(" ", 1)[1] if " " in item else ""
        if item == "le peu":
            present = any(str(row.get("display_headword", "")).casefold() == "le peu" for row in pilot)
        else:
            present = any(str(row.get("lemma", "")).casefold() == lemma and (not pos or str(row.get("part_of_speech", "")).casefold() == pos.casefold()) for row in pilot)
        if not present:
            notes.append([item, "Confirmé par l'enseignante"])
    notes.append(["bonjour", "Note POS : code à confirmer ; entrée hors des 300 mots classés."])
    notes.freeze_panes = "A2"
    notes.column_dimensions["A"].width = 48
    notes.column_dimensions["B"].width = 100
    notes.sheet_view.showGridLines = False
    for row in notes.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    # Only corrected operation rows and ranked refills appear on this sheet.
    recheck = wb.create_sheet("À revérifier")
    recheck_headers = ["#", "Mot", "Genre", "Catégorie", "Formes", "Avis", "Correction"]
    recheck.append(recheck_headers)
    for cell in recheck[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    results = __import__("json").loads(result_path.read_text(encoding="utf-8", errors="strict"))
    operations = __import__("json").loads((DATA / "teacher-overrides.json").read_text(encoding="utf-8", errors="strict")).get("ops", [])
    final_by_key = {(str(row.get("lemma", "")).casefold(), str(row.get("part_of_speech", "")).casefold()): row for row in pilot}
    category_by_code = dict(CATEGORY_NAMES)
    category_by_code.update({"NOM": "nom", "VER": "verbe", "PRE": "préposition", "CON": "conjonction", "ADV": "adverbe"})
    def review_forms(row):
        forms = row.get("forms", row.get("top_forms", [])) or []
        return ", ".join(str(form.get("form", "")) for form in forms[:12])
    def add_recheck_row(word, pos, row, correction=""):
        recheck.append([
            recheck.max_row,
            word,
            str(row.get("gender") or ""),
            category_by_code.get(pos, category_by_code.get(pos.split(":", 1)[0], pos)),
            review_forms(row),
            None,
            correction,
        ])
    for op in operations:
        if op.get("op") == "merge":
            target = op.get("into", {})
            key = (str(target.get("lemma", "")).casefold(), str(target.get("pos", "")).casefold())
            row = final_by_key.get(key, {"lemma": target.get("lemma", ""), "display_headword": target.get("lemma", ""), "part_of_speech": target.get("pos", ""), "forms": []})
            add_recheck_row(str(row.get("display_headword", row.get("lemma", ""))), str(row.get("part_of_speech", target.get("pos", "")),), row)
            continue
        lemma, source_pos = str(op.get("lemma", "")), str(op.get("pos", ""))
        if op.get("op") == "delete":
            row = {"lemma": lemma, "display_headword": lemma, "part_of_speech": source_pos, "gender": None, "forms": []}
            add_recheck_row(lemma, source_pos, row)
            continue
        target_pos = str(op.get("set_pos", source_pos))
        row = final_by_key.get((lemma.casefold(), target_pos.casefold()))
        if row is None:
            row = {"lemma": lemma, "display_headword": op.get("display_headword", lemma), "part_of_speech": target_pos, "gender": op.get("gender"), "forms": []}
        add_recheck_row(str(op.get("display_headword", row.get("display_headword", lemma))), target_pos, row)
    for refill in results.get("refill_added", []):
        key = (str(refill.get("lemma", "")).casefold(), str(refill.get("pos", "")).casefold())
        row = final_by_key.get(key, {})
        if row:
            add_recheck_row(str(row.get("display_headword", row.get("lemma", ""))), str(row.get("part_of_speech", refill.get("pos", ""))), row,
                            "Réapprovisionnement — rang Lexique " + str(refill.get("rank", "inconnu")))
    recheck.freeze_panes = "A2"
    recheck.auto_filter.ref = recheck.dimensions
    recheck.sheet_view.showGridLines = False
    for col, width in {"A": 7, "B": 25, "C": 10, "D": 28, "E": 65, "F": 20, "G": 42}.items():
        recheck.column_dimensions[col].width = width
    for row in recheck.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    recheck_opinion = DataValidation(type="list", formula1='"OK,Faux,À corriger"', allow_blank=True)
    recheck_opinion.error = "Choisissez OK, Faux ou À corriger."
    recheck.add_data_validation(recheck_opinion)
    recheck_opinion.add("F2:F" + str(recheck.max_row))

    wb.save(XLSX_PATH)


def validate_workbook() -> None:
    wb = load_workbook(XLSX_PATH, read_only=False, data_only=True)
    try:
        if wb.sheetnames != ["Instructions", "Mots", "Changes", "Notes", "À revérifier"]:
            raise AssertionError("Workbook sheets must be Instructions and Mots")
        changes = wb["Changes"]
        if changes.max_row < 2 or changes["A1"].value != "Op #":
            raise AssertionError("Changes sheet must list applied teacher operations")
        notes = wb["Notes"]
        if notes.max_row < 3 or not any(notes.cell(row=r, column=1).value == "bonjour" for r in range(2, notes.max_row + 1)):
            raise AssertionError("Notes sheet must include outside-ranked checks and bonjour note")
        recheck = wb["À revérifier"]
        if recheck.max_row != 47 or [recheck.cell(row=1, column=c).value for c in range(1, 8)] != ["#", "Mot", "Genre", "Catégorie", "Formes", "Avis", "Correction"]:
            raise AssertionError("À revérifier must contain only 46 corrected/refilled rows and the seven required columns")
        if not recheck.data_validations.dataValidation or recheck.data_validations.dataValidation[0].sqref != "F2:F47":
            raise AssertionError("À revérifier Avis dropdown must cover the corrected/refilled rows")
        ws = wb["Mots"]
        data_rows = ws.max_row - 1
        if data_rows != 300:
            raise AssertionError("Expected 300 rows in Mots; found " + str(data_rows))
        forbidden = {"VER", "PRE", "NOM", "(shared form)"}
        bad_cells = []
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.strip() in forbidden:
                    bad_cells.append(cell.coordinate + "=" + cell.value)
        if bad_cells:
            raise AssertionError("Forbidden standalone technical values: " + ", ".join(bad_cells[:10]))
        if ws.freeze_panes != "A2":
            raise AssertionError("Mots header row is not frozen")
        if ws["G2"].value is not None or len(ws.data_validations.dataValidation) != 2:
            raise AssertionError("Expected review and register dropdowns")
    finally:
        wb.close()


def main() -> int:
    rows = read_rows()
    build_workbook(rows)
    validate_workbook()
    print("ASSERT xlsx: PASS — 300 rows; no standalone VER/PRE/NOM or (shared form) cells")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("ASSERT xlsx: FAIL — " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(1)
