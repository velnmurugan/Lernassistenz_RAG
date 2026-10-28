#!/usr/bin/env bash
# Git V17. Kein push. Start aus ~/RAG:  bash git_v17.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenbaustein.py lernassistent/dimensionspruefung.py skripte/evaluation/teste_v17_offline.py \
  skripte/evaluation/daten_v17.json skripte/evaluation/kurzlauf_v17.sh git_v17.sh 2>/dev/null
git commit -m "V17b: RB-v8 (Dimensionsprüfung der Nachrechnung, pi-Konstante, keine doppelte Umrechnung) + RP-v13 (Vergleich in Grundeinheiten)" || echo "nichts zu committen"
git tag -a v17 -m "V17" 2>/dev/null || echo "Marke v17 existiert schon"
git log --oneline | head -3
