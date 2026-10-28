#!/usr/bin/env bash
# Git V19a. Kein push. Start aus ~/RAG:  bash git_v19a.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/formelsuche.py lernassistent/rag_pipeline.py skripte/evaluation/teste_v19_offline.py skripte/evaluation/diagnose_formel_retrieval.py skripte/evaluation/diagnose_formelsuche_varianten.py skripte/evaluation/kurzlauf_v19a.sh git_v19a.sh 2>/dev/null
git commit -m "V19a: Formelsuche vorab (Lösungsweg -> Suchbegriffe -> billige Suche -> kleiner Cross-Encoder, 2 Formel-Chunks); Schalter LERNASSISTENT_V19=A; Diagnose-Skripte" || echo "nichts zu committen"
git tag -a v19a -m "V19a" 2>/dev/null || echo "Marke v19a existiert schon"
git log --oneline | head -3
