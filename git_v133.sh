#!/usr/bin/env bash
# Git V13.3 (enthält V13.1, V13.2). Kein push. Start aus ~/RAG nach Einspielen + Offline-Tests:  bash git_v133.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py lernassistent/formelsuche.py app.py \
  skripte/evaluation/teste_v131_offline.py skripte/evaluation/teste_v132_offline.py skripte/evaluation/teste_v133_offline.py \
  skripte/evaluation/nachtlauf_v133.sh git_v133.sh
git commit -m "V13.3: RP-v9 (Denkmodus-Wiederholung, strenge Bestätigung), LERNASSISTENT_CTX; enthält V13.1 (RP-v7, KB v7r) und V13.2 (RP-v8, FS-v3)" || echo "nichts zu committen"
for t in v13.1 v13.2 v13.3; do git tag -a $t -m "$t" 2>/dev/null || echo "Marke $t existiert schon"; done
git log --oneline | head -3
