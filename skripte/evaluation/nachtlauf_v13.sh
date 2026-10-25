#!/usr/bin/env bash
# V13 Nachtlauf auf N100: Test offline -> Lauf A (RP-v6/RB-v3, Prompt G-v4) -> Lauf B (zusätzlich G-v5). Vordergrund, mit tee, kein nohup.
# Start (aus ~/RAG, Umgebung pilot_rag, nur Ollama laeuft):
#   bash skripte/evaluation/nachtlauf_v13.sh 2>&1 | tee protokolle/nachtlauf_v13_$(date +%Y%m%d_%H%M).txt
# Nur ein Lauf: ONLY=A oder ONLY=B.  Dauer je Lauf ca. 2 h (ohne RAGAS).
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
echo "=== Offline-Tests $(date +%H:%M) ==="
for t in teste_v13_offline teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do
  python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen, siehe protokolle/$t.txt"; exit 1; }
done
export OHNE_RAGAS=1
if [ "${ONLY:-AB}" != "B" ]; then
  echo; echo "=== Lauf A: RP-v6 + RB-v3, G-v4 $(date +%H:%M) ==="
  LERNASSISTENT_RP=RP-v6 LERNASSISTENT_G=G-v4 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V13A
fi
if [ "${ONLY:-AB}" != "A" ]; then
  echo; echo "=== Lauf B: RP-v6 + RB-v3, G-v5 $(date +%H:%M) ==="
  LERNASSISTENT_RP=RP-v6 LERNASSISTENT_G=G-v5 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V13B
fi
echo; echo "=== Vergleich $(date +%H:%M) ==="
python skripte/evaluation/vergleiche_n100_laeufe.py V11B V13A V13B
echo "=== fertig $(date +%H:%M) ==="
