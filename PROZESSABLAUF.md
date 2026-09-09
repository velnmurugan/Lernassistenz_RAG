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

# Prompt-zu-Prinzip-Mapping — `baue_scaffolding_prompt()`

---

## 1. Rollen- und Grounding-Rahmen (vor den drei Stufen)

| Prompt-Text (Auszug) | Zugeordnetes Prinzip | Quelle | Empirisch geprüft? |
|---|---|---|---|
| "Du bist ein Lernassistent für die technische und berufliche Bildung." | Rollen-/Persona-Framing (allgemeine Systemkonzept-Grundlage) | — (kein spezifisches Zitat nötig, operationale Festlegung) | n/a |
| "Beantworte die folgende Frage NUR auf Basis des gegebenen Kontexts." | Grounding-Prinzip von RAG-Systemen | Lewis et al. (2020) | Teilweise — funktioniert bei vollständig fehlender Retrieval-Relevanz (siehe RELEVANZ_SCHWELLE-Gate), aber bei *partieller* Relevanz beobachtet: Modell extrapoliert über den Kontext hinaus, ohne dies zu kennzeichnen (Live-Test "Datenleitungen/CNC", ungehedgte Aussagen zu "Produktivitätssteigerung", "Tippfehler-Risiko" — nicht explizit im Quellmaterial). **Validierungslücke.** |
| "Wenn der Kontext die Frage nicht ausreichend beantwortet, sage das ehrlich... anstatt zu raten." | "Tug-of-War"-Gegenmaßnahme: Modell soll internes Wissen nicht über Retrieval-Evidenz stellen | Oche et al. (2025) | Bestätigt bei vollständiger Irrelevanz (Live-Test "anorganische Verbindungen" — korrekte, transparente Ablehnung). **Nicht bestätigt** bei partieller Relevanz (siehe oben). |

## 2. Grounding-Gate vor dem LLM-Aufruf (kein Prompt-Text, aber Teil derselben Pipeline-Stufe)

| Mechanismus | Zugeordnetes Prinzip | Quelle | Empirisch geprüft? |
|---|---|---|---|
| `RELEVANZ_SCHWELLE = 0.35` (Retrieval-Score-Gate vor Generierung) | Refuse-over-guess als zentrale Sicherheitsmaßnahme | Oche et al. (2025) | Schwellenwert bisher **nicht kalibriert** (eigener Docstring-Hinweis: "Startwert, kein empirisch kalibrierter Wert") — offener Punkt für Methodenteil. |
| `top_k=4` (statt z. B. 2) | Retrieval-Vollständigkeit — Gegenmaßnahme gegen Verdrängung kurzer Fakten durch verwandte Prosa | Eigener Testbefund (Phase 1, ECTS-Beispiel) + indirekt Reimers & Gurevych (2019) für Embedding-Qualität als Voraussetzung | Ursprünglicher Befund dokumentiert, aber **kein systematischer Vergleich** top_k=2 vs. 4 vs. 6 durchgeführt — Ablation fehlt noch. |

## 3. Die drei Scaffolding-Stufen

