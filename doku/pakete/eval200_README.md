# eval200 – answers for the rating sheets

Fills "Answer WITHOUT RAG" and "Answer WITH RAG" in the rating sheets. With RAG = V20 (G-v6 + RP-v13, RB-v8, FS-v3, V18=ADEK, V19=AB, CTX 8192); without RAG = prompt O-v1; qwen3.5:9b, T = 0, seed 42, KB v7r.
Requires Eval300 (skripte/evaluation/eval300_antworten.py) and V20 (G-v6 patch) already set up.

```
cd ~ && python3 -c "import zipfile; zipfile.ZipFile('/mnt/c/Users/Vel Narayanasamy/Downloads/eval200.zip').extractall('.')"
cd ~/RAG && bash ~/eval200/eval200_lauf.sh einrichten
bash ~/eval200/eval200_lauf.sh q200    # 200 questions (N100 + NEU100), ~5-6 h -> Downloads/Bewertung_200_N100_NEU100_mit_Antworten.xlsx
bash ~/eval200/eval200_lauf.sh v4      # optional: 100 V4 questions, ~3 h -> Downloads/Bewertung_100_V4_mit_Antworten.xlsx
```
Restart the same command after an interruption; finished questions are skipped. Raw CSV + log are zipped to Downloads.
ID mapping (Q001… / V001… → set, original ID, Eval300 ID): daten/fragen_q200.csv, daten/fragen_v4_100.csv.
