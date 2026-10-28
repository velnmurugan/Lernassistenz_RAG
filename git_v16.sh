#!/usr/bin/env bash
# Git V16 (nimmt V15, V14b–V14d und V13.5 mit, falls noch nicht committet). Kein push. Start aus ~/RAG:  bash git_v16.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py lernassistent/rechenbaustein.py \
  skripte/evaluation/teste_v135_offline.py skripte/evaluation/daten_v135_rv_v134.json skripte/evaluation/teste_v14_offline.py \
  skripte/evaluation/teste_v15_offline.py skripte/evaluation/daten_v15_rb.json skripte/evaluation/rb7_nachrechnen.py \
  skripte/evaluation/teste_v16_offline.py skripte/evaluation/daten_v16.json skripte/evaluation/lauf_n100_rag.py \
  skripte/evaluation/vergleiche_rechenlaeufe.py skripte/evaluation/nachtlauf_v16.sh skripte/evaluation/kurzlauf_v15.sh \
  skripte/evaluation/teste_rechen_varianten.py skripte/evaluation/nachtlauf_v14.sh skripte/evaluation/werkzeug_diagnose.py \
  skripte/werkzeuge/bereinige_namen.py daten/testfragen/n100_rechnung_v1.csv daten/testfragen/rechen_varianten_v2.csv git_v16.sh 2>/dev/null
git commit -m "V16: RP-v12 (Bestätigung mit Retry, Kopfsatz + weiteres Ergebnis, Antwort ohne Ergebnis) + RB-v7 (Einheiten umrechnen); RV-v2 (neue Zahlen); enthält V15, V14b–V14d, V13.5" || echo "nichts zu committen"
for t in v14 v15; do git tag -l $t | grep -q . || git tag -a $t -m "${t^^}"; done
git tag -a v16 -m "V16" 2>/dev/null || echo "Marke v16 existiert schon"
git log --oneline | head -3
