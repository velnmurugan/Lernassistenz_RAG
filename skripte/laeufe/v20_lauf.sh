#!/usr/bin/env bash
# V20: die 18 Rechenfragen aus Fragenset V4 (Eval300) NUR MIT RAG, zwei Arme, gleiche Fragen, gleiche KB, T = 0:
#   V19B = aktueller Rechenstand (RP-v13, RB-v8, V18=ADEK, FS-v3, V19=AB, G-v5, CTX 8192)  – bisher nie auf V4 gelaufen
#   V20  = V19B + G-v6 (neue Lösungsregeln L8: rechnen, wenn alle Werte in der Frage stehen; L9: jede Teilfrage)
# Vergleichsbasis ohne neuen Lauf: Eval300-V11B (eingefroren, schon bewertet).
# Aus ~/RAG starten, Umgebung pilot_rag aktiv, Ollama läuft:
#   bash ~/v20/v20_lauf.sh einrichten   # Patch G-v6 (mit Sicherung), Offline-Test, Fragendatei V4 (1 min)
#   bash ~/v20/v20_lauf.sh pilot        # 3 Rechenfragen in beiden Armen (ca. 15 min)
#   bash ~/v20/v20_lauf.sh lauf         # 18 Rechenfragen x 2 Arme (ca. 1-1,5 h), danach Zip nach Downloads
# Jeder Schritt setzt nach Abbruch fort (gleicher Befehl).
cd "${V20_ROOT:-$PWD}" || exit 1
[ -d lernassistent ] || { echo "Bitte aus ~/RAG starten (Ordner lernassistent fehlt)"; exit 1; }
PAKET="$(cd "$(dirname "$0")" && pwd)"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
unset LERNASSISTENT_HG LERNASSISTENT_THINK
# gemeinsamer Rechenstand beider Arme (wie nachtlauf_v19b.sh, Arm AB)
export LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=AB \
       LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
ALLE=daten/testfragen/fragen_eval300.csv
V4=daten/testfragen/fragen_eval300_v4_rechnung.csv
ZIEL="${V20_ZIEL:-/mnt/c/Users/Vel Narayanasamy/Downloads}"
EV=skripte/evaluation
mkdir -p protokolle evaluationsdaten
cmd="${1:?einrichten | pilot | lauf}"
TS=$(date +%Y%m%d_%H%M)

