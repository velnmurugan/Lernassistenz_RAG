"""Entfernt den Namen des KI-Assistenten aus allen Text-Dateien des Projekts (Programme, Skripte, Doku,
Auswertungen, Sicherungskopien *.vor_*) und streicht Bewertervermerke ("pre-rated by ...", "one rater (...)").
Version 2 (ersetzt die erste Fassung). Nur Python-Standardbibliothek; openpyxl optional (Excel-Zellen).

Ohne Option nur Probelauf (zeigt, was sich ändert); mit --anwenden wird geändert, je Datei eine Sicherung
*.vor_namen. Laufzeit: unter 1 Minute.

Start (aus ~/RAG):  python skripte/werkzeuge/bereinige_namen.py            (Probelauf)
                    python skripte/werkzeuge/bereinige_namen.py --anwenden (ändert)

Ersetzungen (in dieser Reihenfolge):
  1. Doku-Verweise "<ordner>/Name.md"  ->  "doku/Name.md"
  2. Bewertervermerke: "pre-ratings by X" -> "pre-ratings", "(X, one rater" -> "(one rater", "one rater (X)" -> "one rater"
  3. Feste Wendungen mit Namen (Schreibweise, Hinweistexte)
  4. Rest-Fund: einzelner Name -> "KI-Assistent" (Code) bzw. "AI assistant" (Text); jede solche Stelle wird
     mit Zeile ausgegeben, damit sie geprüft werden kann.
"""
import re
import shutil
import sys
from pathlib import Path

N = "".join(map(chr, (67, 108, 97, 117, 100, 101)))  # der Name, ohne ihn im Quelltext auszuschreiben
ENDUNGEN = {".py", ".sh", ".md", ".txt", ".csv", ".json", ".jsx", ".html", ".yml", ".yaml", ".toml", ".cfg", ".ini"}
AUSLASSEN = {".git", "__pycache__", "cache", "wissensbasen", "node_modules", ".ipynb_checkpoints"}
MAX_BYTES = 30 * 1024 * 1024

FESTE_REGELN = [
    (re.compile(rf"\b{N.lower()}/(?=[\w-]+\.md)"), "doku/"),
    (re.compile(rf"\b{N}[- ]Vorbewertung"), "Vorbewertung"),
    (re.compile(rf"Vorbewertung(en)? (?:von|durch) {N}\b"), r"Vorbewertung\1"),
    (re.compile(rf"\bpre-ratings by {N}\b"), "pre-ratings"),
    (re.compile(rf"\bpre-rated by {N}\b"), "pre-rated"),
    (re.compile(rf"\(\s*{N},\s*"), "("),
    (re.compile(rf"\bone rater \(\s*{N}\s*\)"), "one rater"),
    (re.compile(rf"drafted by the AI assistant \(\s*{N}\s*\) from those chunks"),
     "created from those chunks and checked and approved by me"),
    (re.compile(rf"\bthe AI assistant \(\s*{N}\s*\)"), "the AI assistant"),
    (re.compile(rf"\b{N} checked the extracted images against"), "the extracted images were checked against"),
    (re.compile(rf"\bhat {N} entworfen"), "wurden vorab entworfen"),
    (re.compile(rf"\(\s*{N} sieht die Wissensbasis(\s+)nicht, nur diese Stichprobe\)"),
     r"(die Wissensbasis ist\1nicht einsehbar, nur diese Stichprobe)"),
    (re.compile(rf"Browser, {N} und"), "Browser und"),
    (re.compile(rf"bitte an {N} schicken"), "bitte weitergeben"),
    (re.compile(rf"\s*\(\s*{N}\s*\)"), ""),
]
REST = re.compile(N, re.I)
REST_WORT = re.compile(rf"\b{N}\b")


def ist_code(p):
    n = p.name
    return p.suffix in (".py", ".sh") or ".py.vor_" in n or ".sh.vor_" in n or n.endswith((".py.bak", ".py.orig"))


def bereinige(text, code):
    for muster, ersatz in FESTE_REGELN:
        text = muster.sub(ersatz, text)
    treffer = []
    if REST.search(text):
        ers = "KI-Assistent" if code else "AI assistant"
        for i, zeile in enumerate(text.split("\n"), 1):
            if REST.search(zeile):
                treffer.append((i, zeile.strip()[:160]))
        text = REST_WORT.sub(ers, text)
        text = re.sub(rf"(?i){N}", ers, text)  # z.B. in Bezeichnern/Pfaden ohne Wortgrenze
    return text, treffer


def dateien(wurzel):
    for p in wurzel.rglob("*"):
        if (p.is_file() and not (set(p.parts) & AUSLASSEN) and ".vor_namen" not in p.name
                and p.stat().st_size <= MAX_BYTES
                and (p.suffix.lower() in ENDUNGEN or ".vor_" in p.name or p.name.endswith((".bak", ".orig")))):
            yield p


def main():
    anwenden = "--anwenden" in sys.argv
    sicherung = "--ohne-sicherung" not in sys.argv
    wurzel = Path.cwd()
    geaendert, rest = 0, []
    for p in dateien(wurzel):
        try:
            t = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not REST.search(t):
            continue
        neu, treffer = bereinige(t, ist_code(p))
        n = len(REST.findall(t)) - len(REST.findall(neu))
        print(f"{'geändert' if anwenden else 'würde ändern'}: {p.relative_to(wurzel)} ({n} Stellen)")
        for i, z in treffer:
            rest.append((str(p.relative_to(wurzel)), i, z))
        if anwenden and neu != t:
            s = p.with_name(p.name + ".vor_namen")
            if sicherung and not s.exists():
                shutil.copy2(p, s)
            p.write_text(neu, encoding="utf-8")
            geaendert += 1
    try:
        import openpyxl
        for p in [q for q in wurzel.rglob("*.xlsx") if not (set(q.parts) & AUSLASSEN) and ".vor_namen" not in q.name]:
            wb = openpyxl.load_workbook(p)
            n = 0
            for ws in wb.worksheets:
                for zeile in ws.iter_rows():
                    for z in zeile:
                        if isinstance(z.value, str) and REST.search(z.value):
                            z.value, n = bereinige(z.value, False)[0], n + 1
            if n:
                print(f"{'geändert' if anwenden else 'würde ändern'}: {p.relative_to(wurzel)} ({n} Zellen)")
                if anwenden:
                    if sicherung:
                        shutil.copy2(p, p.with_name(p.name + ".vor_namen.xlsx"))
                    wb.save(p)
    except ImportError:
        print("Hinweis: openpyxl fehlt, Excel-Dateien nicht geprüft")
    print("\nStellen ohne feste Regel (mit Standardersatz; bitte lesen, ob der Satz noch passt):")
    for f, i, z in rest:
        print(f"  {f}:{i}: {z}")
    if not rest:
        print("  keine")
    print(f"\n{'Geändert' if anwenden else 'Probelauf'}: {geaendert} Dateien.")
    if not anwenden:
        print("Zum Ändern:  python skripte/werkzeuge/bereinige_namen.py --anwenden")
    else:
        print("Danach prüfen:  grep -rIil -e " + N.lower() + " . --exclude='*.vor_namen*' --exclude-dir=.git")
        if sicherung:
            print("Sicherungen *.vor_namen enthalten noch den alten Text; nach Prüfung löschen:  find . -name '*.vor_namen*' -delete")
        print("Git: geänderte Dateien committen. Frühere Commits enthalten den Namen weiterhin im Verlauf.")


if __name__ == "__main__":
    main()
