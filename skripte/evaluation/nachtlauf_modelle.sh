#!/usr/bin/env bash
# Modellvergleich N100 mit der V11B-Konfiguration (Vordergrund, kein nohup). Nur das Generator-Modell wechselt.
# Aufruf: nachtlauf_modelle.sh [antworten|faith|alles|nur-vergleich] [Modellschlüssel ...]
#   Schlüssel: qwen4b gemma4b gemma12 gptoss   (Standard, ca. 4 h: qwen4b gemma4b; gptoss nur mit MOE=ja)
# Schritte: Umgebung V11B festnageln -> Offline-Tests -> Modelle laden -> Kontrolle mit qwen3.5:9b (8 Fragen gegen gespeicherten V11B-Lauf)
#           -> je Modell: Kurztest, N100 mit und ohne Retrieval -> Vergleich (Kennzahlen, Antwortbogen) -> [faith] Faithfulness je Modell.
cd "$(dirname "$0")/../.." || exit 1
MODUS=${1:-antworten}; shift
mkdir -p protokolle evaluationsdaten
export PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
KB=daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
FF=daten/testfragen/testfragen_fischer_v2_chunks_beide_v7r.csv
t0=$(date +%s); stunde () { echo "[$(date +%H:%M)] $1 (seit Start $(( ($(date +%s)-t0)/60 )) min)"; }

# ---- V11B-Konfiguration festnageln (alles, was nach V11B dazukam, aus)
v11b_env () {
  unset LERNASSISTENT_CTX LERNASSISTENT_RW LERNASSISTENT_V18 LERNASSISTENT_V19 LERNASSISTENT_MODELL LERNASSISTENT_THINK LERNASSISTENT_TIMEOUT
  export LERNASSISTENT_G=G-v4 LERNASSISTENT_RP=RP-v5 LERNASSISTENT_FS=aus
  unset LERNASSISTENT_RB   # RP-v5 reproduziert V11B; RB-Standard der neuen Version wird durch die Kontrolle geprüft
}
v11b_env

# ---- Modellliste: Schlüssel|Ollama-Tag|Label|think|Zeitgrenze s|Größe GB
declare -A TAG LABEL THINK ZEIT GB
TAG[qwen4b]=qwen3.5:4b;            LABEL[qwen4b]=V11BQWEN4B;    THINK[qwen4b]=aus; ZEIT[qwen4b]=300; GB[qwen4b]=3.3
TAG[gemma4b]=gemma4:e4b-it-qat;    LABEL[gemma4b]=V11BGEMMA4B;  THINK[gemma4b]=aus; ZEIT[gemma4b]=400; GB[gemma4b]=6.1
TAG[gemma12]=gemma4:12b-it-qat;    LABEL[gemma12]=V11BGEMMA12;  THINK[gemma12]=aus; ZEIT[gemma12]=600; GB[gemma12]=7.2
TAG[gptoss]=gpt-oss:20b;           LABEL[gptoss]=V11BGPTOSS20;  THINK[gptoss]=low; ZEIT[gptoss]=900; GB[gptoss]=13
RAM=$(awk '/MemTotal/{printf "%d", $2/1048576}' /proc/meminfo)
if [ $# -gt 0 ]; then WAHL="$*"; else
  WAHL="qwen4b gemma4b"
  [ "${MOE:-nein}" = ja ] && WAHL="$WAHL gptoss"
fi
echo "RAM in WSL: ${RAM} GB | Modelle: $WAHL | Modus: $MODUS"
for k in $WAHL; do [ -n "${TAG[$k]:-}" ] || { echo "ABBRUCH: unbekannter Schlüssel $k"; exit 1; }; done
for f in "$KB" "$FF" evaluationsdaten/vergleich_rag_RAGVGL-N100F-V11B-BEIDE7.csv evaluationsdaten/vergleich_rag_RAGVGL-N100B-V11B-BEIDE7.csv \
         skripte/laeufe/n100_rag_vs_ohne_lauf.sh skripte/evaluation/vergleich_mit_ohne_rag.py; do
  [ -f "$f" ] || { echo "ABBRUCH: $f fehlt"; exit 1; }
done
ollama list | grep -q mistral-nemo || { echo "ABBRUCH: Richter mistral-nemo fehlt (ollama pull mistral-nemo)"; exit 1; }
ollama list | grep -q "qwen3.5:9b" || { echo "ABBRUCH: qwen3.5:9b fehlt (Kontrolllauf)"; exit 1; }
stopp () { for m in $(ollama ps 2>/dev/null | awk 'NR>1{print $1}'); do ollama stop "$m"; done; }
fertig () { python - "$1" <<'PY'
import csv, sys, os
csv.field_size_limit(10**9)
L = sys.argv[1]; ok = True
for p, n in (("F", 70), ("B", 30)):
    f = f"evaluationsdaten/vergleich_rag_RAGVGL-N100{p}-{L}-BEIDE7.csv"
    ok = ok and os.path.exists(f) and len(list(csv.DictReader(open(f, encoding="utf-8")))) >= n
sys.exit(0 if ok else 1)
PY
}

if [ "$MODUS" != nur-vergleich ] && [ "$MODUS" != faith ]; then
stunde "Offline-Tests"
python skripte/evaluation/teste_modell_offline.py lernassistent/rag_pipeline.py > protokolle/teste_modell_offline.txt 2>&1; rc=$?
echo "teste_modell_offline: $(tail -1 protokolle/teste_modell_offline.txt) (rc=$rc)"; [ $rc -eq 0 ] || { echo "ABBRUCH"; exit 1; }
for t in teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do
  [ -f skripte/evaluation/$t.py ] || continue
  python skripte/evaluation/$t.py > "protokolle/$t.txt" 2>&1; rc=$?
  echo "$t: $(tail -1 protokolle/$t.txt) (rc=$rc)"; [ $rc -eq 0 ] || echo "WARNUNG: $t nicht bestanden (V11B-Umgebung); Lauf geht weiter, Ausgabe in protokolle/$t.txt prüfen."
done
python - <<'PY' | tee protokolle/modellvergleich_konfiguration.txt
import sys, os
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "lernassistent")]
import rag_pipeline as rp
print("Konfiguration (V11B soll sein: G-v4 / RP-v5 / HP-v4 / FS aus):")
print("  Prompt", rp.SCAFFOLDING_VERSION, "| Rechenprüfung", rp.RECHEN_PRUEFUNG_VERSION, "| Hinweisprüfung", rp.HINWEIS_PRUEFUNG_VERSION, "| Modell", rp.MODEL_NAME, "| Optionen", rp.GENERIERUNGS_OPTIONEN)
for k in sorted(k for k in os.environ if k.startswith("LERNASSISTENT_")):
    print("  ", k, "=", os.environ[k])
