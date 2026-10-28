# Held-out-Test mit 100 neuen Fragen

Inhalt des Pakets
- daten/testfragen/testfragen_fischer_v2.csv  – 70 Fischer-Fragen (62 im Buch, 8 außerhalb), noch ohne chunk_id
- skripte/evaluation/exportiere_chunkstichprobe.py – Chunk-Stichprobe aus der Böge-KB für die 30 Böge-Fragen
- skripte/laeufe/n100_lauf.sh – Lauf einer Version auf dem Set

Schritte (im Ordner ~/RAG, Umgebung pilot_rag)
1. Entpacken (zip landet in Downloads):
   python -m zipfile -e "/mnt/c/Users/Vel Narayanasamy/Downloads/neu100_paket.zip" .
2. Böge-Stichprobe ziehen und mir schicken:
   python skripte/evaluation/exportiere_chunkstichprobe.py --kb daten/wissensbasen/knowledge_base_boege.json --ausschluss daten/testfragen/testfragen_v1.csv --n 45 --seed 2026 --ausgabe evaluationsdaten/boege_stichprobe
   cp evaluationsdaten/boege_stichprobe.txt "/mnt/c/Users/Vel Narayanasamy/Downloads/"
3. Fischer-Lauf auf V10a (der Böge-Teil wird übersprungen, solange testfragen_boege_v2.csv fehlt):
   bash skripte/laeufe/n100_lauf.sh V10A 2>&1 | tee protokolle/n100_V10A_$(date +%Y%m%d_%H%M).txt
4. Sobald die Böge-Fragen da sind, denselben Befehl noch einmal starten: Fischer ist dann fertig (Fortsetzung), es läuft nur Böge.
