# KI-Lernassistent — Studien-Prototyp (Phase 2, Pilotstudie)

Überarbeitete Version für die kontrollierte Evaluation mit Auszubildenden.

**Weitere Dokumente in diesem Projekt:**
- `PROZESSABLAUF.md` — der tatsächliche Ablauf als ASCII-Flowchart, wird
  bei jeder strukturellen Änderung mit aktualisiert.
- `Design_Entscheidungen_Literatur.md` — jede wesentliche Design-
  Entscheidung mit Literaturbezug begründet (14 Punkte).

> **Hinweis zur Pflege:** Diese README wird bei jeder funktionalen
> Änderung am Projekt mit aktualisiert — sie soll immer den tatsächlichen
> aktuellen Stand zeigen, nicht einen veralteten Planungsstand.

---

## Was das System aktuell kann

- **Wissensbasis aus echten PDFs** — automatische Kapitel-Zuordnung aus
  der PDF-Gliederung (Bookmarks), sonst Dateiname als Fallback.
- **Automatisches, inhaltsbasiertes Chunking** — Chunk-Grenzen werden
  über Embedding-Ähnlichkeit zwischen Sätzen bestimmt, nicht über eine
  geratene feste Satzanzahl. Zusätzlich Überlappung zwischen benachbarten
  Chunks (Modran 2025), damit Fakten an Chunk-Grenzen nicht verloren
  gehen.
- **Embeddings-Retrieval** (`top_k = 4`) — kein TF-IDF mehr im
  Studien-Prototyp (siehe `Design_Entscheidungen_Literatur.md`, Punkt 2).
- **Ehrliche Verweigerung** statt Raten, wenn kein Chunk über der
  Relevanz-Schwelle liegt.
- **Pädagogisches Scaffolding**: Antworten werden in drei Stufen
  generiert — Hinweis → Erklärung → Lösung — und im Interface
  schrittweise freigeschaltet, statt sofort vollständig gezeigt zu
  werden (Happe et al. 2025, Modran 2025).
- **Sicherheitsprüfung** (schlüsselwortbasiert) auf jede Antwort.
- **Automatisierte Protokollierung**: jede Interaktion inkl. erreichter
  Scaffolding-Stufe (Uptake-Maß, vgl. Neagu et al. 2026), jeder
  ausgefüllte Fragebogen.
- **TAM-basierter Abschlussfragebogen** (Davis 1989) inkl. Trust- und
  Scaffolding-spezifischer Items.
- **Pseudonymisierte Sitzungs-IDs** statt Klarnamen.
- **Admin-Tool für den Wissensbasis-Aufbau** — per Skript oder
  Weboberfläche, mit Vorschau vor dem Speichern und atomarem Schreiben
  (verhindert eine leere/kaputte `knowledge_base.json` bei einem
  abgebrochenen Schreibvorgang).

## Was bewusst NICHT Teil der Studien-App ist

- **Kein Live-PDF-Upload durch Proband:innen** — alle Teilnehmenden
  nutzen dieselbe, vorab erzeugte Wissensbasis (interne Validität, siehe
  `Design_Entscheidungen_Literatur.md`, Punkt 4).
- **Kein TF-IDF-Vergleich, keine sichtbaren Retrieval-Scores, kein
  "Was sind Embeddings?"-Tab** — das waren Kolloquium-Demo-Features für
  ein technikfremdes Publikum, kein Teil des zu evaluierenden Werkzeugs.

---

## Wissensbasis aus deinen eigenen PDFs erzeugen

Das mitgelieferte `knowledge_base.json` ist sorgfältig erstellter
Platzhalterinhalt (21 Chunks, 7 Themen) — KEIN echtes Curriculum. So
ersetzt du es durch deine eigenen Materialien:

### Option A: per Skript (`baue_wissensbasis.py`)

```
1. PDF-Dateien in den Ordner quellmaterial/ legen
2. python baue_wissensbasis.py
   -> erkennt automatisch Kapitel aus der PDF-Gliederung (falls vorhanden,
      sonst Dateiname als Fallback), extrahiert Text seitenweise, chunked
      automatisch mit Überlappung, fragt vor dem Überschreiben nach,
      schreibt knowledge_base.json atomar neu
```

### Option B: per Weboberfläche (`admin_app.py`)

