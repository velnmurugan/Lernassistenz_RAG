#!/usr/bin/env bash
# Git V13.1 (kein push). Start aus ~/RAG nach Einspielen + Offline-Tests:  bash git_v131.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py app.py skripte/evaluation/teste_v131_offline.py skripte/evaluation/nachtlauf_v131.sh git_v131.sh
git commit -m "V13.1: RP-v7 (Tokenizer-Korrekturen, Bereinigung mitten im Satz, Kopfsatz-Angleichung), RB-v4 (RB-v2-Prompt zuerst, RB-v3 als Retry)" || echo "nichts zu committen"
git tag -a v13.1 -m "V13.1 Kandidat (N100-Lauf V131)" 2>/dev/null || echo "Marke v13.1 existiert schon"
git log --oneline | head -3
