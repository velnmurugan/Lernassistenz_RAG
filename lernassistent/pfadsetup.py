"""
pfadsetup.py
------------
Wird von jedem Skript und jeder App als Erstes importiert (zwei Zeilen am Dateianfang,
eingefügt von ordne_projekt.py). Sorgt dafür, dass

  1. die Bibliothek (lernassistent/) und alle Skript-Ordner importierbar sind
     (z. B. importiert ideen_feedback.py die Funktion ist_modell_verweigerung aus
     skripte/evaluation/ragas_auswertung.py), ohne Imports umzuschreiben;
  2. das Arbeitsverzeichnis immer der Projektordner ist, damit relative Pfade wie
     "evaluationsdaten/", "cache/" und "daten/..." unabhängig vom Startort stimmen.
"""
import os
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

for ordner in [WURZEL / "lernassistent", WURZEL, *sorted((WURZEL / "skripte").glob("*/"))]:
    if ordner.is_dir() and str(ordner) not in sys.path:
        sys.path.append(str(ordner))

os.chdir(WURZEL)
