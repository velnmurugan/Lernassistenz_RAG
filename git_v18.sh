#!/usr/bin/env bash
# Git V18. Kein push. Start aus ~/RAG:  bash git_v18.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rechenbaustein.py skripte/evaluation/teste_v18_offline.py skripte/evaluation/kurzlauf_v18.sh git_v18.sh 2>/dev/null
git commit -m "V18: A strengere Schreibweise der Bestätigung, B Formelbeleg bei Kürzung und kurzen Formeln (Schalter LERNASSISTENT_V18)" || echo "nichts zu committen"
git tag -a v18 -m "V18" 2>/dev/null || echo "Marke v18 existiert schon"
git log --oneline | head -3
