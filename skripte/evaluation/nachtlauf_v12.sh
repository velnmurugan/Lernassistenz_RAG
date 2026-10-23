#!/usr/bin/env bash
# V12 komplett unbeaufsichtigt (Vordergrund, Ausgabe nach evaluationsdaten/V12_nachtlauf.log). Start aus ~/RAG:
#   bash skripte/evaluation/nachtlauf_v12.sh
set -u
mkdir -p evaluationsdaten
{
echo "### 1/3 Offline-Tests"; for t in teste_v12_offline teste_rb2_offline teste_rb_offline teste_v10_offline; do python skripte/evaluation/$t.py | tail -1; done
echo; echo "### 2/3 Formelsuche mit echter KB"; python skripte/evaluation/teste_formelsuche.py
echo; echo "### 3/3 A/B V11b vs V12 (N100-Rechenfragen + 3 Varianten)"; python skripte/evaluation/vergleiche_v11b_v12.py V12-AB
echo; echo "FERTIG $(date)"
} 2>&1 | tee evaluationsdaten/V12_nachtlauf.log
