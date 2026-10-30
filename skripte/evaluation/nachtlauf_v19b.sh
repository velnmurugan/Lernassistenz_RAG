#!/usr/bin/env bash
# V19b Lauf auf den vollständigen Rechensätzen (nur RAG, Vordergrund, kein nohup).
# Sätze (alle Entwicklungsdaten, keine unabhängige Prüfung): RV-v1 (22), N100-Rechnen (22), RV-v2 (21).
# Arme:  AB  = V19a (Formelsuche vorab) + V19b (Parser-Korrekturen)      aus = ohne V19 (Basis im selben Stand)
# Aufruf (aus ~/RAG):   bash skripte/evaluation/nachtlauf_v19b.sh [AB|aus|beide]   (Standard: beide, ca. 5–6 h)
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle evaluationsdaten
WAHL=${1:-beide}
export PYTHONUNBUFFERED=1 LERNASSISTENT_G=G-v5 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
echo "=== Offline-Tests $(date +%H:%M) ==="
for m in "" A AB; do
  LERNASSISTENT_V19=$m timeout 300 python skripte/evaluation/teste_v19_offline.py > "protokolle/teste_v19_offline_${m:-aus}.txt" 2>&1; rc=$?
  echo "teste_v19_offline ${m:-aus}: $(tail -1 protokolle/teste_v19_offline_${m:-aus}.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: teste_v19_offline ${m:-aus} fehlgeschlagen"; exit 1; }
done
TB=$(find . -maxdepth 2 -name teste_v19b_offline.py | head -1)
if [ -n "$TB" ]; then
  (cd "$(dirname "$TB")" && python teste_v19b_offline.py) > protokolle/teste_v19b_offline.txt 2>&1; rc=$?
  echo "teste_v19b_offline: $(tail -1 protokolle/teste_v19b_offline.txt) (rc=$rc)"; [ $rc -eq 0 ] || { echo "ABBRUCH: teste_v19b_offline"; exit 1; }
fi
for t in teste_v18_offline teste_v17_offline teste_v16_offline teste_v15_offline teste_v14_offline; do
  arg=""; [ $t = teste_v18_offline ] && arg=ADEK
  LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=AB timeout 300 python skripte/evaluation/$t.py $arg > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"
  [ $rc -eq 0 ] || { echo "ABBRUCH: $t fehlgeschlagen (rc=$rc), siehe protokolle/$t.txt"; exit 1; }
done
# Schalter-Kontrolle: kommt "AB" wirklich im Programm an? (Fehler im ersten Versuch: das Skript hatte V19=A fest eingestellt)
pruefe_schalter () {  # $1 = Wert von LERNASSISTENT_V19, $2 = erwartet (1/0)
  LERNASSISTENT_V19="$1" python - "$2" <<'PY'
import sys, os
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "lernassistent")]
import rechenbaustein as rb, formelsuche as fs
soll = sys.argv[1] == "1"
ok = (bool(rb.V19_B) == soll) and (bool(fs.V19_A) == soll)
print("Schalter-Kontrolle V19=%r: V19_A=%s V19_B=%s -> %s" % (os.environ.get("LERNASSISTENT_V19"), fs.V19_A, rb.V19_B, "OK" if ok else "FEHLER"))
sys.exit(0 if ok else 1)
PY
}
pruefe_schalter AB 1 && pruefe_schalter "" 0 || { echo "ABBRUCH: Schalter V19 wirkt nicht wie erwartet (rechenbaustein.py ohne V19b?)"; exit 1; }
RV1=daten/testfragen/rechen_varianten_v1.csv; N1R=daten/testfragen/n100_rechnung_v1.csv; RV2=daten/testfragen/rechen_varianten_v2.csv
arm () {  # $1 = AB | aus
  local M="$1" V19 ETI
  [ "$M" = "aus" ] && V19="" || V19="$M"
  ETI=$([ "$M" = "aus" ] && echo "V19aus" || echo "V19b")
  export LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=$V19
  for par in "RV1-$ETI:$RV1" "N100R-$ETI:$N1R" "RV2-$ETI:$RV2"; do
    local L="${par%%:*}" F="${par#*:}"
    echo; echo "=== $L (RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB V18=$LERNASSISTENT_V18 V19=${LERNASSISTENT_V19:-aus}) $(date +%H:%M) ==="
    rm -f "evaluationsdaten/rechen_varianten_$L.csv"
    python skripte/evaluation/teste_rechen_varianten.py "$L" --fragen "$F" 2>&1 | tee "protokolle/rechen_varianten_$L.txt"
  done
}
[ "$WAHL" = "aus" ] || arm AB
[ "$WAHL" = "AB" ] || arm aus
echo; echo "=== Vergleich $(date +%H:%M) ==="
python - <<'PY' 2>&1 | tee protokolle/vergleich_v19b.txt
import csv, os
csv.field_size_limit(10**9)
def lade(p):
    return {r["nr"]: r for r in csv.DictReader(open(p, encoding="utf-8"))} if os.path.exists(p) else {}
print("Satz   Frage  AB(ja/nein, Status)          aus(ja/nein, Status)         Antwort gleich")
tot = {"AB": 0, "aus": 0}; n = {}
for satz in ("RV1", "N100R", "RV2"):
    a = lade(f"evaluationsdaten/rechen_varianten_{satz}-V19b.csv"); b = lade(f"evaluationsdaten/rechen_varianten_{satz}-V19aus.csv")
    for k in sorted(set(a) | set(b), key=lambda x: (x[0], int(''.join(c for c in x if c.isdigit()) or 0))):
        ra, rb_ = a.get(k), b.get(k)
        sa = f"{ra['richtig']:<4} {ra['rechen_pruefung']}" if ra else "-"; sb = f"{rb_['richtig']:<4} {rb_['rechen_pruefung']}" if rb_ else "-"
        gl = "ja" if ra and rb_ and ra["loesung"] == rb_["loesung"] else ("-" if not (ra and rb_) else "NEIN")
        print(f"{satz:<6} {k:<6} {sa:<28} {sb:<28} {gl}")
        if ra: tot["AB"] += ra["richtig"] == "ja"
        if rb_: tot["aus"] += rb_["richtig"] == "ja"
    n[satz] = (sum(1 for r in a.values() if r["richtig"] == "ja"), len(a), sum(1 for r in b.values() if r["richtig"] == "ja"), len(b))
print()
for s, (x, nx, y, ny) in n.items():
    print(f"{s:<6} AB: {x}/{nx}   aus: {y}/{ny}")
print("Hinweis: 'richtig' ist die Skriptbewertung (Erwartungswert im ersten Satz, großzügig); Entwicklungsfragen, keine Belege für den Beitrag.")
PY
dateien=""
for x in evaluationsdaten/rechen_varianten_*-V19b.csv evaluationsdaten/rechen_varianten_*-V19aus.csv protokolle/rechen_varianten_*-V19b.txt protokolle/rechen_varianten_*-V19aus.txt \
         protokolle/vergleich_v19b.txt protokolle/teste_v19b_offline.txt $(ls -t protokolle/nachtlauf_v19b_*.txt 2>/dev/null | head -1); do
  [ -f "$x" ] && dateien="$dateien $x"
done
python -m zipfile -c V19b_ergebnisse.zip $dateien && cp V19b_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V19b_ergebnisse.zip (auch in Windows-Downloads: V19b_ergebnisse.zip)"
echo "=== fertig $(date +%H:%M) ==="
