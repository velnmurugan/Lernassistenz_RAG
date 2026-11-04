# Stand V20 – eingefroren für den Beitrag (4. Nov 2026)

Git-Tag: `v20-paper`. Alle Ergebnisse des Beitrags beziehen sich auf diesen Stand. Spätere Änderungen = neue Version (V21 …),
nur mit erneutem Lauf auf denselben Fragen.

## Konfiguration

| Baustein | Einstellung |
| --- | --- |
| Generator | qwen3.5:9b (Ollama), Temperatur 0, Seed 42, Kontext 8192 (`LERNASSISTENT_CTX=8192`) |
| Antwortprompt | G-v6 = G-v5 + L8 (rechnen, wenn alle Werte in der Frage stehen; Grundgleichung gekennzeichnet) + L9 (jede Teilfrage, alle Ergebnisse im ersten Satz) |
| Rechenprüfung | RP-v13 (intern `RP_V13`), Nachrechnung RB-v8, Formelsuche FS-v3, V18=ADEK, V19=AB, Rechenwerkzeug aus (`LERNASSISTENT_RW=`) |
| Retrieval | `hybrid_kg_rr` (Dense + BM25 + Wissensgraph, RRF, Cross-Encoder bge-reranker-v2-m3, 50 Kandidaten), 4 Abschnitte an das Modell |
| Wissensbasis | `daten/wissensbasen/knowledge_base_fischer_boege_v7r.json` (Fischer + Böge, 8.805 Abschnitte) |
| Ohne-RAG-Vergleich | Prompt O-v1 (nur die Frage), sonst gleiche Einstellungen |
| Oberfläche | UI-v2 (`skripte/patches/patch_ui2.py`): kurze Startseite (4 Schritte, nur Name), Verlauf in der Seitenleiste, Sitzungsübersicht, Hinweisstatistik, Zeitanzeige, Schrittleiste, Übungsfrage zu anderem Aspekt, Muster „du hast gesehen/gelesen“ als Materialverweis (HP) |

Start der App: `bash skripte/laeufe/start_demo.sh` (setzt die Umgebungsvariablen oben).

## Pakete und Skripte

| Paket | Zweck | Skripte |
| --- | --- | --- |
| v20 | G-v6 einspielen, Offline-Test (7/7), Rechenfragen V4 | `skripte/patches/patch_v20.py`, `skripte/evaluation/teste_v20_offline.py`, `skripte/laeufe/v20_lauf.sh` |
| ui2 | Oberfläche UI-v2 | `skripte/patches/patch_ui2.py`, `skripte/laeufe/start_demo.sh` |
| eval300 | Eval300 (V11B), Antworten + Richter | `skripte/evaluation/eval300_*.py`, `skripte/laeufe/eval300_lauf.sh` |
| eval200 | Bewertungsbögen 200 + 100 (V20) | `skripte/evaluation/baue_boegen.py`, `fuelle_excel.py`, `skripte/laeufe/eval200_lauf.sh` |
| run300 | Fragen300 mit V20: Antworten, Rang, Richter, Faithfulness, Bogen | `skripte/evaluation/{antworten,rang,richter,faith,fuelle,zusammen}300.py`, `skripte/laeufe/lauf300.sh` |

Paket-READMEs: `doku/pakete/`.

## Fragen300 (eingefrorener Testsatz)

- 300 Fragen: Fischer 135, Böge 135, außerhalb 30; Konzept 75, Fakt 75, Rechnung 60, Tabellenabfrage 30, Aufzählung 30, außerhalb 30.
- Gegen die Bücher geprüft (3. Nov 2026): 180 unverändert, 90 kleine Korrekturen (Abschnitt, Buchstelle, Seite, Referenz), keine schwerwiegenden.
- Bewertungsbogen `Fragen300_Bewertung.xlsx`: Bewertung 1 (Vel), 2 (Prof. Zinn), 3 (LLM-Richter) je ohne / mit RAG; Statistik mit κ, Vorzeichentest, Recall@k, MRR, Faithfulness, Zeit.
- Daten (nicht im Git, Buchinhalte): `daten/testfragen/fragen300.csv`, `gold300.json`; Läufe in `evaluationsdaten/*300_F300-V20*`, Archiv `evaluationsdaten/archiv/F300-V20/`.

## Lauf F300-V20 (Q1–Q100, 3./4. Nov 2026)

- Richter: gemma4:12b (Google), Prompt R300-J1 (Kriterien wörtlich aus dem Bogen + 10 Beispiele aus entfernten Eval300-Fragen), T 0, Seed 42; derselbe Richter für Faithfulness (Prompts J-v1).
- Rang der Buchstelle: Abschnitt zählt als Treffer, wenn ≥ 40 % seiner 4-Wort-Folgen auf der PDF-Seite der Frage stehen; 0 = nicht unter 50.

| | ohne RAG | mit RAG |
| --- | --- | --- |
| Punkteanteil (Vel, 92 Buchfragen) | 34,2 % | 83,7 % |
| Außerhalb abgelehnt | 5/8 | 8/8 |
| Faithfulness | 0,27 | 0,79 |
| Antwortzeit Median | 4,0 s | 47,3 s |

RAG-Effekt (Vel): 54 besser, 6 schlechter, 32 gleich; Vorzeichentest p ≈ 10⁻¹⁰. Retrieval: Recall@1 0,72, Recall@4 0,89, MRR 0,79.
Vel – Gemma: κ 0,69 (ohne) / 0,65 (mit RAG), 85–89 % gleich (in jamovi bestätigt). Q101–Q300 und Bewertung 2 offen.

## Nächste Schritte

- Bewertung 2 (Prof. Zinn) über das verblindete Bewertungsexemplar; `lauf300.sh zusammen`.
- Q101–Q300: `bash skripte/laeufe/lauf300.sh alles` (setzt fort).
- Studie 2 (Hinweise): Rubrik mit vier Prüfpunkten und geschütztem Kern (Folien 4–6, Vorschlag „Hint and Feedback Evaluation“), danach finale Hinweisversion (separater Hinweisschritt mit expliziter Planung) entwickeln, einfrieren, auf 50 Fragen bewerten.
