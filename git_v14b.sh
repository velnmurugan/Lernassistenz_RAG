#!/usr/bin/env bash
# Git V14b (nimmt V13.5 mit, falls noch nicht committet). Kein push. Start aus ~/RAG:  bash git_v14b.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py lernassistent/rechenbaustein.py \
  skripte/evaluation/teste_v135_offline.py skripte/evaluation/daten_v135_rv_v134.json skripte/evaluation/teste_v14_offline.py \
  skripte/evaluation/teste_rechen_varianten.py skripte/evaluation/nachtlauf_v14.sh git_v14b.sh daten/testfragen/n100_rechnung_v1.csv skripte/evaluation/kurzlauf_v14.sh skripte/werkzeuge/bereinige_namen.py 2>/dev/null
git commit -m "V14b: Rechenweg mit Python (RW-v1/RW-v2 Werkzeugaufruf, RW-v3 Platzhalter), Namensbereinigung; enthält V13.5 (RP-v11, RB-v6)" || echo "nichts zu committen"
for t in v13.5 v14; do git tag -l $t | grep -q . && echo "Marke $t existiert schon" || true; done
git tag -l v13.5 | grep -q . || echo "Hinweis: v13.5 nie getaggt – V13.5 steckt in diesem Commit."
git tag -a v14 -m "V14" 2>/dev/null || true
git log --oneline | head -3
