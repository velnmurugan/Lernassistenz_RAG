#!/usr/bin/env bash
# V19c-Lauf (nur RAG, Vordergrund, kein nohup): V19=AB1 = Formelsuche vorab mit nur 1 Zusatz-Chunk + Parser-Korrekturen.
# Frage: Vermeidet 1 statt 2 Zusatz-Chunks die Verluste von AB (F4, R05 in RV-v2, R04, R21 in RV-v1) und behält die Gewinne?
# Teil 1 "kern" (20 Fragen: Gewinne und Verluste von AB, Zielfälle R07, Kontrolle F62; ca. 1 h 10 min)
# Teil 2 "rest" (die übrigen 45 Fragen der drei Sätze; ca. 2 h)   -> Aufruf: nachtlauf_v19c.sh [kern|voll]  (Standard voll, zusammen ca. 3 h 10 min)
# Vergleich mit den vorhandenen Läufen AB (…-V19b.csv) und aus (…-V19aus.csv) aus evaluationsdaten/.
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle evaluationsdaten
WAHL=${1:-voll}
export PYTHONUNBUFFERED=1 LERNASSISTENT_G=G-v5 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
for f in RV1-V19b RV2-V19b N100R-V19b RV1-V19aus RV2-V19aus N100R-V19aus; do
  [ -f "evaluationsdaten/rechen_varianten_$f.csv" ] || { echo "ABBRUCH: evaluationsdaten/rechen_varianten_$f.csv fehlt (Vergleichslauf AB/aus vom 29 Oct nötig)."; exit 1; }
done
echo "=== Offline-Tests $(date +%H:%M) ==="
for m in "" A AB; do
  LERNASSISTENT_V19=$m timeout 300 python skripte/evaluation/teste_v19_offline.py > "protokolle/teste_v19_offline_${m:-aus}.txt" 2>&1; rc=$?
  echo "teste_v19_offline ${m:-aus}: $(tail -1 protokolle/teste_v19_offline_${m:-aus}.txt) (rc=$rc)"; [ $rc -eq 0 ] || { echo "ABBRUCH"; exit 1; }
done
for t in teste_v19b_offline teste_v19c_offline; do
  TB=$(find . -maxdepth 2 -name $t.py | head -1)
  [ -n "$TB" ] || { echo "ABBRUCH: $t.py fehlt"; exit 1; }
  (cd "$(dirname "$TB")" && python $t.py) > protokolle/$t.txt 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"; [ $rc -eq 0 ] || { echo "ABBRUCH: $t"; exit 1; }
done
for t in teste_v18_offline teste_v17_offline teste_v16_offline teste_v15_offline teste_v14_offline; do
  arg=""; [ $t = teste_v18_offline ] && arg=ADEK
  LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=AB1 timeout 300 python skripte/evaluation/$t.py $arg > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"; [ $rc -eq 0 ] || { echo "ABBRUCH: $t (siehe protokolle/$t.txt)"; exit 1; }
