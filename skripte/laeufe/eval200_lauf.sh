#!/usr/bin/env bash
# Antworten ohne und mit RAG für die Bewertungsbögen (200 Fragen N100 + NEU100, optional 100 Fragen V4).
# Mit RAG: Stand V20 (G-v6, RP-v13, RB-v8, FS-v3, V18=ADEK, V19=AB, CTX 8192). Ohne RAG: Prompt O-v1. qwen3.5:9b, T = 0, seed 42.
# Aus ~/RAG starten, Umgebung pilot_rag aktiv, Ollama läuft:
#   bash ~/eval200/eval200_lauf.sh einrichten   # Fragen kopieren, Stand prüfen (1 min)
#   bash ~/eval200/eval200_lauf.sh q200          # 200 Fragen ohne + mit RAG (ca. 5-6 h), danach Bogen mit Antworten nach Downloads
#   bash ~/eval200/eval200_lauf.sh v4            # optional: 100 Fragen V4 (ca. 3 h)
# Nach Abbruch denselben Befehl erneut starten: bereits beantwortete Fragen werden übersprungen.
cd "${EVAL200_ROOT:-$PWD}" || exit 1
[ -d lernassistent ] || { echo "Bitte aus ~/RAG starten (Ordner lernassistent fehlt)"; exit 1; }
PAKET="$(cd "$(dirname "$0")" && pwd)"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
unset LERNASSISTENT_HG LERNASSISTENT_THINK
export LERNASSISTENT_G=G-v6 LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 \
       LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=AB LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
ZIEL="${EVAL200_ZIEL:-/mnt/c/Users/Vel Narayanasamy/Downloads}"
EV=skripte/evaluation
mkdir -p protokolle evaluationsdaten daten/testfragen daten/boegen
cmd="${1:?einrichten | q200 | v4}"
TS=$(date +%Y%m%d_%H%M)

einrichten() {
  [ -f "$EV/eval300_antworten.py" ] || { echo "FEHLER: $EV/eval300_antworten.py fehlt (Eval300 nicht eingerichtet)"; exit 1; }
  grep -q "V20 (G-v6)" lernassistent/rag_pipeline.py || { echo "FEHLER: G-v6 fehlt – erst: bash ~/v20/v20_lauf.sh einrichten"; exit 1; }
  cp "$PAKET"/daten/fragen_q200.csv "$PAKET"/daten/fragen_v4_100.csv daten/testfragen/
  cp "$PAKET"/daten/Bewertung_200_N100_NEU100.xlsx "$PAKET"/daten/Bewertung_100_V4.xlsx daten/boegen/
  cp "$PAKET/fuelle_excel.py" "$EV/"
  python - <<'PY'
import sys; sys.path.insert(0, "lernassistent")
import formelsuche as fs, rechenbaustein as rb, rag_pipeline as rp
ok = rp.SCAFFOLDING_VERSION == "G-v6" and fs.V19_A and rb.V19_B and rp.RP_V13 and rp.NACHRECHNUNG_VERSION == "RB-v8"
print(f"Schalter: G={rp.SCAFFOLDING_VERSION} RP={'RP-v13' if rp.RP_V13 else rp.RECHEN_PRUEFUNG_VERSION} RB={rp.NACHRECHNUNG_VERSION} "
      f"FS={fs.FORMELSUCHE_VERSION} V19_A={fs.V19_A} V19_B={rb.V19_B} CTX={rp.KONTEXT_TOKENS} -> {'OK' if ok else 'FEHLER'}")
sys.exit(0 if ok else 1)
PY
  [ $? -eq 0 ] || exit 1
  python -c "import csv;[print(f, sum(1 for _ in csv.DictReader(open('daten/testfragen/'+f,encoding='utf-8'))), 'Fragen') for f in ('fragen_q200.csv','fragen_v4_100.csv')]"
  ollama list | grep -q "qwen3.5:9b" || echo "WARNUNG: qwen3.5:9b nicht gefunden"
}
lauf() {  # $1 Label, $2 Fragen, $3 Vorlage, $4 Ausgabename
  local label=$1 fragen=$2 vorlage=$3 aus=$4 LOG="protokolle/eval200_${1}_$TS.txt"
  { echo "=== $label $(date) | G=$LERNASSISTENT_G RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB FS=$LERNASSISTENT_FS V18=$LERNASSISTENT_V18 V19=$LERNASSISTENT_V19 CTX=$LERNASSISTENT_CTX"
    ollama ps
    python "$EV/eval300_antworten.py" "$label" --kb "$KB" --fragen "$fragen" --retrieval hybrid_kg_rr --nur beide
    echo "=== fertig $(date)"; } 2>&1 | tee -a "$LOG"
  echo "G=$LERNASSISTENT_G RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB FS=$LERNASSISTENT_FS V18=$LERNASSISTENT_V18 V19=$LERNASSISTENT_V19 CTX=$LERNASSISTENT_CTX" \
    >> "evaluationsdaten/eval300_antworten_${label}_konfig.txt"
  mkdir -p "$ZIEL"
  python "$EV/fuelle_excel.py" "evaluationsdaten/eval300_antworten_${label}.csv" "$vorlage" "$ZIEL/$aus" | tee -a "$LOG"
  python - "$ZIEL" "$label" "$LOG" <<'PY'
import sys, zipfile, glob, os, time
ziel, label, log = sys.argv[1:4]
z = os.path.join(ziel, f"{label}_rohdaten_{time.strftime('%Y%m%d_%H%M')}.zip")
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
    for p in glob.glob(f"evaluationsdaten/eval300_antworten_{label}*") + [log]:
        if os.path.isfile(p): f.write(p)
print("Rohdaten:", z)
PY
}
case "$cmd" in
  einrichten) einrichten ;;
  q200) [ -f daten/testfragen/fragen_q200.csv ] || { echo "erst: einrichten"; exit 1; }
        lauf EVAL200-V20 daten/testfragen/fragen_q200.csv daten/boegen/Bewertung_200_N100_NEU100.xlsx Bewertung_200_N100_NEU100_mit_Antworten.xlsx ;;
  v4)   [ -f daten/testfragen/fragen_v4_100.csv ] || { echo "erst: einrichten"; exit 1; }
        lauf EVAL100V4-V20 daten/testfragen/fragen_v4_100.csv daten/boegen/Bewertung_100_V4.xlsx Bewertung_100_V4_mit_Antworten.xlsx ;;
  *) echo "unbekannt: $cmd"; exit 1 ;;
esac
