"""
entferne_register.py
--------------------
Entfernt Inhaltsverzeichnis- und Sachwortverzeichnis-Chunks aus einer Wissensbasis (Böge, MinerU).
Sie haben keinen Lerninhalt, hängen wegen fehlender Überschriften am letzten Kapitel (falsche Quellenangabe)
und stören die Suche (Seitenzahlen als Rauschen).

Regel (dokumentunabhängig, nur Seitenränder): Ein Chunk wird entfernt, wenn
  (a) sein Text mit "Inhaltsverzeichnis" beginnt oder "Inhaltsverzeichnis" in den ersten 8 Wörtern steht, oder
  (b) er in den ersten RAND_VORN oder letzten RAND_HINTEN Seiten liegt, nicht mit "Tabelle"/"Abbildung" beginnt
      UND Zahlen > 25 % der Wörter ausmachen
      UND kaum Rechenzeichen enthält (kein "=", "√", "·" usw.).
Es wird nichts überschrieben: Ausgabe ist eine neue Datei; die entfernten Chunks stehen in <ausgabe>.entfernt.csv
zur Kontrolle.

Start:
  python skripte/wissensbasis/entferne_register.py daten/wissensbasen/knowledge_base_boege_v7b.json \
      daten/wissensbasen/knowledge_base_boege_v7b_ohne_register.json
"""
import csv
import json
import re
import sys

RAND_VORN = 30
RAND_HINTEN = 60
ZAHLENANTEIL = 0.25
_RECHENZEICHEN = re.compile(r"[=√·×÷∑∫±≈≤≥]")


def ist_register(chunk, max_seite):
    text = chunk["text"]
    woerter = text.split()
    if not woerter:
        return "leer"
    if "inhaltsverzeichnis" in " ".join(woerter[:8]).lower():
        return "inhaltsverzeichnis"
    if text.startswith(("Tabelle", "Abbildung")):  # Tabellen-/Bildchunks sind nie Verzeichnisse
        return ""
    seite = chunk.get("seite") or 0
    am_rand = seite <= RAND_VORN or seite > max_seite - RAND_HINTEN
    zahlen = len(re.findall(r"\b\d{1,4}\b", text)) / len(woerter)
    if am_rand and zahlen > ZAHLENANTEIL and not _RECHENZEICHEN.search(text):
        return "verzeichnis"
    return ""


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    eingabe, ausgabe = sys.argv[1:]
    with open(eingabe, encoding="utf-8") as f:
        daten = json.load(f)
    chunks = daten["chunks"]
    max_seite = max((c.get("seite") or 0) for c in chunks)
    behalten, entfernt = [], []
    for c in chunks:
        grund = ist_register(c, max_seite)
        (entfernt if grund else behalten).append((c, grund))
    daten["chunks"] = [c for c, _ in behalten]
    daten["register_entfernt"] = len(entfernt)
    with open(ausgabe, "w", encoding="utf-8") as f:
        json.dump(daten, f, ensure_ascii=False)
    with open(ausgabe + ".entfernt.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "seite", "grund", "woerter", "anfang"])
        for c, g in entfernt:
            w.writerow([c["id"], c.get("seite"), g, len(c["text"].split()), c["text"][:80].replace("\n", " ")])
    print(f"{len(chunks)} Chunks -> {len(behalten)} behalten, {len(entfernt)} entfernt (max. Seite {max_seite})")
    seiten = sorted({c.get("seite") for c, _ in entfernt if c.get("seite")})
    if seiten:
        print(f"entfernte Seiten: {seiten[0]}–{seiten[-1]}, {len(seiten)} verschiedene; Liste: {ausgabe}.entfernt.csv")


if __name__ == "__main__":
    main()
