#!/usr/bin/env bash
# Git V14c (nimmt V13.5/V14b mit, falls noch nicht committet). Kein push. Start aus ~/RAG:  bash git_v14c.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py lernassistent/rechenbaustein.py \
  skripte/evaluation/teste_v135_offline.py skripte/evaluation/daten_v135_rv_v134.json skripte/evaluation/teste_v14_offline.py \
  skripte/evaluation/teste_rechen_varianten.py skripte/evaluation/nachtlauf_v14.sh skripte/evaluation/kurzlauf_v14c.sh \
  skripte/evaluation/werkzeug_diagnose.py skripte/werkzeuge/bereinige_namen.py daten/testfragen/n100_rechnung_v1.csv git_v14c.sh 2>/dev/null
git commit -m "V14c: RW-v4 (gegebene Größen als Platzhalter, Startwerte aus der Frage, Rohtext protokolliert); enthält V14b und V13.5" || echo "nichts zu committen"
git tag -l v14 | grep -q . || git tag -a v14 -m "V14"
git tag -a v14c -m "V14c" 2>/dev/null || echo "Marke v14c existiert schon"
git log --oneline | head -3
