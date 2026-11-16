#!/usr/bin/env bash
# Studie 1 (Fragen300) mit V20: Antworten ohne/mit RAG (qwen3.5:9b), Rang der Buchstelle (Recall@k, MRR), LLM-Richter ja/teilweise/nein
# (gemma4:12b, Bewertungsspalte 3), Faithfulness ohne/mit RAG (gemma4:12b), Bewertungsbogen nach ausgabe/.
# Umgebung aktiv, Ollama läuft:
#   bash skripte/laeufe/lauf300.sh einrichten   # Dateien und V20-Schalter prüfen, Richtermodell laden (einmal)
#   bash skripte/laeufe/lauf300.sh pilot        # 3 Fragen komplett (Buch, Rechnung, außerhalb), ca. 10 min
#   bash skripte/laeufe/lauf300.sh teil 100     # alle Schritte nur für Q1–Q100 (ca. 3 h); "alles" macht später mit Q101–Q300 weiter
#   bash skripte/laeufe/lauf300.sh zusammen     # danach: menschliche Bewertungen (Exemplar) + Lauf-Bogen -> Fragen300_komplett_*.xlsx
#   bash skripte/laeufe/lauf300.sh alles        # alle Schritte (mehrere Stunden): Antworten -> Bogen nach ausgabe/ -> Rang -> Richter -> Faithfulness -> Bogen + Zip
# Einzelschritte: antworten | rang | richter | faith | bogen. Jeder Schritt setzt nach Abbruch fort (gleicher Befehl).
cd "${RUN300_ROOT:-$(dirname "$0")/../..}" || exit 1
[ -d lernassistent ] || { echo "Ordner lernassistent fehlt"; exit 1; }
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
unset LERNASSISTENT_HG LERNASSISTENT_THINK
# V20 (eingefrorene Konfiguration)
export LERNASSISTENT_G=G-v6 LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 \
       LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=AB LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
LABEL="${RUN300_LABEL:-F300-V20}"
RICHTER="${RUN300_RICHTER:-gemma4:12b}"
GENERATOR=qwen3.5:9b
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
T=daten/testfragen
EV=skripte/evaluation
ZIEL="${RUN300_ZIEL:-ausgabe}"
mkdir -p protokolle evaluationsdaten daten/boegen "$T" "$ZIEL"
cmd="${1:?einrichten | pilot | teil N | alles | zusammen | antworten | rang | richter | faith | bogen}"
TS=$(date +%Y%m%d_%H%M)
LOG="protokolle/lauf300_${cmd}_$TS.txt"

einrichten() {
  for f in "$T/fragen300.csv" "$T/gold300.json" "$T/richter_beispiele.json" "$T/kriterien300.json" daten/boegen/Fragen300_Bewertung.xlsx; do
    [ -f "$f" ] || echo "FEHLT: $f (siehe daten/README.md)"
  done
  python - <<'PY'
import sys; sys.path.insert(0, "lernassistent")
import formelsuche as fs, rechenbaustein as rb, rag_pipeline as rp
ok = rp.SCAFFOLDING_VERSION == "G-v6" and fs.V19_A and rb.V19_B and rp.RP_V13 and rp.NACHRECHNUNG_VERSION == "RB-v8"
print(f"V20-Schalter: G={rp.SCAFFOLDING_VERSION} RP={'RP-v13' if rp.RP_V13 else rp.RECHEN_PRUEFUNG_VERSION} "
      f"RB={rp.NACHRECHNUNG_VERSION} FS={fs.FORMELSUCHE_VERSION} CTX={rp.KONTEXT_TOKENS} -> {'OK' if ok else 'FEHLER'}")
sys.exit(0 if ok else 1)
PY
  [ $? -eq 0 ] || { echo "FEHLER: V20 nicht eingespielt "; exit 1; }
  python -c "import csv;print(sum(1 for _ in csv.DictReader(open('$T/fragen300.csv',encoding='utf-8'))), 'Fragen')"
  [ -f "$KB" ] || echo "WARNUNG: $KB fehlt"
  ollama list | grep -q "$GENERATOR" || echo "WARNUNG: $GENERATOR fehlt"
  ollama list | grep -q "$RICHTER" || { echo "Richtermodell $RICHTER wird geladen (einmalig, ca. 8 GB) ..."; ollama pull "$RICHTER"; }
  ollama list | grep -E "$GENERATOR|$RICHTER"
}
antworten() { python "$EV/antworten300.py" "$1" --fragen "$2" --kb "$KB"; ollama stop "$GENERATOR" 2>/dev/null; }
rang()      { python "$EV/rang300.py" "$1" --fragen "$2" --gold "$T/gold300.json" --kb "$KB"; }
richter()   { python "$EV/richter300.py" "$1" --richter "$RICHTER" --fragen "$2" --kriterien "$T/kriterien300.json" --beispiele "$T/richter_beispiele.json"; }
faith()     { python "$EV/faith300.py" "$1" --richter "$RICHTER" --kb "$KB"; }
bogen()     { python "$EV/fuelle300.py" "$1" daten/boegen/Fragen300_Bewertung.xlsx "$ZIEL/Fragen300_Bewertung_$1.xlsx"; }
# Bewertungsexemplar: nur Antworten (ohne Richter/Faithfulness, verblindet), wird nur einmal angelegt und nie überschrieben
exemplar()  { local E="$ZIEL/Fragen300_zum_Bewerten_$1.xlsx"
              [ -f "$E" ] && { echo "Bewertungsexemplar existiert schon (unverändert): $E"; return; }
              python "$EV/fuelle300.py" "$1" daten/boegen/Fragen300_Bewertung.xlsx "$E" --nur-antworten && echo "Bewertungsexemplar: $E"; }
