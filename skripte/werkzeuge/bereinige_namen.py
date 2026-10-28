"""Entfernt den Namen des KI-Assistenten aus allen Text-Dateien des Projekts (Programme, Skripte, Doku, Auswertungen).
Ersetzungen: Doku-Verweise "<ordner>/Name.md" ohne Ordner-Präfix, Bewertungsvermerke -> "KI" bzw. "AI assistant".
Ohne Option nur Anzeige (Probelauf); mit --anwenden wird geändert, je Datei eine Sicherung *.vor_namen.
Start (aus ~/RAG):  python skripte/werkzeuge/bereinige_namen.py            (zeigt, was sich ändert)
                    python skripte/werkzeuge/bereinige_namen.py --anwenden (ändert)"""
import re
import shutil
import sys
from pathlib import Path

N = "".join(map(chr, (67, 108, 97, 117, 100, 101)))  # der Name, ohne ihn im Quelltext auszuschreiben
ENDUNGEN = {".py", ".sh", ".md", ".txt", ".csv", ".json", ".jsx", ".html", ".yml", ".yaml", ".toml", ".cfg", ".ini"}
AUSLASSEN = {".git", "__pycache__", "cache", "wissensbasen", "node_modules", ".ipynb_checkpoints"}
REGELN_CODE = [
    (re.compile(rf"\b{N.lower()}/(?=[\w-]+\.md)"), ""),
    (re.compile(rf"\b{N}[- ]Vorbewertung"), "Vorbewertung"),
    (re.compile(rf"\(\s*{N}\s*\)"), "(KI)"),
    (re.compile(rf"\b(?:von|durch) {N}\b"), "vom KI-Assistenten"),
    (re.compile(rf"\b{N}\b"), "KI-Assistent"),
]
REGELN_TEXT = [
    (re.compile(rf"\b{N.lower()}/(?=[\w-]+\.md)"), ""),
    (re.compile(rf"\b{N}[- ]Vorbewertung"), "Vorbewertung"),
    (re.compile(rf"\bthe AI assistant \({N}\)"), "the AI assistant"),
    (re.compile(rf"\(\s*{N}\s*\)"), "(AI)"),
    (re.compile(rf"\bby {N}\b"), "by the AI assistant"),
    (re.compile(rf"\b{N}\b"), "AI assistant"),
]
REST = re.compile(N, re.I)


def dateien(wurzel):
    for p in wurzel.rglob("*"):
        if (p.is_file() and not (set(p.parts) & AUSLASSEN) and ".vor_namen" not in p.name
                and (p.suffix.lower() in ENDUNGEN or ".vor_" in p.name)):
            yield p


def main():
    anwenden = "--anwenden" in sys.argv
    wurzel = Path.cwd()
    geaendert, rest = 0, []
    for p in dateien(wurzel):
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not REST.search(t):
            continue
        regeln = REGELN_CODE if p.suffix in (".py", ".sh") or ".py.vor_" in p.name or ".sh.vor_" in p.name else REGELN_TEXT
        neu = t
        for muster, ersatz in regeln:
            neu = muster.sub(ersatz, neu)
        n = len(REST.findall(t)) - len(REST.findall(neu))
        print(f"{'geändert' if anwenden else 'würde ändern'}: {p.relative_to(wurzel)} ({n} Stellen)")
        if REST.search(neu):
            rest.append(str(p.relative_to(wurzel)))
        if anwenden and neu != t:
            s = p.with_name(p.name + ".vor_namen")
            if not s.exists():
                shutil.copy2(p, s)
            p.write_text(neu, encoding="utf-8")
            geaendert += 1
    # Excel-Dateien (Spaltenköpfe, Zellen), falls openpyxl vorhanden
    try:
        import openpyxl
        for p in [q for q in wurzel.rglob("*.xlsx") if not (set(q.parts) & AUSLASSEN) and ".vor_namen" not in q.name]:
            wb = openpyxl.load_workbook(p)
            n = 0
            for ws in wb.worksheets:
                for zeile in ws.iter_rows():
                    for z in zeile:
                        if isinstance(z.value, str) and REST.search(z.value):
                            v = z.value
                            for muster, ersatz in REGELN_TEXT:
                                v = muster.sub(ersatz, v)
                            z.value, n = v, n + 1
            if n:
                print(f"{'geändert' if anwenden else 'würde ändern'}: {p.relative_to(wurzel)} ({n} Zellen)")
                if anwenden:
                    shutil.copy2(p, p.with_name(p.name + ".vor_namen.xlsx"))
                    wb.save(p)
    except ImportError:
        print("Hinweis: openpyxl fehlt, Excel-Dateien nicht geprüft")
    print(f"\n{'Geändert' if anwenden else 'Probelauf'}: {geaendert} Dateien. Mit Restfundstellen (bitte melden): {rest or 'keine'}")
    if not anwenden:
        print("Zum Ändern:  python skripte/werkzeuge/bereinige_namen.py --anwenden")
    else:
        print("Sicherungen *.vor_namen enthalten noch den alten Text; nach Prüfung löschen:  find . -name '*.vor_namen*' -delete")


if __name__ == "__main__":
    main()
