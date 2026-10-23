#!/usr/bin/env bash
# Held-out-Test mit den 100 neuen, ungetunten Fragen (70 Fischer + 30 Böge) auf EINER Version.
# Start (im Projektordner, Umgebung pilot_rag aktiv), Beispiel für den Stand von ~/RAG (V10a):
#   bash skripte/laeufe/n100_lauf.sh V10A 2>&1 | tee protokolle/n100_V10A_$(date +%Y%m%d_%H%M).txt
# Der Lauf setzt nach Abbruch fort (bereits protokollierte Fragen je Sitzungs-ID werden übersprungen).
# Dauer grob 40 s je Frage: Fischer 70 Fragen ca. 50 min, Böge 30 Fragen ca. 20 min.
LABEL="${1:?Versionskennung angeben, z. B. V10A}"
cd "$(dirname "$0")/../.." || exit 1
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
RET="--retrieval hybrid_kg_rr --rrf-k 5"
KB_F=daten/wissensbasen/knowledge_base_fischer_v7c.json
F_ROH=daten/testfragen/testfragen_fischer_v2.csv
F_CHUNKS=daten/testfragen/testfragen_fischer_v2_chunks.csv
B_FRAGEN=daten/testfragen/testfragen_boege_v2.csv
STATUS=()
schritt() { echo; echo "=================== $(date +%H:%M) $1 ==================="; }
merke() { if [ "$2" -eq 0 ]; then STATUS+=("OK     $1"); else STATUS+=("FEHLER $1"); fi; }

schritt "0 Version dieses Codes"
python - <<'PY'
import sys; sys.path.insert(0, "lernassistent")
import rag_pipeline as r
for n in ("SCAFFOLDING_VERSION", "HINWEIS_PRUEFUNG_VERSION", "RECHEN_PRUEFUNG_VERSION"):
    print(n, getattr(r, n, "-"))
PY

schritt "1 Chunk-Zuordnung Fischer (Anker -> chunk_id)"
if [ -f "$F_CHUNKS" ]; then echo "schon vorhanden: $F_CHUNKS"; else
  python skripte/wissensbasis/ordne_chunks_zu.py "$F_ROH" "$KB_F" "$F_CHUNKS" | tail -15
fi
merke "Zuordnung Fischer" $?

schritt "2 Generierung N100F-$LABEL (Fischer, 70 Fragen)"
python skripte/evaluation/fuehre_testfragen_aus.py "N100F-$LABEL" $RET --kb "$KB_F" --fragen "$F_CHUNKS"
merke "Generierung N100F-$LABEL" $?

if [ -f "$B_FRAGEN" ]; then
  schritt "3 Generierung N100B-$LABEL (Böge, 30 Fragen)"
  python skripte/evaluation/fuehre_testfragen_aus.py "N100B-$LABEL" $RET --fragen "$B_FRAGEN"
  merke "Generierung N100B-$LABEL" $?
else
  echo "(Böge-Fragen $B_FRAGEN noch nicht da – Schritt 3 übersprungen)"
fi

schritt "Übersicht"
printf '%s\n' "${STATUS[@]}"
ls -1 evaluationsdaten/testlauf_retrieval_N100*-"$LABEL".csv 2>/dev/null
