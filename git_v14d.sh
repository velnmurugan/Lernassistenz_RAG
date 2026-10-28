#!/usr/bin/env bash
# Git V14d (nimmt V13.5/V14b mit, falls noch nicht committet). Kein push. Start aus ~/RAG:  bash git_v14d.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py lernassistent/rechenbaustein.py \
  skripte/evaluation/teste_v135_offline.py skripte/evaluation/daten_v135_rv_v134.json skripte/evaluation/teste_v14_offline.py \
  skripte/evaluation/teste_rechen_varianten.py skripte/evaluation/nachtlauf_v14.sh skripte/evaluation/kurzlauf_v14d.sh \
  skripte/evaluation/werkzeug_diagnose.py skripte/werkzeuge/bereinige_namen.py daten/testfragen/n100_rechnung_v1.csv git_v14d.sh 2>/dev/null
git commit -m "V14d: RW-v5 (Grundeinheiten, „[[Name]] = Ausdruck“ und „[[Ausdruck]]“, Startwerte nur mit Grundeinheit, nie Klammern anzeigen); enthält V14c, V14b, V13.5" || echo "nichts zu committen"
git tag -l v14 | grep -q . || git tag -a v14 -m "V14"; git tag -l v14c | grep -q . || true
git tag -a v14d -m "V14d" 2>/dev/null || echo "Marke v14d existiert schon"
git log --oneline | head -3
