#!/usr/bin/env bash
# Freeze-Lauf (Vordergrund, kein nohup): aktuelle Rechenpfad-Varianten auf allen 100 Fragen (N100) und den 22 Fragen aus RV-v1.
# Reihenfolge: Tests -> N100 "aus" (V19 aus) -> N100 "AB" (V19=AB) -> RV-v1 (22) aus und AB -> Vergleich mit V11B
#              -> Faithfulness (V11B als Basis, identische Antworten werden übernommen) -> RAGAS (Answer-/Context-Relevance) je Lauf.
# Aufruf:  nachtlauf_n100_freeze.sh [voll|ohne-ragas|nur-vergleich]    (Standard voll; ca. 8 h, ohne RAGAS ca. 5-6 h)
cd "$(dirname "$0")/../.." || exit 1
WAHL=${1:-voll}
mkdir -p protokolle evaluationsdaten
export PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 LERNASSISTENT_G=G-v5 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=
export LERNASSISTENT_RP=RP-v13 LERNASSISTENT_RB=RB-v8 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_V18=ADEK
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
RV1=daten/testfragen/rechen_varianten_v1.csv
t0=$(date +%s); stunde () { echo "[$(date +%H:%M)] $1 (seit Start $(( ($(date +%s)-t0)/60 )) min)"; }
for f in "$KB" "$RV1" evaluationsdaten/vergleich_rag_RAGVGL-N100F-V11B-BEIDE7.csv evaluationsdaten/vergleich_rag_RAGVGL-N100B-V11B-BEIDE7.csv \
         skripte/laeufe/n100_rag_vs_ohne_lauf.sh skripte/evaluation/vergleich_mit_ohne_rag.py skripte/evaluation/ragas_auswertung.py; do
  [ -f "$f" ] || { echo "ABBRUCH: $f fehlt"; exit 1; }
done
ollama list | grep -q mistral-nemo || { echo "ABBRUCH: Richter mistral-nemo fehlt (ollama pull mistral-nemo)"; exit 1; }
[ "$WAHL" = nur-vergleich ] || {
stunde "Offline-Tests"
for m in "" A AB; do
  LERNASSISTENT_V19=$m timeout 300 python skripte/evaluation/teste_v19_offline.py > "protokolle/teste_v19_offline_${m:-aus}.txt" 2>&1; rc=$?
  echo "teste_v19_offline ${m:-aus}: $(tail -1 protokolle/teste_v19_offline_${m:-aus}.txt) (rc=$rc)"; [ $rc -eq 0 ] || { echo "ABBRUCH"; exit 1; }
done
for t in teste_v19b_offline teste_v19c_offline; do
  TB=$(find . -maxdepth 2 -name $t.py | head -1); [ -n "$TB" ] || { echo "ABBRUCH: $t.py fehlt"; exit 1; }
  (cd "$(dirname "$TB")" && python $t.py) > protokolle/$t.txt 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"; [ $rc -eq 0 ] || { echo "ABBRUCH: $t"; exit 1; }
done
for t in teste_v18_offline teste_v17_offline teste_v16_offline teste_v15_offline teste_v14_offline; do
  arg=""; [ $t = teste_v18_offline ] && arg=ADEK
  LERNASSISTENT_V19=AB timeout 300 python skripte/evaluation/$t.py $arg > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"; [ $rc -eq 0 ] || { echo "ABBRUCH: $t"; exit 1; }
done
LERNASSISTENT_V19=AB python - <<'PY' || { echo "ABBRUCH: Schalter AB wirkt nicht"; exit 1; }
import sys, os
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "lernassistent")]
import rechenbaustein as rb, formelsuche as fs
ok = bool(fs.V19_A) and bool(rb.V19_B)
print("Schalter-Kontrolle V19='AB': V19_A=%s V19_B=%s -> %s" % (fs.V19_A, rb.V19_B, "OK" if ok else "FEHLER")); sys.exit(0 if ok else 1)
PY
for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done
ollama ps
# --- 1) N100 aus (V19 aus), 70 Fischer + 30 Böge, mit und ohne Retrieval
stunde "N100 aus"
LERNASSISTENT_V19= OHNE_RAGAS=1 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V19AUS 2>&1 | tee protokolle/n100_V19AUS_$(date +%Y%m%d_%H%M).txt
# --- 2) N100 AB
stunde "N100 AB"
LERNASSISTENT_V19=AB OHNE_RAGAS=1 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh V19AB 2>&1 | tee protokolle/n100_V19AB_$(date +%Y%m%d_%H%M).txt
# --- 3) RV-v1 (22 Fragen) aus und AB; Vergleich mit den früheren Läufen derselben Fragen (Reproduzierbarkeit)
for v in "aus:" "AB:AB"; do
  n=${v%%:*}; sw=${v#*:}
  stunde "RV-v1 $n"
  rm -f "evaluationsdaten/rechen_varianten_RV1-NACHT$n.csv"
  LERNASSISTENT_V19=$sw python skripte/evaluation/teste_rechen_varianten.py "RV1-NACHT$n" --fragen "$RV1" 2>&1 | tee "protokolle/rechen_varianten_RV1-NACHT$n.txt"
done
python - <<'PY' 2>&1 | tee protokolle/vergleich_rv1_nacht.txt
import csv, os
csv.field_size_limit(10**9)
E = "evaluationsdaten/rechen_varianten_"
def lade(p):
    return {r["nr"]: r for r in csv.DictReader(open(p, encoding="utf-8"))} if os.path.exists(p) else {}
for neu, alt in (("RV1-NACHTaus", "RV1-V19aus"), ("RV1-NACHTAB", "RV1-V19b")):
    a, b = lade(f"{E}{neu}.csv"), lade(f"{E}{alt}.csv")
    ids = [k for k in a if k in b]
    gl = sum(a[k]["richtig"] == b[k]["richtig"] and a[k].get("rechen_pruefung") == b[k].get("rechen_pruefung") for k in ids)
    ric = sum(a[k]["richtig"] == "ja" for k in a)
    print(f"{neu}: richtig {ric}/{len(a)}; gegenüber früherem Lauf {alt}: Urteil und Prüfstatus gleich bei {gl} von {len(ids)}" + ("" if gl == len(ids) else "  -> ABWEICHUNG: " + ", ".join(k for k in ids if a[k]['richtig'] != b[k]['richtig'] or a[k].get('rechen_pruefung') != b[k].get('rechen_pruefung'))))
PY
}
# --- 4) Vergleich N100 mit V11B
stunde "Vergleich"
python skripte/evaluation/vergleich_laeufe_n100.py V19AUS V19AB --ref V11B 2>&1 | tee protokolle/vergleich_laeufe_n100.txt
# --- 5) Faithfulness (Richter mistral-nemo); V11B zuerst (Basis), danach nur geänderte Antworten neu
for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done
stunde "Faithfulness V11B"
python skripte/evaluation/faithfulness_rag_vs_ohne.py --label V11B 2>&1 | tee protokolle/faithfulness_V11B_$(date +%Y%m%d_%H%M).txt
for L in V19AUS V19AB; do
  stunde "Faithfulness $L"
  python skripte/evaluation/faithfulness_rag_vs_ohne.py --label $L --basis V11B 2>&1 | tee protokolle/faithfulness_${L}_$(date +%Y%m%d_%H%M).txt
