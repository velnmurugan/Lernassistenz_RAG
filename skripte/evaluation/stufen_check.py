"""
stufen_check.py
---------------
Automatische Prüfung der Stufen-Texte (Scaffolding-Spezifikation §6/§7) für eine
oder mehrere Versionen, ohne LLM:
  - Format: Hinweis geparst?
  - H3: verweist der Hinweis auf Material, das Lernende nicht sehen ("Kontext", "im Text",
    "Tabelle", "Abbildung", "Diagramm", "nachschlagen", "schau dir … an" …; rag_pipeline.MATERIAL_VERWEIS)?
  - dasselbe für die Rückmeldungen auf "Deine Idee?" (ideen_feedback.csv derselben Sitzung)
  - ab V8: Ergebnis der Hinweis-Prüfung je Antwort (ok / nachgebessert / ersetzt); die H3-Zählung
    bezieht sich dann auf den GEZEIGTEN Hinweis, der ursprüngliche steht in hinweis_original
  - X3: Anrede du / Sie (Regex-Heuristik)
  - H1 (Teil): verrät der Hinweis eine Zahl aus der Lösung, die nicht in der Frage steht?
  - Länge (Wörter) von Hinweis / Erklärung / Lösung (Median)
Verratene Begriffe (H1) bleiben menschliche Bewertung.

Start:
  python stufen_check.py V3-RR V4-S2 V5-S2H
Liest evaluationsdaten/archiv/<VERSION>/interaktionen.csv, sonst
evaluationsdaten/interaktionen.csv (gefiltert nach Sitzungs-ID).
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import csv
import re
import statistics
import sys
from pathlib import Path

EVAL = Path("evaluationsdaten")
import rag_pipeline as rp

H3 = rp.MATERIAL_VERWEIS  # ab 14 Oct 2026 gemeinsam mit App/Erklärseite; erweitert um Abbildung, Diagramm, nachschlagen …
DU = re.compile(r"\b(du|dir|dich|dein\w*)\b")
ZAHL = re.compile(r"\d+(?:[.,]\d+)?")
SIE = re.compile(r"(?<![.!?]\s)(?<!^)\b(Sie|Ihnen|Ihr\w*)\b")


def lade(version):
    pfad = EVAL / "archiv" / version / "interaktionen.csv"
    if not pfad.exists():
        pfad = EVAL / "interaktionen.csv"
    with open(pfad, encoding="utf-8") as f:
        return [z for z in csv.DictReader(f) if z["sitzungs_id"] == version]


def lade_feedback(version):
    pfad = EVAL / "archiv" / version / "ideen_feedback.csv"
    if not pfad.exists():
        pfad = EVAL / "ideen_feedback.csv"
    if not pfad.exists():
        return []
    with open(pfad, encoding="utf-8") as f:
        return [z for z in csv.DictReader(f) if z.get("sitzungs_id") == version]


def zahlen(t):
    return {z.replace(",", ".") for z in ZAHL.findall(t or "")}


def zahlen_leck(z):
    """Zahlen im Hinweis, die in der Lösung, aber nicht in der Frage stehen (wie leck_zahlen in ideen_feedback.py)."""
    return (zahlen(z["hinweis"]) & zahlen(z["loesung"])) - zahlen(z["frage"])


def woerter(t):
    return len(t.split())


def main(versionen):
    for v in versionen:
        zeilen = lade(v)
        if not zeilen:
            print(f"{v}: keine Zeilen gefunden"); continue
        geparst = [z for z in zeilen if z["hinweis"].strip()]
        h3 = [i + 1 for i, z in enumerate(zeilen) if z["hinweis"].strip() and H3.search(z["hinweis"])]
        leck = [i + 1 for i, z in enumerate(zeilen) if z["hinweis"].strip() and zahlen_leck(z)]
        du = sie = 0
        for z in geparst:
            t = " ".join([z["hinweis"], z["erklaerung"], z["loesung"]])
            du += bool(DU.search(t)); sie += bool(SIE.search(t))
        med = lambda feld: statistics.median([woerter(z[feld]) for z in geparst]) if geparst else 0
        print(f"\n=== {v} ({len(zeilen)} Antworten) ===")
        print(f"Format geparst:            {len(geparst)}/{len(zeilen)}")
        print(f"Hinweis verweist auf Text: {len(h3)}/{len(geparst)}  (Fall-Nr.: {h3})")
        print(f"Hinweis verrät Zahl (H1):  {len(leck)}/{len(geparst)}  (Fall-Nr.: {leck})")
        print(f"Anrede du / Sie:           {du} / {sie}")
        print(f"Median Wörter H / E / L:   {med('hinweis')} / {med('erklaerung')} / {med('loesung')}")
        hp = [z.get("hinweis_pruefung", "") for z in zeilen if z.get("hinweis_pruefung")]
        if hp:
            from collections import Counter
            print(f"Hinweis-Prüfung (HP):      {dict(Counter(hp))}")
        fb = lade_feedback(v)
        if fb:
            fb_verweis = [z for z in fb if H3.search(z.get("rueckmeldung", ""))]
            print(f"Rückmeldung verweist auf Material: {len(fb_verweis)}/{len(fb)}  "
                  f"(Prompt {', '.join(sorted({z.get('prompt_version', '?') for z in fb}))})")
            fp = [z.get("feedback_pruefung", "") for z in fb if z.get("feedback_pruefung")]
            if fp:
                from collections import Counter
                print(f"Rückmeldungs-Prüfung (FP): {dict(Counter(fp))}")
            mit_neuen = [z for z in fb if z.get("neue_zahlen")]
            if any("neue_zahlen" in z for z in fb):
                print(f"Rückmeldung mit neuen Zahlen: {len(mit_neuen)}/{len(fb)}  (ab IF-v4 protokolliert)")


if __name__ == "__main__":
    main(sys.argv[1:] or ["V3-RR"])
