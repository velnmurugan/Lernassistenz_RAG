#!/usr/bin/env bash
# V14d Kurzlauf (ca. 1 h, nur Rechnen): RP-v11 + RW-v5 (Platzhalter, Grundeinheiten, weitere Schreibweisen, Startwerte nur mit Grundeinheit).
# 1) 8 RV-Fragen, die in V134 falsch waren. Abbruch, wenn RW-v5 in weniger als 2 davon genutzt wird.
# 2) 22 N100-Rechenfragen. Am Ende: Zusammenfassung (genutzt / Rückfall / ohne Platzhalter, Verweigerungen, richtig).
# Start (aus ~/RAG, pilot_rag, nur Ollama läuft):
#   bash skripte/evaluation/kurzlauf_v14d.sh 2>&1 | tee protokolle/kurzlauf_v14d_$(date +%Y%m%d_%H%M).txt
cd "$(dirname "$0")/../.." || exit 1
mkdir -p protokolle
export PYTHONUNBUFFERED=1 LERNASSISTENT_RP=RP-v11 LERNASSISTENT_G=G-v5 LERNASSISTENT_FS=FS-v3 LERNASSISTENT_CTX=8192 LERNASSISTENT_RW=RW-v5
python skripte/evaluation/teste_v14_offline.py | tail -1
zusammenfassung () {  # $1 Label
  python - "$1" <<'PY'
import csv, sys; csv.field_size_limit(10**9)
x = list(csv.DictReader(open(f"evaluationsdaten/rechen_varianten_{sys.argv[1]}.csv", encoding="utf-8")))
z = lambda f: sum(1 for r in x if f(r))
print(f"{sys.argv[1]}: {len(x)} Fragen | richtig {z(lambda r: r['richtig'] == 'ja')} | RW genutzt {z(lambda r: ' genutzt' in r['werkzeug'])}"
      f" | Rückfall {z(lambda r: 'Rückfall' in r['werkzeug'])} | ohne Platzhalter {z(lambda r: 'keine Platzhalter' in r['werkzeug'])}"
      f" | Verweigerung {z(lambda r: r['status'] == 'NICHT_IM_MATERIAL')}")
sys.exit(0 if z(lambda r: ' genutzt' in r['werkzeug']) >= 2 else 1)
PY
}
echo "=== RV, 8 in V134 falsche Fragen, RW-v5 $(date +%H:%M) ==="
rm -f evaluationsdaten/rechen_varianten_V14D.csv
python skripte/evaluation/teste_rechen_varianten.py V14D --nur R01,R02,R04,R12,R14,R17,R19,R20 2>&1 | tee protokolle/rechen_varianten_V14D.txt
if ! zusammenfassung V14D; then
  echo "ABBRUCH: RW-v5 in weniger als 2 Fragen genutzt. Ausgabe bitte schicken."
  python -m zipfile -c V14D_ergebnisse.zip evaluationsdaten/rechen_varianten_V14D.csv protokolle/rechen_varianten_V14D.txt \
    && cp V14D_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
  exit 1
fi
echo; echo "=== N100-Rechenfragen (22), RW-v5 $(date +%H:%M) ==="
rm -f evaluationsdaten/rechen_varianten_N100R-V14D.csv
python skripte/evaluation/teste_rechen_varianten.py N100R-V14D --fragen daten/testfragen/n100_rechnung_v1.csv 2>&1 | tee protokolle/rechen_varianten_N100R-V14D.txt
echo; zusammenfassung V14D; zusammenfassung N100R-V14D
python -m zipfile -c V14D_ergebnisse.zip evaluationsdaten/rechen_varianten_{V14D,N100R-V14D}.csv \
  protokolle/rechen_varianten_{V14D,N100R-V14D}.txt $(ls -t protokolle/kurzlauf_v14d_*.txt 2>/dev/null | head -1) \
  && cp V14D_ergebnisse.zip "/mnt/c/Users/Vel Narayanasamy/Downloads/" 2>/dev/null
echo "Ergebnis-Zip: ~/RAG/V14D_ergebnisse.zip (auch in Windows-Downloads)"
echo "=== fertig $(date +%H:%M) ==="
