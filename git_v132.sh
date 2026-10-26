#!/usr/bin/env bash
# Git V13.2 (enthält V13.1). Kein push. Start aus ~/RAG nach Einspielen + Offline-Tests:  bash git_v132.sh
cd "$(dirname "$0")" || exit 1
git add lernassistent/rag_pipeline.py lernassistent/rechenpruefung.py lernassistent/formelsuche.py app.py skripte/evaluation/teste_v131_offline.py \
  skripte/evaluation/teste_v132_offline.py skripte/evaluation/nachtlauf_v132.sh git_v132.sh
git commit -m "V13.1+V13.2: RP-v7/RB-v4, KB v7r als App-Standard; RP-v8 + FS-v3 (Übernahme-Befund, Formelsuche bei Übernahme, Bestätigung vor Ersetzen, Kopf ohne Häkchen)" || echo "nichts zu committen"
git tag -a v13.1 -m "V13.1 (RP-v7, RB-v4, KB v7r)" 2>/dev/null || true
git tag -a v13.2 -m "V13.2 (RP-v8)" 2>/dev/null || echo "Marke v13.2 existiert schon"
git log --oneline | head -3
