#!/usr/bin/env bash
# Git V15 (nimmt V14b–V14d und V13.5 mit, falls noch nicht committet). Kein push. Start aus ~/RAG:  bash git_v15.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py lernassistent/rechenbaustein.py \
  skripte/evaluation/teste_v135_offline.py skripte/evaluation/daten_v135_rv_v134.json skripte/evaluation/teste_v14_offline.py \
  skripte/evaluation/teste_v15_offline.py skripte/evaluation/daten_v15_rb.json skripte/evaluation/rb7_nachrechnen.py \
  skripte/evaluation/teste_rechen_varianten.py skripte/evaluation/nachtlauf_v14.sh skripte/evaluation/kurzlauf_v15.sh \
  skripte/evaluation/werkzeug_diagnose.py skripte/werkzeuge/bereinige_namen.py daten/testfragen/n100_rechnung_v1.csv git_v15.sh 2>/dev/null
git commit -m "V15: RB-v7 (Nachrechnung rechnet Einheiten in Grundeinheiten um); enthält V14b–V14d (Rechenweg RW-v1..v5, abgeschaltet) und V13.5" || echo "nichts zu committen"
git tag -l v14 | grep -q . || git tag -a v14 -m "V14"
git tag -a v15 -m "V15" 2>/dev/null || echo "Marke v15 existiert schon"
git log --oneline | head -3
