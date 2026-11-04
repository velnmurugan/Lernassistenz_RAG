#!/usr/bin/env bash
# Eval300: 300 gemischte Fragen (N100 + NEU100 + Fragenset v4) mit und ohne RAG beantworten (qwen3.5:9b, V11B)
# und von einem zweiten Modell (Standard qwen3.5:4b) bewerten lassen. Aus ~/RAG, Umgebung pilot_rag, Ollama läuft.
#
#   cd ~/RAG && bash ~/eval300/eval300_lauf.sh einrichten   # Skripte + Fragen kopieren, Modelle prüfen (1 min)
#   bash skripte/laeufe/eval300_lauf.sh pilot                # 6 Fragen komplett (Antworten + Richter), Zeit prüfen (ca. 10 min)
#   bash skripte/laeufe/eval300_lauf.sh antworten            # 300 Fragen ohne und mit RAG (ca. 4-5 h)
#   bash skripte/laeufe/eval300_lauf.sh richter              # Richter auf alle 600 Antworten (ca. 1-1,5 h)
#   bash skripte/laeufe/eval300_lauf.sh auswertung           # Zusammenfassung + Bewertungsbogen
#   bash skripte/laeufe/eval300_lauf.sh alles                # EIN BEFEHL ÜBER NACHT: antworten, richter, auswertung, Zip nach Downloads
# Jeder Schritt setzt nach Abbruch fort (gleicher Befehl). Andere Modelle: EVAL300_RICHTER=<tag>, LERNASSISTENT_MODELL=<tag>.
cd "${EVAL300_ROOT:-$PWD}" || exit 1
[ -d lernassistent ] || { echo "Bitte aus ~/RAG starten (Ordner lernassistent fehlt)"; exit 1; }
PAKET="${EVAL300_PAKET:-$(cd "$(dirname "$0")" && pwd)}"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
# V11B (eingefroren): G-v4, RP-v5, Formelsuche aus, Hinweis-Wächter aus
export LERNASSISTENT_G=G-v4 LERNASSISTENT_RP=RP-v5 LERNASSISTENT_FS=aus; unset LERNASSISTENT_HG
LABEL="${EVAL300_LABEL:-EVAL300-V11B}"
RICHTER="${EVAL300_RICHTER:-qwen3.5:4b}"
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
FRAGEN=daten/testfragen/fragen_eval300.csv
ZIEL="${EVAL300_ZIEL:-/mnt/c/Users/Vel Narayanasamy/Downloads}"
EV=skripte/evaluation
mkdir -p protokolle evaluationsdaten
cmd="${1:?einrichten | pilot | antworten | richter | auswertung | alles}"
TS=$(date +%Y%m%d_%H%M)

einrichten() {
  for f in eval300_antworten.py eval300_richter.py eval300_auswertung.py vergleiche_bewertungen.py; do
    [ -f "$PAKET/$f" ] || { echo "fehlt im Paket: $PAKET/$f"; exit 1; }
    cp "$PAKET/$f" "$EV/" ; done
  mkdir -p skripte/laeufe daten/testfragen
  cp "$PAKET/eval300_lauf.sh" skripte/laeufe/eval300_lauf.sh
  cp "$PAKET/daten/fragen_eval300.csv" "$FRAGEN"
  cp "$PAKET"/daten/testfragen_v4*.csv daten/testfragen/ 2>/dev/null
  echo "Skripte nach $EV, Fragen nach $FRAGEN ($(($(wc -l < "$FRAGEN")-1)) Zeilen inkl. Mehrzeilern)"
  [ -f "$KB" ] && echo "KB ok: $KB ($(sha256sum "$KB" | cut -c1-12), erwartet c2742e8c278f)" || echo "WARNUNG: $KB fehlt"
  ollama list | grep -E "qwen3.5:9b|$RICHTER" || echo "WARNUNG: Modelle nicht gefunden (ollama pull qwen3.5:9b / ollama pull $RICHTER)"
  python - <<'PY'
import csv
r=list(csv.DictReader(open("daten/testfragen/fragen_eval300.csv",encoding="utf-8")))
import collections; print(len(r),"Fragen", dict(collections.Counter(x["satz"] for x in r)))
PY
}
antworten() { python "$EV/eval300_antworten.py" "$1" --kb "$KB" --fragen "$FRAGEN" --retrieval hybrid_kg_rr "${@:2}"; }
richter()   { python "$EV/eval300_richter.py" "$1" --richter "$RICHTER" "${@:2}"; }
auswertung(){ python "$EV/eval300_auswertung.py" "$1"; }

case "$cmd" in
  einrichten) einrichten ;;
  pilot)
    echo "=== Pilot: 6 Fragen $(date +%H:%M)"; ollama ps
    antworten "${LABEL}-PILOT" --limit 6 && richter "${LABEL}-PILOT" && auswertung "${LABEL}-PILOT"
    echo "=== Pilot fertig $(date +%H:%M)" ;;
  antworten)  antworten "$LABEL" 2>&1 | tee -a "protokolle/eval300_antworten_$TS.txt" ;;
  richter)    richter "$LABEL" 2>&1 | tee -a "protokolle/eval300_richter_$TS.txt" ;;
  auswertung) auswertung "$LABEL" ;;
  alles)
    LOG="protokolle/eval300_alles_$TS.txt"
    { echo "=== Eval300 alles $(date)"; echo "Generator ${LERNASSISTENT_MODELL:-qwen3.5:9b}, Richter $RICHTER, Label $LABEL"; } | tee -a "$LOG"
    antworten "$LABEL" 2>&1 | tee -a "$LOG"
    richter "$LABEL" 2>&1 | tee -a "$LOG"
    auswertung "$LABEL" 2>&1 | tee -a "$LOG"
    python - "$ZIEL" "$LABEL" "$LOG" <<'PY'
import sys, zipfile, glob, os, time
ziel, label, log = sys.argv[1:4]
os.makedirs(ziel, exist_ok=True)
z = os.path.join(ziel, f"eval300_ergebnisse_{time.strftime('%Y%m%d')}.zip")
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
    for p in glob.glob(f"evaluationsdaten/eval300_*{label}*") + [log, "daten/testfragen/fragen_eval300.csv"]:
        if os.path.isfile(p): f.write(p)
print("Zip:", z)
PY
    echo "=== fertig $(date)" | tee -a "$LOG" ;;
  *) echo "unbekannt: $cmd"; exit 1 ;;
esac
