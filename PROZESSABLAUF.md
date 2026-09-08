# Prozessablauf — KI-Lernassistent





## 1. Wissensbasis-Aufbau (offline, vor der Studie)

Wird über `admin_app.py` (Weboberfläche, Port 8502) oder
`baue_wissensbasis.py` (Kommandozeile) ausgeführt — **nicht** Teil der
Studien-App selbst (siehe `Design_Entscheidungen_Literatur.md`, Punkt 4).

```
                        PDF hochladen
                              │
                              ▼
                ┌───────────────────────────────┐
                │ Kapitel-Zuordnung              │
                │ (aus PDF-Gliederung, sonst      │
                │  Dateiname als Fallback)        │
                └───────────────┬─────────────────┘
                                │
                                ▼
                ┌───────────────────────────────┐
                │ Seitenweise Textextraktion      │
                └───────────────┬─────────────────┘
                                │
                                ▼
                ┌───────────────────────────────┐
                │ Semantisches Chunking           │
                │ + Überlappung (Modran 2025)     │
                └───────────────┬─────────────────┘
                                │
                                ▼
                      knowledge_base.json
                (atomar geschrieben, siehe
                 sichere_json_schreiben())
```

**Relevante Funktionen** (`rag_pipeline.py`): `lese_pdf_gliederung()`,
`thema_fuer_seite()`, `verarbeite_pdf_seitenweise()`,
`chunke_text_semantisch()`, `_gruppen_zu_chunks()` (Überlappung),
`sichere_json_schreiben()`.

---

## 2. Studien-App — Ablauf pro Frage (live, während der Studie)

```
                          Frage stellen
                                │
                                ▼
                ┌───────────────────────────────┐
                │ Retrieval                       │
                │ Embedding-Modell:                │
                │ paraphrase-multilingual-         │
                │ MiniLM-L12-v2                    │
                │ top_k = 4, Kosinus-Ähnlichkeit   │
                └───────┬───────────────┬─────────┘
                        │               │
             Score < 0.35        Score ≥ 0.35
             (RELEVANZ_SCHWELLE)  (RELEVANZ_SCHWELLE)
                        │               │
                        ▼               ▼
        ┌───────────────────────┐   ┌───────────────────────────┐
        │ Ehrliche Verweigerung │   │ Scaffolding-Antwort         │
        │ (keine Quelle über     │   │ Hinweis → Erklärung →       │
        │  Schwelle, kein         │   │ Lösung                      │
        │  LLM-Aufruf)             │   │ Modell: Qwen3.5:9b (Ollama) │
        │                          │   │ think = False               │
        └───────────┬─────────────┘   └─────────────┬───────────────┘
                    │                               ▼
                    │                 ┌───────────────────────────┐
                    │                 │ Sicherheitsprüfung          │
                    │                 │ Schlüsselwortbasiert         │
                    │                 │ (9 Begriffe, z. B. "Strom",  │
                    │                 │  "Gefahr", "Not-Aus")        │
                    │                 └─────────────┬───────────────┘
                    │                               ▼
                    │                 ┌───────────────────────────┐
                    │                 │ Protokollierung (CSV)       │
                    │                 │ inkl. scaffolding_stufe_    │
                    │                 │ erreicht (1-3)               │
                    │                 └─────────────┬───────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                            TAM-Fragebogen
                    (10 Items, 5-Punkte-Likert,
                     erreichbar über "Zur Bewertung →"
                     nach mind. einer Frage)
```

### Technische Details je Schritt

| Schritt | Funktion (`rag_pipeline.py`) | Parameter / Werte |
|---|---|---|
| Retrieval | `retrieval()` | **Embedding-Modell:** `paraphrase-multilingual-MiniLM-L12-v2`<br>**top_k:** 4<br>**Ähnlichkeitsmaß:** Kosinus-Ähnlichkeit |
| Relevanz-Prüfung | `beantworte_frage()`, `RELEVANZ_SCHWELLE` | Schwellenwert: **0.35** — darunter keine Generierung, nur Verweigerung |
| Scaffolding-Generierung | `baue_scaffolding_prompt()`, `frage_llm()` | **LLM:** `qwen3.5:9b` via Ollama<br>`think = False` (kein sichtbares Reasoning)<br>Ein Aufruf liefert alle 3 Stufen (Marker-Format) |
| Parsing der Stufen | `parse_scaffolding_antwort()` | Fallback: komplette Rohantwort als "Lösung", falls Format nicht eingehalten |
| Sicherheitsprüfung | `sicherheitspruefung()`, `SICHERHEITS_SCHLUESSELWOERTER` | 9 Schlüsselwörter: spannung, strom, not-aus, gefahr, schutzausrüstung, psa, druckluft, sicherheitsregel, fehlerstrom |
| Protokollierung | `protokolliere_interaktion()` | Schreibt `evaluationsdaten/interaktionen.csv`; wird bei jedem Scaffolding-Klick erneut aufgerufen (Uptake-Messung) |
| Fragebogen | `FRAGEBOGEN_ITEMS`, `speichere_fragebogen()` | **10 Items:** PU (2), PEOU (2), Trust (3), Scaffolding (2), ITU (1) — TAM nach Davis (1989) |


---