zippen() {
  python - "$ZIEL" "$LABEL" "$LOG" <<'PY'
import sys, zipfile, glob, os, time
ziel, label, log = sys.argv[1:4]
z = os.path.join(ziel, f"run300_{label}_rohdaten_{time.strftime('%Y%m%d_%H%M')}.zip")
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
    for p in glob.glob(f"evaluationsdaten/*300_{label}*") + [log]:
        if os.path.isfile(p): f.write(p)
print("Rohdaten:", z)
PY
}

case "$cmd" in
  einrichten) einrichten ;;
  pilot)
    python - "$T/fragen300.csv" "$T/fragen300_pilot.csv" <<'PY'
import csv, sys
r = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
p = [x for x in r if x["id"] in ("Q1", "Q3", "Q7")]
w = csv.DictWriter(open(sys.argv[2], "w", encoding="utf-8", newline=""), fieldnames=list(r[0])); w.writeheader(); w.writerows(p)
print(len(p), "Pilotfragen:", [x["id"] + " " + x["typ"] for x in p])
PY
    { L="$LABEL-PILOT"; P="$T/fragen300_pilot.csv"
      antworten "$L" "$P"; rang "$L" "$P"; richter "$L" "$P"; faith "$L"; bogen "$L"; } 2>&1 | tee -a "$LOG" ;;
  teil)
    N="${2:-100}"; F="$T/fragen300_erste$N.csv"
    python - "$T/fragen300.csv" "$F" "$N" <<'PY'
import csv, sys
r = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))[: int(sys.argv[3])]
w = csv.DictWriter(open(sys.argv[2], "w", encoding="utf-8", newline=""), fieldnames=list(r[0])); w.writeheader(); w.writerows(r)
print(len(r), "Fragen:", r[0]["id"], "bis", r[-1]["id"])
PY
    # gleiches Label wie der volle Lauf: "alles" überspringt diese Fragen später
    { echo "=== Fragen300 $LABEL, erste $N Fragen, $(date) | Richter $RICHTER"
      antworten "$LABEL" "$F"; exemplar "$LABEL"
      rang "$LABEL" "$F"
      richter "$LABEL" "$F"; bogen "$LABEL"
      faith "$LABEL"; bogen "$LABEL"
      echo "=== fertig $(date)"; } 2>&1 | tee -a "$LOG"
    zippen ;;
  antworten) antworten "$LABEL" "$T/fragen300.csv" 2>&1 | tee -a "$LOG" ;;
  rang)      rang "$LABEL" "$T/fragen300.csv" 2>&1 | tee -a "$LOG" ;;
  richter)   richter "$LABEL" "$T/fragen300.csv" 2>&1 | tee -a "$LOG" ;;
  faith)     faith "$LABEL" 2>&1 | tee -a "$LOG" ;;
  bogen)     bogen "$LABEL" 2>&1 | tee -a "$LOG" ;;
  zusammen)  python "$EV/zusammen300.py" "$ZIEL/Fragen300_zum_Bewerten_$LABEL.xlsx" "$ZIEL/Fragen300_Bewertung_$LABEL.xlsx" \
               "$ZIEL/Fragen300_komplett_${LABEL}_${TS}.xlsx" 2>&1 | tee -a "$LOG" ;;
  alles)
    { echo "=== Fragen300 $LABEL $(date) | Richter $RICHTER"
      antworten "$LABEL" "$T/fragen300.csv"; exemplar "$LABEL"
      rang "$LABEL" "$T/fragen300.csv"
      richter "$LABEL" "$T/fragen300.csv"; bogen "$LABEL"
      faith "$LABEL"; bogen "$LABEL"
      echo "=== fertig $(date)"; } 2>&1 | tee -a "$LOG"
    zippen ;;
  *) echo "unbekannt: $cmd"; exit 1 ;;
esac
