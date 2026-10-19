# Archiv der Patchstände V5 bis V10a (nur Code und Doku)

Reihenfolge (jede Datei ist ein Paket der geänderten Dateien, in dieser Reihenfolge angewendet):
 1. V5_paket.zip
 2. V6_paket.zip
 3. V7_paket.zip
 4. V7_patch1.zip
 5. V7_patch2.zip
 6. V7_patch3.zip
 7. V7_patch4.zip
 8. V7_patch5.zip
 9. V8_patch.zip
10. V8b_patch.zip
11. V8c_patch.zip
12. V8d_patch.zip
13. V9_patch.zip
14. V9b_patch.zip
15. V9c_patch.zip
16. V9c2_patch.zip
17. V9d_patch.zip
18. V10_patch.zip
19. V10a_patch.zip

Werkzeuge ohne Versionsstand: RAGVGL_patch.zip (Vergleich mit/ohne RAG), retrieval_erklaeren_paket.zip.

Hinweise
- V9c_patch und V9c2_patch sind inhaltlich gleich.
- Entfernt wurden die Testsets mit Buch-Ankerzitaten (testfragen_fischer_v1.csv, testideen_fischer_v1.csv) und .pyc-Dateien.
  Sie liegen nur lokal in daten/testfragen/ (nicht im Git).
- Git-Tags mit vollständigem Stand: v1-t0 (V0), V1-hybrid, V2-kg, V3-rr, V4-s2, v6-pre-v7 (V5+V6), v7, v8d, v9d, v10, v10a.
- Entpacken eines Standes: python -m zipfile -e archiv_versionen/V8b_patch.zip <Zielordner>
