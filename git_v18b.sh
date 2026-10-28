#!/usr/bin/env bash
# Git V18b. Kein push. Start aus ~/RAG:  bash git_v18b.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rechenbaustein.py skripte/evaluation/teste_v18_offline.py skripte/evaluation/daten_v18.json skripte/evaluation/kurzlauf_v18b.sh git_v18b.sh 2>/dev/null
git commit -m "V18b: Nachrechnung A (Schreibweise), B (Formelbeleg, Standard aus), D (Zahlen in RECHNUNG belegt), E (ERGEBNIS-Name); Schalter LERNASSISTENT_V18" || echo "nichts zu committen"
git tag -a v18b -m "V18b" 2>/dev/null || echo "Marke v18b existiert schon"
git log --oneline | head -3