done
LERNASSISTENT_V19=AB1 python - <<'PY' || { echo "ABBRUCH: Schalter AB1 wirkt nicht (formelsuche.py ohne V19c?)"; exit 1; }
import sys, os
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "lernassistent")]
import rechenbaustein as rb, formelsuche as fs
ok = bool(fs.V19_A) and bool(rb.V19_B) and fs.V19_ZUSATZ == 1
print("Schalter-Kontrolle V19='AB1': V19_A=%s V19_B=%s V19_ZUSATZ=%s -> %s" % (fs.V19_A, rb.V19_B, fs.V19_ZUSATZ, "OK" if ok else "FEHLER"))
sys.exit(0 if ok else 1)
PY
export LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_V18=ADEK LERNASSISTENT_V19=AB1
RV1=daten/testfragen/rechen_varianten_v1.csv; N1R=daten/testfragen/n100_rechnung_v1.csv; RV2=daten/testfragen/rechen_varianten_v2.csv
lauf () {  # $1 Label  $2 Fragen-CSV  $3 Fragen
  echo; echo "=== $1 (RP=$LERNASSISTENT_RP RB=$LERNASSISTENT_RB V18=$LERNASSISTENT_V18 V19=$LERNASSISTENT_V19) $(date +%H:%M) ==="
  rm -f "evaluationsdaten/rechen_varianten_$1.csv"
  python skripte/evaluation/teste_rechen_varianten.py "$1" --fragen "$2" --nur "$3" 2>&1 | tee "protokolle/rechen_varianten_$1.txt"
}
vergleich () {
python - <<'PY' 2>&1 | tee protokolle/vergleich_v19c.txt
import csv, os
csv.field_size_limit(10**9)
def lade(*ps):
    d = {}
    for p in ps:
        if os.path.exists(p):
            d.update({r["nr"]: r for r in csv.DictReader(open(p, encoding="utf-8"))})
    return d
E = "evaluationsdaten/rechen_varianten_"
print("Satz   Frage  aus                  AB (2 Chunks)        AB1 (1 Chunk)")
cnt = {"aus": [0, 0], "AB": [0, 0], "AB1": [0, 0]}
for satz in ("RV1", "N100R", "RV2"):
    aus = lade(f"{E}{satz}-V19aus.csv"); ab = lade(f"{E}{satz}-V19b.csv"); a1 = lade(f"{E}{satz}-V19b1k.csv", f"{E}{satz}-V19b1r.csv")
    for k in sorted(a1, key=lambda x: (x[0], int(''.join(c for c in x if c.isdigit()) or 0))):
        f = lambda r: (f"{r['richtig']:<4} {r['rechen_pruefung']}" if r else "-")
        print(f"{satz:<6} {k:<6} {f(aus.get(k)):<20} {f(ab.get(k)):<20} {f(a1.get(k))}")
        for name, d in (("aus", aus), ("AB", ab), ("AB1", a1)):
            if k in d:
                cnt[name][1] += 1; cnt[name][0] += d[k]["richtig"] == "ja"
print()
print("Auf den bisher gelaufenen AB1-Fragen richtig:  aus %d/%d   AB %d/%d   AB1 %d/%d" % (*cnt["aus"], *cnt["AB"], *cnt["AB1"]))
print("Hinweis: 'richtig' = Skriptbewertung (großzügig). Entwicklungsfragen; Gewinne/Verluste wurden nach AB ausgewählt (Regression zur Mitte möglich).")
PY
}
zippen () {
  dateien=""
  for x in evaluationsdaten/rechen_varianten_*-V19b1?.csv protokolle/rechen_varianten_*-V19b1?.txt protokolle/vergleich_v19c.txt protokolle/teste_v19c_offline.txt $(ls -t protokolle/nachtlauf_v19c_*.txt 2>/dev/null | head -1); do
    [ -f "$x" ] && dateien="$dateien $x"
  done
  python -m zipfile -c V19c_ergebnisse.zip $dateien && cp V19c_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
  echo "Ergebnis-Zip: ~/RAG/V19c_ergebnisse.zip (auch in Windows-Downloads: V19c_ergebnisse.zip)"
}
# Teil 1: kern
lauf RV1-V19b1k  $RV1 R04,R05,R07,R14,R17,R18,R19,R21
lauf N100R-V19b1k $N1R F1,F4,F29,F62
lauf RV2-V19b1k  $RV2 R03,R05,R07,R09,R12,R17,R18,R20
echo; echo "=== Zwischenstand nach Teil 1 $(date +%H:%M) ==="; vergleich; zippen
[ "$WAHL" = "kern" ] && { echo "=== fertig (nur kern) $(date +%H:%M) ==="; exit 0; }
# Teil 2: rest
lauf RV1-V19b1r  $RV1 R01,R02,R03,R06,R08,R09,R10,R11,R12,R13,R15,R16,R20,R22
lauf N100R-V19b1r $N1R F2,F3,F7,F13,F14,F15,F37,F38,F39,F40,F43,F50,F52,F55,F61,B5,B24,B27
lauf RV2-V19b1r  $RV2 R01,R02,R04,R06,R08,R10,R11,R13,R14,R15,R16,R21,R22
echo; echo "=== Vergleich gesamt $(date +%H:%M) ==="; vergleich; zippen
echo "=== fertig $(date +%H:%M) ==="
