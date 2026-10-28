#!/usr/bin/env bash
# Git V18c. Kein push. Start aus ~/RAG:  bash git_v18c.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rechenbaustein.py lernassistent/rechenpruefung.py skripte/evaluation/teste_v18_offline.py skripte/evaluation/daten_v18.json skripte/evaluation/kurzlauf_v18c.sh git_v18c.sh 2>/dev/null
git commit -m "V18c: Nachrechnung A (Schreibweise), B (Formelbeleg, Standard aus), D (Zahlen in RECHNUNG belegt), E (ERGEBNIS-Name); K (Hochzahl einer Einheit); Schalter LERNASSISTENT_V18" || echo "nichts zu committen"
git tag -a v18c -m "V18c" 2>/dev/null || echo "Marke v18c existiert schon"
git log --oneline | head -3