done
# --- 6) RAGAS Answer-/Context-Relevance (Faithfulness liegt oben vor), je Lauf und Teilsatz
if [ "$WAHL" = voll ]; then
  for L in V19AUS V19AB; do
    for P in F B; do
      stunde "RAGAS $L $P"
      python skripte/evaluation/ragas_auswertung.py "RAGVGL-N100${P}-${L}-BEIDE7" --judge mistral-nemo --kb "$KB" --metriken ar,cr 2>&1 | tee "protokolle/ragas_${L}_${P}.txt"
      for f in ragas_ergebnisse ragas_answer_relevance_details ragas_context_relevance_details; do
        [ -f "evaluationsdaten/$f.csv" ] && cp "evaluationsdaten/$f.csv" "evaluationsdaten/${f}_N100${P}_${L}.csv"
      done
    done
  done
fi
# --- 7) Zip
stunde "Zip"
dateien=""
for x in evaluationsdaten/vergleich_rag_RAGVGL-N100?-V19A*-BEIDE7*.csv evaluationsdaten/vergleich_rag_RAGVGL-N100?-V19A*-BEIDE7*.txt evaluationsdaten/vergleich_laeufe_N100_*.md \
         evaluationsdaten/aenderungen_N100_*.csv evaluationsdaten/faithfulness_rag_vs_ohne_*.csv evaluationsdaten/faithfulness_rag_vs_ohne_*.txt \
         evaluationsdaten/ragas_*_N100?_V19A*.csv evaluationsdaten/rechen_varianten_RV1-NACHT*.csv protokolle/vergleich_rv1_nacht.txt protokolle/vergleich_laeufe_n100.txt \
         protokolle/teste_v19*_offline*.txt protokolle/n100_V19A*.txt protokolle/faithfulness_V*.txt protokolle/ragas_V19A*.txt protokolle/rechen_varianten_RV1-NACHT*.txt \
         $(ls -t protokolle/nachtlauf_n100_freeze_*.txt 2>/dev/null | head -1); do
  [ -f "$x" ] && dateien="$dateien $x"
done
python -m zipfile -c N100_freeze_ergebnisse.zip $dateien && cp N100_freeze_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/N100_freeze_ergebnisse.zip (auch in Windows-Downloads)"
stunde "fertig"