```
streamlit run admin_app.py --server.port 8502 --server.fileWatcherType none
```

Läuft bewusst auf einem **anderen Port** (8502 statt 8501) als die
Studien-App, damit Studierende die Admin-Oberfläche nie sehen. Dort
kannst du PDFs hochladen, die erkannten Kapitel und eine Chunk-Stichprobe
vor dem Speichern prüfen, und wählen, ob die vorhandene Wissensbasis
ersetzt oder ergänzt wird.

**Wichtig:** Weder Skript noch Admin-Tool laufen innerhalb der
Studien-App und werden nicht durch Proband:innen ausgeführt.

---

## Setup

```
conda activate pilot_rag          # oder dein vorhandenes Environment
pip install -r requirements.txt
```

Ollama muss laufen (Modell `qwen3.5:9b`).

## Starten

```
streamlit run app.py --server.fileWatcherType none
```

## Ablauf für Proband:innen

1. **Start-Seite**: Hinweise lesen, Sitzungs-ID eingeben, Einverständnis
   bestätigen.
2. **Chat**: beliebig viele Fragen stellen. Jede Antwort erscheint
   zunächst nur als Hinweis; über "Mehr Hilfe" lässt sich schrittweise
   die Erklärung und die vollständige Lösung freischalten.
3. **Fragebogen**: über den Button "Zur Bewertung →" erreichbar — 10
   TAM-basierte Items (5-Punkte-Likert) plus optionales Freitextfeld.
4. **Abschluss**: Bestätigungsseite.

Der vollständige technische Ablauf steht bildlich in `PROZESSABLAUF.md`.

## Wo liegen die Evaluationsdaten?

Wird beim ersten Durchlauf automatisch erstellt:

```
evaluationsdaten/
  interaktionen.csv   # Frage, Antwortstufen, erreichte Scaffolding-Stufe,
                       # Quellen, Sicherheitshinweis, Zeitstempel
  fragebogen.csv      # ausgefüllte Fragebögen pro Sitzungs-ID
```

Beide Dateien lassen sich direkt in Excel/SPSS/R öffnen (eine Zeile pro
Interaktion bzw. pro Fragebogen). Da jede Scaffolding-Stufe, die
angeklickt wird, erneut protokolliert wird, ergibt `MAX(scaffolding_
stufe_erreicht)` pro Frage die tatsächliche Scaffolding-Uptake-Rate.

## Verfügbare Themen in der (Platzhalter-)Wissensbasis

Elektrische Sicherheit · SPS Grundlagen · Sensorik · Regelungstechnik ·
Arbeitssicherheit Werkstatt · Wartung und Instandhaltung · Pneumatik

## Bekannte offene Punkte (siehe auch Ausblick-Folie)

- Formale Ethikfreigabe vor Einsatz mit echten (insbesondere
  minderjährigen) Lernenden noch ausstehend.
- Relevanz-Schwelle (0.35) und Ähnlichkeits-Schwelle für das Chunking
  (0.55) sind Startwerte, nicht aus einer größeren Stichprobe kalibriert.
- Sicherheitsprüfung ist weiterhin schlüsselwortbasiert, kein echter
  Klassifikator.
- Überlappung zwischen Chunks wirkt nur innerhalb einer Seite, nicht
  über Seitengrenzen hinweg.
- Ein einzelner LLM-Aufruf liefert alle drei Scaffolding-Stufen; wie
  zuverlässig das Modell dieses Format tatsächlich einhält, ist noch
  nicht systematisch erhoben (siehe `Design_Entscheidungen_Literatur.md`,
  Punkt 13).

Details und Quellenangaben zu jeder Entscheidung: siehe
`Design_Entscheidungen_Literatur.md`.

## V19b (29 Oct 2026)
V19b (29 Oct 2026) – Schalter LERNASSISTENT_V19 (Standard: aus)
  A = Formelsuche vorab (formelsuche.py, rag_pipeline.py)
  B = Parser-Korrekturen der Nachrechnung (rechenbaustein.py): (1) Hochzahl an einer Einheit ("kg*m**2") gehört zur Einheit;
      (2) nicht auswertbare RECHNUNG-Zeile wird übersprungen, wenn ihre Größe weder Ergebnis noch in einem späteren Schritt gebraucht wird.
  Aufruf: LERNASSISTENT_V19=AB (beide) oder A. Lauf: bash skripte/evaluation/nachtlauf_v19b.sh [AB|aus|beide]
  Test: teste_v19b_offline.py. Kurzlauf: kurzlauf_v19a.sh [A|AB|aus] (Modus nur als Argument).

