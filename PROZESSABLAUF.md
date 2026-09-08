# Prozessablauf — KI-Lernassistent

> **Wichtig:** Diese Datei bei jeder strukturellen Änderung an `app.py`,
> `rag_pipeline.py` oder `admin_app.py` mit aktualisieren — z. B. wenn ein
> Verarbeitungsschritt hinzukommt, wegfällt oder sich die Reihenfolge
> ändert. Ziel: Diese Datei zeigt IMMER den tatsächlichen, aktuellen
> Ablauf des Systems, nicht einen veralteten Planungsstand.
>
> Bewusst als reiner ASCII-Text gehalten — lesbar in jedem Editor, ohne
> Mermaid- oder Markdown-Renderer nötig.

---

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
                │ Retrieval (Embeddings)          │
                │ top_k = 4                       │
                └───────┬───────────────┬─────────┘
                        │               │
             Score < Schwelle   Score ≥ Schwelle
                        │               │
                        ▼               ▼
        ┌───────────────────────┐   ┌───────────────────────────┐
        │ Ehrliche Verweigerung │   │ Scaffolding-Antwort         │
        │ (keine Quelle über     │   │ Hinweis → Erklärung →       │
        │  Schwelle)              │   │ Lösung                      │
        └───────────┬─────────────┘   └─────────────┬───────────────┘
                    │                               ▼
                    │                 ┌───────────────────────────┐
                    │                 │ Sicherheitsprüfung          │
                    │                 └─────────────┬───────────────┘
                    │                               ▼
                    │                 ┌───────────────────────────┐
                    │                 │ Protokollierung (CSV)       │
                    │                 └─────────────┬───────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                            TAM-Fragebogen
                    (erreichbar über "Zur Bewertung →"
                     nach mind. einer Frage)
```

**Relevante Funktionen** (`rag_pipeline.py`): `retrieval()`,
`RELEVANZ_SCHWELLE`, `baue_scaffolding_prompt()`,
`parse_scaffolding_antwort()`, `sicherheitspruefung()`,
`protokolliere_interaktion()` (inkl. `scaffolding_stufe_erreicht` für
Uptake-Messung, siehe Neagu et al. 2026), `FRAGEBOGEN_ITEMS`.

---

## Änderungsprotokoll

Jede strukturelle Änderung hier kurz eintragen, damit nachvollziehbar
bleibt, wann und warum sich der Ablauf verändert hat.

| Datum | Änderung | Betroffene Datei(en) |
|---|---|---|
| 2026-09-01 | Grundstruktur: Wissensbasis-Aufbau + Frage-Antwort-Ablauf dokumentiert | `rag_pipeline.py`, `app.py`, `admin_app.py` |
| 2026-09-02 | Scaffolding (Hinweis/Erklärung/Lösung) eingeführt | `rag_pipeline.py`, `app.py` |
| 2026-09-03 | Section-aware Chunking (Gliederungserkennung), Überlappung, atomares Schreiben ergänzt | `rag_pipeline.py`, `admin_app.py`, `baue_wissensbasis.py` |
| 2026-09-04 | Von farbigen Mermaid-Diagrammen auf reines ASCII umgestellt | `PROZESSABLAUF.md` |
| | | |