PY

# ---- Modelle laden
stunde "Modelle laden"
for k in $WAHL; do
  if ollama list | awk '{print $1}' | grep -qx "${TAG[$k]}"; then echo "${TAG[$k]}: vorhanden"; else
    echo "${TAG[$k]}: Download (${GB[$k]} GB) ..."; ollama pull "${TAG[$k]}" || { echo "WARNUNG: ${TAG[$k]} nicht ladbar, wird übersprungen."; WAHL=${WAHL/$k/}; }
  fi
done

# ---- Kontrolllauf: dieselbe Konfiguration mit qwen3.5:9b gegen den gespeicherten V11B-Lauf (erste 8 Fischer-Fragen)
stunde "Kontrolle: qwen3.5:9b gegen gespeicherten V11B-Lauf"
stopp
rm -f "evaluationsdaten/vergleich_rag_RAGVGL-KONTROLLE-V11B.csv"
python skripte/evaluation/vergleich_mit_ohne_rag.py RAGVGL-KONTROLLE-V11B --kb "$KB" --fragen "$FF" --ideen '' --retrieval hybrid_kg_rr --judge none --limit 8 2>&1 | tail -12
python - <<'PY' | tee protokolle/kontrolle_v11b.txt
import csv, re, sys
csv.field_size_limit(10**9)
n = lambda t: re.sub(r"\s+", " ", (t or "").strip())
a = {r["nr"]: r for r in csv.DictReader(open("evaluationsdaten/vergleich_rag_RAGVGL-N100F-V11B-BEIDE7.csv", encoding="utf-8"))}
b = list(csv.DictReader(open("evaluationsdaten/vergleich_rag_RAGVGL-KONTROLLE-V11B.csv", encoding="utf-8")))
gl = [r["nr"] for r in b if n(r["antwort_mit"]) == n(a[r["nr"]]["antwort_mit"])]
st = [r["nr"] for r in b if r["status_mit"] == a[r["nr"]]["status_mit"] and r.get("rechen_pruefung_mit", "") == a[r["nr"]].get("rechen_pruefung_mit", "")]
print(f"Kontrolle V11B: Antwort identisch bei {len(gl)} von {len(b)} ({', '.join(gl) or '-'}); Status und Rechenprüfung gleich bei {len(st)} von {len(b)}.")
if len(gl) < 3:
    print("ABBRUCH-BEDINGUNG: weniger als 3 von 8 identisch -> die Umgebung entspricht nicht dem gespeicherten V11B-Lauf."); sys.exit(2)
if len(gl) < len(b):
    print("Hinweis: Abweichungen möglich durch Ollama-Cache/Version; die Modelle werden trotzdem gegen den gespeicherten Lauf verglichen.")
PY
rc=${PIPESTATUS[0]}
[ $rc -eq 2 ] && [ "${GATE:-streng}" = streng ] && { echo "ABBRUCH (mit GATE=weiter überspringen). Ausgabe von protokolle/modellvergleich_konfiguration.txt und kontrolle_v11b.txt schicken."; exit 1; }