einrichten() {
  [ -f "$EV/eval300_antworten.py" ] || { echo "FEHLER: $EV/eval300_antworten.py fehlt (Eval300 nicht eingerichtet)"; exit 1; }
  [ -f "$ALLE" ] || { echo "FEHLER: $ALLE fehlt"; exit 1; }
  grep -q "V19_A" lernassistent/formelsuche.py && grep -q "V19_B" lernassistent/rechenbaustein.py \
    || { echo "FEHLER: Stand ohne V19 (formelsuche/rechenbaustein) – erst V19b/V19c einspielen"; exit 1; }
  python "$PAKET/patch_v20.py" lernassistent/rag_pipeline.py || exit 1
  cp "$PAKET/teste_v20_offline.py" "$EV/"
  (cd lernassistent && timeout 600 python "../$EV/teste_v20_offline.py" .) | tee "protokolle/teste_v20_offline.txt" | tail -2
  grep -q "7/7 bestanden" protokolle/teste_v20_offline.txt || { echo "FEHLER: Offline-Test nicht bestanden"; exit 1; }
  python - "$ALLE" "$V4" <<'PY'
import csv, sys, collections
r = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
v = [x for x in r if x["satz"] == "V4" and x["typ"] == "rechnung"]
with open(sys.argv[2], "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(r[0].keys())); w.writeheader(); w.writerows(v)
print(len(v), "V4-Rechenfragen ->", sys.argv[2], dict(collections.Counter(x["typ"] for x in v)))
PY
  for g in G-v5 G-v6; do
    LERNASSISTENT_G=$g python - <<'PY'
import sys; sys.path.insert(0, "lernassistent")
import formelsuche as fs, rechenbaustein as rb, rag_pipeline as rp
ok = fs.V19_A and rb.V19_B and rp.RP_V13 and rp.NACHRECHNUNG_VERSION == "RB-v8"
print(f"Schalter-Kontrolle: G={rp.SCAFFOLDING_VERSION} RP={"RP-v13" if rp.RP_V13 else rp.RECHEN_PRUEFUNG_VERSION} RB={rp.NACHRECHNUNG_VERSION} "
      f"FS={fs.FORMELSUCHE_VERSION} V19_A={fs.V19_A} V19_B={rb.V19_B} CTX={rp.KONTEXT_TOKENS} -> {'OK' if ok else 'FEHLER'}")
sys.exit(0 if ok else 1)
PY
    [ $? -eq 0 ] || exit 1
  done
  ollama list | grep -q "qwen3.5:9b" || echo "WARNUNG: qwen3.5:9b nicht gefunden"
}
arm() {  # $1 = G-Version, $2 = Label, weitere Argumente an eval300_antworten.py
  local g=$1 label=$2; shift 2
  echo "=== $label (G=$g RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB FS=$LERNASSISTENT_FS V18=$LERNASSISTENT_V18 V19=$LERNASSISTENT_V19 CTX=$LERNASSISTENT_CTX) $(date +%H:%M) ==="
  LERNASSISTENT_G=$g python "$EV/eval300_antworten.py" "$label" --kb "$KB" --fragen "$V4" --retrieval hybrid_kg_rr --nur mit "$@"
  echo "G=$g RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB FS=$LERNASSISTENT_FS V18=$LERNASSISTENT_V18 V19=$LERNASSISTENT_V19 CTX=$LERNASSISTENT_CTX" \
    >> "evaluationsdaten/eval300_antworten_${label}_konfig.txt"
}
pilotfragen() {  # 3 Rechenfragen: E047 (V11B richtig), E084 (Rechenfehler), E055 (Teilverweigerung)
  python - "$V4" <<'PY'
import csv, sys
r = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
p = [x for x in r if x["id"] in ("E047", "E084", "E055")]
with open("daten/testfragen/fragen_v20_pilot.csv", "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(r[0].keys())); w.writeheader(); w.writerows(p)
print(len(p), "Pilotfragen")
PY
}
zippen() {
  python - "$ZIEL" "$@" <<'PY'
import sys, zipfile, glob, os, time
ziel = sys.argv[1]; os.makedirs(ziel, exist_ok=True)
z = os.path.join(ziel, f"v20_ergebnisse_{time.strftime('%Y%m%d_%H%M')}.zip")
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
    for p in glob.glob("evaluationsdaten/eval300_antworten_EVAL300-V4-*") + sys.argv[2:] + ["protokolle/teste_v20_offline.txt"]:
        if os.path.isfile(p): f.write(p)
print("Zip:", z)
PY
}

case "$cmd" in
  einrichten) einrichten ;;
  pilot)
    [ -f "$V4" ] || { echo "erst: einrichten"; exit 1; }
    pilotfragen; ollama ps
    V4=daten/testfragen/fragen_v20_pilot.csv
    LOG="protokolle/v20_pilot_$TS.txt"
    { arm G-v5 EVAL300-V4-V19B-PILOT; arm G-v6 EVAL300-V4-V20-PILOT; } 2>&1 | tee -a "$LOG"
    python - <<'PY'
import csv
for l in ("V19B", "V20"):
    for r in csv.DictReader(open(f"evaluationsdaten/eval300_antworten_EVAL300-V4-{l}-PILOT.csv", encoding="utf-8")):
        print(f"\n[{l} {r['id']}] {r['sek_mit']} s {r['status_mit']} | {r['rechen_pruefung_mit']}\n{r['antwort_mit'][:500]}")
PY
    zippen "$LOG" ;;
  lauf)
    [ -f "$V4" ] || { echo "erst: einrichten"; exit 1; }
    LOG="protokolle/v20_lauf_$TS.txt"
    { echo "=== V20 Lauf $(date)"; ollama ps; arm G-v5 EVAL300-V4-V19B; arm G-v6 EVAL300-V4-V20; echo "=== fertig $(date)"; } 2>&1 | tee -a "$LOG"
    zippen "$LOG" ;;
  *) echo "unbekannt: $cmd"; exit 1 ;;
esac