| Stufe / Prompt-Text (Auszug) | Zugeordnetes Prinzip | Quelle | Empirisch geprüft? |
|---|---|---|---|
| Gesamtstruktur: drei aufeinander aufbauende, klar markierte Stufen | Scaffolding-Grundkonzept; konkret: Hint/Explanation/Solution als getaggte Abschnitte | Ursprung des Scaffolding-Konzepts: Wood, Bruner & Ross (1976) — **fehlt bisher als Zitat im Code**, sollte ergänzt werden. Konkrete 3-Stufen-Umsetzung: Happe et al. (2025) — dort autor:innen-vorautoriert, hier dynamisch promptet (bewusste, dokumentierte Abweichung) | Format wird vom Modell meist eingehalten (`vollstaendig_geparst=True` im Regelfall, siehe Fallback-Logik) — Formathaltungsrate selbst aber **nicht systematisch gemessen** (offener Punkt, bereits in eigener Doku vermerkt). |
| **STUFE1_HINWEIS**: "kurzer Hinweis... OHNE die Antwort direkt zu verraten. Soll zum eigenen Nachdenken anregen." | Selbsterklärungseffekt — Lernende müssen die kognitive Arbeit selbst leisten, Hinweis darf die Erklärung nicht vorwegnehmen | Chi (1989, 2000, 2009) | **Widerlegt in Live-Test** (Fototransistor-Frage): Hinweis nannte bereits den Kernmechanismus ("größere Kapazität zwischen Kollektor und Basis") — verletzt das eigene Prinzip. **Konkrete Fixaufgabe.** |
| **STUFE2_ERKLAERUNG**: "ausführlichere Erklärung... die der Antwort schon näherkommt, aber noch nicht die vollständige... Antwort ist" | Gestuftes Hinting (vereinfachte, nicht-kontinuierliche Variante eines adjustierbaren hinting_level) | Modran (2025) | Im selben Live-Test **zu geringe Differenzierung** gegenüber Hinweis UND Lösung beobachtet — die drei Stufen waren inhaltlich stark redundant. **Konkrete Fixaufgabe.** |
| **STUFE3_LOESUNG**: "vollständige, direkte Antwort... verständlich auf dem Niveau von Auszubildenden erklärt" | Reduktion extraneous load durch niveaugerechte Sprache | Sweller (1988, 2010); Chandler & Sweller (1991) | Sprachliches Niveau bisher nur subjektiv/anekdotisch beurteilt, **keine systematische Prüfung** (z. B. Lesbarkeitsindex, Fachbegriffsdichte). |
| "Halte dich EXAKT an dieses Format mit allen drei Markern." | **Kein pädagogisches Prinzip** — reine Pipeline-Notwendigkeit für `parse_scaffolding_antwort()` | — | Ehrlich als technische Instruktion zu kennzeichnen, nicht als didaktisches Design-Prinzip misszuverstehen. |

## 4. Flankierende Pipeline-Entscheidungen (außerhalb des Prompt-Texts selbst)

| Mechanismus | Zugeordnetes Prinzip | Quelle | Empirisch geprüft? |
|---|---|---|---|
| `think=False` bei Ollama-Aufruf | Antwortzeit als Usability-Faktor (Perceived Ease of Use) | Davis (1989), TAM | Nicht separat gemessen (kein A/B-Vergleich think=True vs. False), aber plausibel begründet. |
| Embedding-Retrieval statt TF-IDF | Bedeutungserfassung statt Wortoberfläche; bessere Handhabung deutscher Wortformvarianten | Reimers & Gurevych (2019) + eigener Testbefund ("einfachwirkenden" vs. "einfachwirkender") | Ursprünglicher TF-IDF-Vergleich dokumentiert (Phase 1) — **kein quantifizierter Vorher-Nachher-Vergleich** der Retrieval-Genauigkeit. |
| `sicherheitspruefung()` (Keyword-Matching) | Systemkonzept-Säule "Sicherheit" | Bisher **kein spezifisches Zitat** — als "bewusst einfache Version für Phase 1/2" im Code selbst gekennzeichnet, echter Klassifikator für Phase 3 vorgesehen | **Falsch-Positiv bereits dokumentiert** ("Drehstrom" via "strom") + neu bestätigt in Live-Test ("Spannung" im Fotodioden-Kontext). Konkrete Fixaufgabe (Wortgrenzen + Kontext-Whitelist, siehe separate Code-Vorschläge). |

---

## Zusammenfassung für den Methodenteil

Von den 10 zitierten Design-Entscheidungen sind:
- **2 durch Live-Tests bestätigt** (Grounding-Refusal bei vollständiger Irrelevanz; Wortformvarianten-Vorteil von Embeddings gegenüber TF-IDF, historisch)
- **3 durch Live-Tests widerlegt oder als Lücke identifiziert** (Selbsterklärungseffekt im Hinweis verletzt; Stufen-Redundanz; Grounding bei partieller Relevanz nicht gekennzeichnet)
- **5 bisher nur als Designabsicht dokumentiert, ohne systematische Prüfung** (Schwellenwert-Kalibrierung, top_k-Ablation, Formathaltungsrate, Sprachniveau-Prüfung, think=False-Wirkung)

Diese Aufstellung selbst — insbesondere die Spalte "Empirisch geprüft?" — ist der entscheidende Unterschied zur rezensierten JOTED-Einreichung: dort wurden Design-Prinzipien zitiert und behauptet, aber nie gegen das tatsächliche Modellverhalten geprüft. Eine solche Tabelle (ggf. mit systematischerer Stichprobe statt Ad-hoc-Tests) wäre ein eigenständiger, publizierbarer Beitrag zum Methodenteil.

---