# ---- je Modell
for k in $WAHL; do
  L=${LABEL[$k]}
  if fertig "$L"; then echo "[$(date +%H:%M)] $L: bereits vollständig, übersprungen (Dateien löschen für Neulauf)"; continue; fi
  stunde "$L ${TAG[$k]}: Kurztest"
  stopp
  export LERNASSISTENT_MODELL=${TAG[$k]} LERNASSISTENT_THINK=${THINK[$k]} LERNASSISTENT_TIMEOUT=${ZEIT[$k]}
  python - <<'PY' || { echo "WARNUNG: Kurztest fehlgeschlagen, Modell wird übersprungen."; v11b_env; continue; }
import sys, os, time
sys.path[:0] = [os.getcwd(), os.path.join(os.getcwd(), "lernassistent")]
import rag_pipeline as rp
t = time.time(); a = rp.frage_llm("Antworte in einem Satz auf Deutsch: Was ist ein ohmscher Widerstand?", options=rp.GENERIERUNGS_OPTIONEN)
print(f"Kurztest {rp.MODEL_NAME} (think={os.environ.get('LERNASSISTENT_THINK')}): {time.time()-t:.0f} s (inkl. Laden) | {a[:200]!r}")
t = time.time(); a = rp.frage_llm("Antworte in einem Satz auf Deutsch: Was ist ein ohmscher Widerstand?", options=rp.GENERIERUNGS_OPTIONEN)
print(f"  zweiter Aufruf: {time.time()-t:.1f} s")
sys.exit(0 if a.strip() and "<think>" not in a else 1)
PY
  ollama ps
  echo "(Spalte PROCESSOR: Anteil GPU/CPU notieren – bei Aufteilung ist das Modell langsamer.)"
  stunde "$L ${TAG[$k]}: N100"
  OHNE_RAGAS=1 bash skripte/laeufe/n100_rag_vs_ohne_lauf.sh "$L" 2>&1 | tee "protokolle/n100_${L}_$(date +%Y%m%d_%H%M).txt"
  v11b_env
  stopp
done
fi

# ---- Vergleich
stunde "Vergleich"
FERTIG=""; for k in qwen4b gemma4b gemma12 gptoss; do fertig "${LABEL[$k]}" 2>/dev/null && FERTIG="$FERTIG ${LABEL[$k]}"; done
[ -n "$FERTIG" ] || { echo "Kein vollständiger Modelllauf vorhanden."; exit 1; }
python skripte/evaluation/modell_kennzahlen.py $FERTIG --ref V11B 2>&1 | tee protokolle/modell_kennzahlen.txt
python skripte/evaluation/vergleich_laeufe_n100.py $FERTIG --ref V11B 2>&1 | tee protokolle/vergleich_laeufe_n100_modelle.txt

# ---- Faithfulness (Richter mistral-nemo; V11B als Basis, identische Antworten werden übernommen)
if [ "$MODUS" = faith ] || [ "$MODUS" = alles ]; then
  stopp
  for L in $FERTIG; do
    stunde "Faithfulness $L"
    python skripte/evaluation/faithfulness_rag_vs_ohne.py --label $L --basis V11B 2>&1 | tee protokolle/faithfulness_${L}_$(date +%Y%m%d_%H%M).txt
  done
fi

# ---- Zip
stunde "Zip"
dateien=""
for x in evaluationsdaten/vergleich_rag_RAGVGL-N100?-V11B?*-BEIDE7*.csv evaluationsdaten/vergleich_rag_RAGVGL-N100?-V11B?*-BEIDE7*.txt \
         evaluationsdaten/vergleich_rag_RAGVGL-KONTROLLE-V11B.csv evaluationsdaten/modellvergleich_N100_*.md evaluationsdaten/modellvergleich_N100_*.csv \
         evaluationsdaten/vergleich_laeufe_N100_V11B_V11B?*.md evaluationsdaten/aenderungen_N100_V11B?*_gegen_V11B.csv \
         evaluationsdaten/faithfulness_rag_vs_ohne_V11B?*.csv evaluationsdaten/faithfulness_rag_vs_ohne_V11B?*.txt \
         protokolle/teste_modell_offline.txt protokolle/modellvergleich_konfiguration.txt protokolle/kontrolle_v11b.txt protokolle/modell_kennzahlen.txt \
         protokolle/vergleich_laeufe_n100_modelle.txt protokolle/n100_V11B?*.txt protokolle/faithfulness_V11B?*.txt \
         $(ls -t protokolle/nachtlauf_modelle_*.txt 2>/dev/null | head -1); do
  [ -f "$x" ] && dateien="$dateien $x"
done
python -m zipfile -c N100_modelle_ergebnisse.zip $dateien && cp N100_modelle_ergebnisse.zip "$(bash "$HOME/RAG/skripte/werkzeuge/windows_downloads.sh")/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/N100_modelle_ergebnisse.zip (auch in Windows-Downloads)"
stunde "fertig"