## V19c (29 Oct 2026)
V19c (29 Oct 2026) – Ziffer „1“ in LERNASSISTENT_V19 (z. B. AB1): die Formelsuche vorab (V19a) ergänzt nur 1 statt 2 Formel-Chunks (formelsuche.V19_ZUSATZ).
  Grund: Im Lauf AB gegen aus änderten die zusätzlichen Chunks bei F4, RV-v2 R05 und RV-v1 R04 schon die erste Antwort (Verluste). Frage: Behält 1 Chunk die Gewinne?
  Test: teste_v19c_offline.py. Lauf: bash skripte/evaluation/nachtlauf_v19c.sh [kern|voll]

## Faithfulness mit und ohne Retrieval (29 Oct 2026)
Faithfulness mit und ohne Retrieval (29 Oct 2026): skripte/evaluation/faithfulness_rag_vs_ohne.py, Lauf skripte/laeufe/faithfulness_lauf.sh [probe].
  Bewertet werden die 95 beantwortbaren N100-Fragen (V11B-Antworten mit Retrieval; Antworten ohne Retrieval, Prompt O-v1) mit demselben Richter (mistral-nemo, J-v1)
  gegen dieselben vier abgerufenen Textabschnitte. Ergebnis: evaluationsdaten/faithfulness_rag_vs_ohne_V11B*.csv/.txt. Nur Pilotfragen, Richter nicht validiert.

## Freeze-Lauf N100 (29 Oct 2026)
Ziel: Prüfen, ob die Rechenpfad-Varianten "aus" (V18=ADEK, V19 aus) und "AB" (V19=AB) auf allen 100 Fragen stabil sind; V11B bleibt Referenz bis zur Entscheidung.
Läufe: N100 (70 Fischer + 30 Böge) mit und ohne Retrieval je Variante (Labels V19AUS, V19AB); RV-v1 (22 Fragen) je Variante als Reproduzierbarkeitskontrolle gegen die früheren Läufe.
Auswertung: vergleich_laeufe_n100.py (Antwort für Antwort gegen V11B, Liste geänderter Antworten zur Handbewertung), Faithfulness (V11B als Basis; identische Antworten übernommen, Stichprobenkontrolle), RAGAS Answer-/Context-Relevance.
Entscheidungsregel (vorab festgelegt): Eine Variante wird eingefroren, wenn nach Handbewertung der geänderten Antworten keine Verschlechterung gegenüber V11B auf Nicht-Rechenfragen auftritt und die Rechenfragen nicht schlechter sind als bei der anderen Variante; sonst bleibt V11B.
Hinweis: Entwicklungs- und Pilotfragen; keine Evidenz für den Beitrag ohne unabhängigen Satz.

