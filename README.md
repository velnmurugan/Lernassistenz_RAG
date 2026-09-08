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
