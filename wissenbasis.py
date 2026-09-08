"""
baue_wissensbasis.py
---------------------
Erzeugt knowledge_base.json aus echten PDF-Dateien.

WICHTIG: Dieses Skript läuft NICHT innerhalb der Streamlit-App und wird
NICHT von Proband:innen ausgeführt. Es ist ein einmaliges Vorbereitungs-
werkzeug für die Forscherin/den Forscher, um aus echten curricularen PDFs
eine feste, für alle Teilnehmenden identische Wissensbasis zu erzeugen
(siehe Design_Entscheidungen_Literatur.md, Punkt 4).

Themenerkennung (siehe rag_pipeline.lese_pdf_gliederung):
    - Enthält eine PDF eine eingebettete Gliederung (Bookmarks/TOC) -- bei
      Fachbüchern aus wissenschaftlichen Verlagen praktisch immer der Fall
      -- wird jeder Chunk automatisch seinem tatsächlichen Kapitel/
      Abschnitt zugeordnet.
    - Nur wenn KEINE Gliederung gefunden wird, dient der Dateiname als
      einheitliches Thema für die gesamte Datei (Fallback).

Verwendung:
    1. PDF-Datei(en) in den Ordner 'quellmaterial/' legen.
    2. python baue_wissensbasis.py
    3. Ergebnis: knowledge_base.json (überschreibt eine vorhandene Datei
       nach Bestätigung).
"""

import json
from pathlib import Path

from rag_pipeline import verarbeite_pdf_seitenweise

QUELLORDNER = Path("quellmaterial")
ZIEL_DATEI = Path("knowledge_base.json")
# Automatische, inhaltsbasierte Chunk-Grenzen statt fester Satzanzahl
# (siehe Design_Entscheidungen_Literatur.md, Punkt 11). MAX_SAETZE_PRO_CHUNK
# wirkt hier nur noch als Sicherheitsobergrenze, nicht als Zielgröße.
CHUNKING_METHODE = "semantisch"  # oder "fest" für die einfachere Alternative
AEHNLICHKEITS_SCHWELLE = 0.55
MAX_SAETZE_PRO_CHUNK = 8
UEBERLAPP_SAETZE = 1  # siehe Design_Entscheidungen_Literatur.md, Punkt 14 (Modran 2025)


def dateiname_zu_thema(pfad):
    """'SPS_Grundlagen.pdf' -> 'SPS Grundlagen' (nur als Fallback genutzt,
    wenn die PDF keine eigene Gliederung enthält)"""
    return pfad.stem.replace("_", " ").replace("-", " ").strip()


def main():
    if not QUELLORDNER.exists():
        QUELLORDNER.mkdir()
        print(f"Ordner '{QUELLORDNER}/' wurde erstellt. Bitte PDF-Dateien dort ablegen und erneut ausführen.")
        return

    pdf_dateien = sorted(QUELLORDNER.glob("*.pdf"))
    if not pdf_dateien:
        print(f"Keine PDF-Dateien in '{QUELLORDNER}/' gefunden. Bitte PDFs dort ablegen.")
        return

    if ZIEL_DATEI.exists():
        antwort = input(f"'{ZIEL_DATEI}' existiert bereits und wird überschrieben. Fortfahren? (j/n): ")
        if antwort.strip().lower() not in ("j", "ja", "y", "yes"):
            print("Abgebrochen.")
            return

    alle_chunks = []
    chunk_zaehler = 0

    print(f"Verarbeite {len(pdf_dateien)} PDF-Datei(en) aus '{QUELLORDNER}/':\n")

    for pdf_pfad in pdf_dateien:
        fallback_thema = dateiname_zu_thema(pdf_pfad)
        print(f"  📄 {pdf_pfad.name}")

        try:
            seiten_chunks, anzahl_seiten, gliederung, hat_gliederung = verarbeite_pdf_seitenweise(
                pdf_pfad, max_saetze_pro_chunk=MAX_SAETZE_PRO_CHUNK, fallback_thema=fallback_thema,
                methode=CHUNKING_METHODE, aehnlichkeits_schwelle=AEHNLICHKEITS_SCHWELLE,
                ueberlapp_saetze=UEBERLAPP_SAETZE,
            )
        except Exception as e:
            print(f"     ⚠️  Fehler beim Lesen: {e} — Datei wird übersprungen.")
            continue

        if not seiten_chunks:
            print(f"     ⚠️  Kein Text extrahiert (evtl. gescanntes PDF ohne OCR) — Datei wird übersprungen.")
            continue

        for sc in seiten_chunks:
            chunk_zaehler += 1
            alle_chunks.append({
                "id": f"pdf_{chunk_zaehler:04d}",
                "thema": sc["thema"],
                "text": sc["text"],
                "quelle_datei": pdf_pfad.name,
                "seite": sc["seite"],
            })

        if hat_gliederung:
            anzahl_themen = len(set(c["thema"] for c in seiten_chunks))
            print(f"     ✅ {anzahl_seiten} Seite(n), {len(seiten_chunks)} Chunks, "
                  f"{anzahl_themen} Kapitel/Abschnitte automatisch erkannt")
            for titel, seite in gliederung[:10]:
                print(f"        - {titel} (ab Seite {seite})")
            if len(gliederung) > 10:
                print(f"        ... und {len(gliederung) - 10} weitere")
        else:
            print(f"     ℹ️  {anzahl_seiten} Seite(n), {len(seiten_chunks)} Chunks. "
                  f"Keine PDF-Gliederung gefunden — einheitliches Thema '{fallback_thema}' verwendet.")

    if not alle_chunks:
        print("\nKeine verwertbaren Chunks erzeugt. knowledge_base.json wurde NICHT geschrieben.")
        return

    ausgabe = {
        "_hinweis": (
            "Automatisch aus echten PDF-Quellen erzeugt via baue_wissensbasis.py. "
            "Themen aus PDF-Gliederung (Bookmarks) wo vorhanden, sonst aus Dateinamen. "
            "Quelldatei und Seite siehe 'quelle_datei'/'seite'-Feld pro Chunk."
        ),
        "chunks": alle_chunks,
    }

    with open(ZIEL_DATEI, "w", encoding="utf-8") as f:
        json.dump(ausgabe, f, ensure_ascii=False, indent=2)

    themen = sorted(set(c["thema"] for c in alle_chunks))
    print(f"\n✅ '{ZIEL_DATEI}' geschrieben: {len(alle_chunks)} Chunks aus {len(pdf_dateien)} PDF(s)")
    print(f"   {len(themen)} Themen/Kapitel insgesamt: {', '.join(themen[:15])}{', ...' if len(themen) > 15 else ''}")


if __name__ == "__main__":
    main()