## Modellvergleich N100 mit der V11B-Konfiguration (30 Oct 2026)
Frage: Wie verhält sich dieselbe Pipeline (V11B: Prompt G-v4, Rechenprüfung RP-v5, Hinweisprüfung HP-v4, Formelsuche aus, Retrieval hybrid_kg_rr mit Reranker, KB v7r), wenn nur das Generator-Modell gewechselt wird?
Modelle (Ollama): qwen3.5:4b (3,3 GB), gemma4:e4b-it-qat (6,1 GB, Standard), gemma4:12b-it-qat (7,2 GB, optional), optional gpt-oss:20b (13 GB, Mixture-of-Experts; nur mit genug RAM). Referenz: qwen3.5:9b (gespeicherter Lauf V11B).
Unverändert: Embedding (MiniLM), BM25, Konzeptgraph, Reranker bge, Gate 0,35, T = 0, Seed 42; Richter für Faithfulness bleibt mistral-nemo (kein Generator-Modell ist Richter).
Technik: Patch M-v1 in rag_pipeline.py (idempotent): LERNASSISTENT_MODELL, LERNASSISTENT_THINK (aus | low | medium | high | ohne), LERNASSISTENT_TIMEOUT; Standardverhalten unverändert (qwen3.5:9b, think=False, 120 s). Antwortet Ollama mit HTTP 400 auf think, wird einmal ohne think wiederholt.
Kontrolle vor den Modellläufen: qwen3.5:9b mit der festgenagelten V11B-Umgebung auf den ersten 8 Fischer-Fragen gegen den gespeicherten V11B-Lauf (Abbruch bei weniger als 3 identischen Antworten, GATE=weiter überspringt).
Läufe: N100 (70 Fischer + 30 Böge) mit und ohne Retrieval je Modell, Labels V11BQWEN4B, V11BGEMMA12, V11BGPTOSS20. Auswertung: modell_kennzahlen.py (Status, Ablehnungen, Format, Denkreste, Sprache, Zeit), vergleich_laeufe_n100.py (Antwort für Antwort gegen V11B), Antwortbogen zur Handbewertung, optional Faithfulness (V11B als Basis).
Grenzen: Entwicklungs- und Pilotfragen; Richtigkeit nur per Handbewertung; die Rechenprüfung RP-v5 ist auf das Ausgabeformat von qwen3.5 abgestimmt, bei anderen Modellen können Formatfehler (Status ungeprueft/markiert) auftreten, das ist ein Befund und kein Pipeline-Fehler; Laufzeiten hängen vom GPU/CPU-Anteil ab (8 GB VRAM).

## Vorab-Prüfsatz V1 (30 Oct 2026)
Vorab-Prüfsatz V1 (30 Oct 2026): 100 frische Fragen (50 Fischer, 50 Böge) aus den Original-PDFs, ohne Überschneidung mit bisherigen Sätzen. Lauf mit V11B (G-v4, RP-v5, FS=aus, qwen3.5:9b, KB v7r) über skripte/laeufe/vorabsatz_lauf.sh; Ergebnisse in evaluationsdaten/ (testlauf_retrieval_VORAB*, vergleich_rag_RAGVGL-VORAB*). Privat, kein Beleg im Beitrag; nichts auf diesem Satz abstimmen.

## Hinweis-Dialogtest HD-V2
Hinweis-Dialogtest HD-V2 (30 Oct 2026): N100 (70 Fischer + 30 Böge), V11B eingefroren. Je Frage bis zu 3 Versuche: simulierte Lernende (anderes Modell, ca. 30 % richtig), Rückmeldung IF-v5, Folgehinweis HD-v2; Rubrik P1-P6 / R1-R4 durch einen Richter (kein Generator), Bewertungsbogen für zwei Menschen. Skript skripte/evaluation/teste_hinweis_dialog.py; Ergebnisse evaluationsdaten/hinweis_dialog_HD-V2_*. Kein Beleg im Beitrag ohne Abgleich Richter gegen Menschen.

## Hinweis-Optimierung HO-V1
Hinweis-Optimierung HO-V1 (31 Oct 2026): Replay der 143 Hinweis-Situationen aus HD-V2; Varianten Basis, Wächter (Leck-Prüfer mit Neufassung), Prompt H-v4 (Lösungsbausteine, ein Ziel, Formregeln P1-P6) und Kombination; Leck-Prüfer vorher gegen Referenzurteile kalibriert. Vorläufige Empfehlung nach Leck-Rate: V1. Skript skripte/evaluation/optimiere_hinweise.py; Ergebnisse evaluationsdaten/hinweis_opt_HO-V1_*. Entwicklungsbefund, kein Beleg im Beitrag; Bewertungsbogen für zwei Menschen liegt bei.

## Stabilität Hinweise HS-V1
Stabilität der Hinweis-Erzeugung HS-V1 (31 Oct 2026): Teil A prüft, ob neu erzeugte Basis-Hinweise bei T=0/Seed 42 den gespeicherten gleichen (direkt, mit anderer Situation, mit Modellwechsel dazwischen) und wie stabil die Leck-Prüfer sind; Teil B erzeugt Basis und Basis+Wächter in mehreren Runden (T0 und Temperatur 0.3) und vergleicht den Unterschied mit dem Rauschen. Skript skripte/evaluation/teste_hinweis_stabilitaet.py; Ergebnisse evaluationsdaten/hinweis_stab_HS-V1_*. Entwicklungsbefund, kein Beleg im Beitrag.
