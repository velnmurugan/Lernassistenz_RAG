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
