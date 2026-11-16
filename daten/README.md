# daten/

Nicht im Repository enthalten (die Buchinhalte sind urheberrechtlich geschützt; Fragensätze und Bewertungen sind Studiendaten).
Erwartete Struktur:

| Pfad | Inhalt | Verwendet von |
|---|---|---|
| `quellen/fischer/*.pdf`, `quellen/boege/*.pdf` | Fachbücher | Aufbau der Wissensbasis |
| `wissensbasen/knowledge_base_fischer_boege_v7r.json` | Wissensbasis, 8.805 Abschnitte (Fingerabdruck c2742e8c278f) | App, alle Läufe |
| `testfragen/fragen300.csv` | 300 Testfragen (ID, Typ, Buch, Seite, Frage, …) | Studie 1 |
| `testfragen/gold300.json` | Text der hinterlegten Buchseite je Frage | `rang300.py` |
| `testfragen/kriterien300.json`, `testfragen/richter_beispiele.json` | Bewertungskriterien und Beispiele für den lokalen Richter | `richter300.py` |
| `boegen/Fragen300_Bewertung.xlsx` | Leerer Bewertungsbogen | `fuelle300.py` |

Ebenfalls Studiendaten und nicht enthalten: `bewertung/antworten/judge_input.json` und `bewertung/hinweise/hint_input.json` (Eingaben der Modellbewertungen).
