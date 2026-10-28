#!/usr/bin/env bash
# Git V13.4 (nimmt V13.3.1 mit, falls noch nicht committet). Kein push. Start aus ~/RAG nach Einspielen + Offline-Test:  bash git_v134.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py lernassistent/rechenbaustein.py lernassistent/formelsuche.py app.py \
  skripte/evaluation/teste_v13*_offline.py skripte/evaluation/diagnose_buchergebnisse.py skripte/evaluation/teste_rechen_varianten.py \
  daten/testfragen/rechen_varianten_v1.csv skripte/evaluation/nachtlauf_v13*.sh git_v13*.sh 2>/dev/null
git commit -m "V13.4: RP-v10 (Wurzel-/Halbausdruck-Fix, Aufgabennummern, bestätigte Nachrechnung ohne Buchformel, kein kopf_korrigiert mit Buchwerten, Denkmodus liest LaTeX), RB-v5 (Kettenzeilen, NFKC, LaTeX, Prozent, Grad), Buchergebnisse aus dem Material; RV-Testset" || echo "nichts zu committen"
git tag -l v13.3 | grep -q . || echo "Hinweis: Marke v13.3 fehlt (git_v133.sh nie gelaufen) – V13.3.1 steckt in diesem Commit."
git tag -a v13.4 -m "V13.4" 2>/dev/null || echo "Marke v13.4 existiert schon"
git log --oneline | head -3
