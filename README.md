# Lernassistent – RAG-basierter Lernassistent für die berufliche Bildung

Lokaler Lernassistent (qwen3.5:9b über Ollama), der Fragen aus zwei Fachbüchern (Fischer, *Elektrotechnik für Maschinenbauer*; Böge, *Handbuch Maschinenbau*) beantwortet: hybride Suche (Dense, BM25, Begriffsgraph, Reciprocal Rank Fusion, Cross-Encoder), Relevanzschwelle, gestufte Antwort (Hinweis vor der Lösung), Formelsuche und Rechenprüfung für Rechenaufgaben, Hinweisprüfung. Dieses Dokument ist die technische Dokumentation: Code, Prompts, Parameter und Einstellungen.

## Inhalt

1. [Zweck und Geltungsbereich](#1-zweck-und-geltungsbereich)
2. [Entwicklungs- und Testumgebung](#2-entwicklungs--und-testumgebung)
3. [Übersicht über den Code](#3-übersicht-über-den-code)
4. [Versionsschalter des Stands V20](#4-versionsschalter-des-stands-v20)
5. [Wissensbasis](#5-wissensbasis)
6. [Antwortweg einer Frage](#6-antwortweg-einer-frage)
7. [Formelsuche und Rechenprüfung](#7-formelsuche-und-rechenprüfung-nur-rechenfragen)
8. [Hinweisprüfung (HP-v4)](#8-hinweisprüfung-hp-v4)
9. [Gestufte Lerninteraktion in der App](#9-gestufte-lerninteraktion-in-der-app)
10. [Studie 1: Antworten](#10-studie-1-antworten)
11. [Studie 2: Hinweise](#11-studie-2-hinweise)

## Installation

```bash
conda create -n lernassistent python=3.11 && conda activate lernassistent
pip install -r requirements.txt
ollama pull qwen3.5:9b      # Generator
ollama pull gemma4:12b      # lokaler Richter / Faithfulness
ollama pull qwen2.5vl:7b    # Bildbeschreibungen (nur Aufbau der Wissensbasis)
```

Hugging-Face-Modelle (werden beim ersten Aufruf geladen; die Startskripte setzen danach `HF_HUB_OFFLINE=1`): `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, `BAAI/bge-reranker-v2-m3`, `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`. MinerU 3.4.5 läuft in einer eigenen conda-Umgebung `mineru` (Befehl über `MINERU_BEFEHL`) und wird nur für den Aufbau der Wissensbasis gebraucht.

API-Schlüssel nur als Umgebungsvariablen: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`. Daten (Bücher, Wissensbasis, Testfragen, Bewertungen) sind nicht enthalten, siehe `daten/README.md`.

## Start

```bash
bash skripte/laeufe/start_demo.sh                                    # Lern-App, Port 8501
streamlit run admin_app.py --server.port 8502 --server.fileWatcherType none
bash skripte/laeufe/lauf300.sh einrichten                            # Studie 1: Dateien und Schalter prüfen
bash skripte/laeufe/lauf300.sh alles                                 # Bedingungen A/B, Rang, Richter, Faithfulness
python skripte/evaluation/gpt300.py                                  # Bedingung C
bash skripte/laeufe/lauf_gpt_rag300.sh alles                         # Bedingung D
python -u skripte/evaluation/faith1200.py                            # Faithfulness aller Bedingungen
python bewertung/antworten/judge.py --provider gemini                # Modellbewertungen (auch: mistral)
python bewertung/hinweise/hint_judge.py --provider gemini            # Studie 2 (auch: mistral)
```

Alle Läufe setzen nach einem Abbruch fort (gleicher Befehl). Ausgaben landen in `evaluationsdaten/`, `protokolle/` und `ausgabe/` (von Git ausgeschlossen).

# 1 Zweck und Geltungsbereich

Dieses Repository enthält den Lernassistenten im Stand **V20** (eingefrorene Konfiguration) und die Auswertungsskripte von Studie 1 (Antworten auf 300 Testfragen) und Studie 2 (Hinweise). Dokumentiert sind nur die **endgültigen Fassungen**, die in Studie 1 und den anschließenden Bewertungen tatsächlich verwendet wurden. Ältere Versionen (G-v1 bis G-v5, RP-v1 bis RP-v12 usw.) stehen weiterhin im Code, werden aber nur zur Reproduktion früherer Läufe gebraucht und sind hier nicht beschrieben.

Alle Prompts sind **wörtlich** wiedergegeben. Sie wurden nicht abgeschrieben, sondern direkt aus dem Code erzeugt (Aufruf der jeweiligen Funktion mit Platzhaltern). Platzhalter stehen in doppelten spitzen Klammern, z. B. `<<FRAGE>>`.

# 2 Entwicklungs- und Testumgebung

| Bereich | Einstellung |
|---|---|
| Rechner | Intel Core i7-11800H, 16 GB RAM, NVIDIA RTX 3070 mit 8 GB VRAM |
| Betriebssystem | Windows 11 mit WSL2 (Ubuntu); der Code läuft in WSL |
| Python | Python 3.11 (conda-Umgebung) |
| Sprachmodell-Server | Ollama unter Windows; aus WSL über die automatisch ermittelte Gateway-Adresse erreicht (`http://<host>:11434/api/generate`) |
| Wichtige Python-Pakete | `streamlit`, `scikit-learn`, `requests`, `sentence-transformers`, `rank_bm25`, `snowballstemmer`, `pypdf`, `numpy`, `scipy`; Extraktion mit MinerU 3.4.5 |
| Offline-Betrieb | `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` (Modelle aus dem lokalen Cache, keine Downloads während der Läufe) |
| Cloud-Dienste | Nur für die Vergleichsbedingungen C und D (OpenAI-API) und die Modellbewertungen (Google-, Mistral-API). Der Prototyp selbst nutzt keine Cloud. Schlüssel nur als Umgebungsvariablen (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`). |

# 3 Übersicht über den Code

| Datei | Aufgabe |
|---|---|
| `app.py` | Lernoberfläche (Streamlit, Port 8501) |
| `admin_app.py` | Oberfläche für Lehrkräfte und Forschende (Port 8502): Protokolle einsehen, Wissensbasis verwalten |
| `lernassistent/rag_pipeline.py` | Kern: Wissensbasis laden, Retrieval, Relevanzschwelle, Antwortprompt, Generierung, Rechenprüfung, Hinweisprüfung, Protokoll |
| `lernassistent/wissensgraph.py` | Begriffsgraph und Personalized PageRank (dritte Suchliste) |
| `lernassistent/reranker.py` | Cross-Encoder-Re-Ranking |
| `lernassistent/formelsuche.py` | Formelsuche für Rechenfragen (V19-A vor der Antwort, FS-v3 nach einem Fehlschlag) |
| `lernassistent/rechenpruefung.py` | Deterministische Prüfung der Rechenschritte in der Antwort |
| `lernassistent/rechenbaustein.py` | Unabhängige Nachrechnung (Modell stellt die Rechnung auf, Python rechnet) |
| `lernassistent/dimensionspruefung.py` | Einheiten- und Dimensionsprüfung der Nachrechnung |
| `lernassistent/ideen_feedback.py` | Rückmeldung zur eigenen Idee und deren Prüfung |
| `lernassistent/lernhilfen.py` | Anschlussfragen und Übungsfrage in der App (in der Studie nicht bewertet) |
| `lernassistent/pdf_struktur.py`, `bildbeschreibung.py` | Extraktion mit MinerU, Chunking, Bildbeschreibungen |
| `skripte/wissensbasis/*.py` | Aufbau der Wissensbasis (Struktur-Chunking, Register entfernen, Bücher zusammenführen) |
| `skripte/evaluation/antworten300.py` | Studie 1: Antworten der Bedingungen A und B |
| `skripte/evaluation/gpt300.py`, `gpt_rag300.py` | Studie 1: Antworten der Bedingungen C und D (OpenAI-API) |
| `bewertung/antworten/judge.py` | Studie 1: Modellbewertungen Gemini und Mistral |
| `bewertung/hinweise/hint_judge.py` | Studie 2: Modellbewertungen der Hinweise |
| `skripte/evaluation/rang300.py` | Rang der Buchstelle (Recall@k, MRR) |
| `skripte/evaluation/faith300.py`, `faith1200.py`, `ragas_auswertung.py` | Faithfulness |
| `skripte/laeufe/lauf300.sh`, `lauf_gpt_rag300.sh`, `start_demo.sh`, `boege_wissensbasis.sh` | Startskripte mit den V20-Schaltern |
| `statistik/R/*.R` | Abbildungen und Kennwerte der Studien (jamovi/R) |

# 4 Versionsschalter des Stands V20

Der Code enthält mehrere Versionen nebeneinander. Welche läuft, bestimmen Umgebungsvariablen, die `start_demo.sh` (App) und `lauf300.sh` (Studie) identisch setzen:

| Variable | Wert | Bedeutung |
|---|---|---|
| `LERNASSISTENT_G` | `G-v6` | Antwortprompt (Abschnitt 6.2) |
| `LERNASSISTENT_RP` | `RP-v13` | Rechenprüfung (Abschnitt 7) |
| `LERNASSISTENT_RB` | `RB-v8` | Nachrechnung mit Einheitenumrechnung und Dimensionsprüfung |
| `LERNASSISTENT_FS` | `FS-v3` | Formelsuche nach einem Fehlschlag |
| `LERNASSISTENT_V18` | `ADEK` | Zusatzregeln der Nachrechnung (Abschnitt 7.4) |
| `LERNASSISTENT_V19` | `AB` | A: Formelsuche vor der Antwort; B: Leseregeln der Nachrechnung |
| `LERNASSISTENT_CTX` | `8192` | Kontextfenster jedes Modellaufrufs (Tokens) |
| `LERNASSISTENT_RW` | leer | Rechenwerkzeug (Tool Calling) aus |
| `LERNASSISTENT_KB` | `daten/wissensbasen/knowledge_base_fischer_boege_v7r.json` | Wissensbasis |
| `LERNASSISTENT_RETRIEVAL` | `hybrid_kg_rr` | Dense + BM25 + Begriffsgraph, RRF, Cross-Encoder |
| `LERNASSISTENT_HG`, `LERNASSISTENT_THINK` | nicht gesetzt | Hinweis-Wächter aus; kein sichtbares Reasoning |
| Hinweisprüfung | `HP-v4` (im Code fest) | Abschnitt 8 |
| Rückmeldung zur Idee | `IF-v5`, Prüfung `FP-v3` (im Code fest) | Abschnitt 9 |

Die Konfigurationsdatei des Laufs bestätigt diese Einstellungen: `Generator qwen3.5:9b {'temperature': 0, 'seed': 42}; ohne RAG O-v1; mit RAG G=G-v6 RP=RP-v13 RB=RB-v8 CTX=8192; Retrieval hybrid_kg_rr; KB …v7r.json (c2742e8c278f); Fragen daten/testfragen/fragen300.csv (300)`.

# 5 Wissensbasis

## 5.1 Quellen

| Buch | Datei | Abschnitte in der Wissensbasis |
|---|---|---|
| Fischer, R. (2019). *Elektrotechnik für Maschinenbauer sowie Studierende technischer Fächer* (16. Aufl.). Springer Vieweg | Wissensbasis `knowledge_base_fischer_v7c.json` | 1.279 |
| Böge, A., & Böge, W. (Hrsg.). (2021). *Handbuch Maschinenbau* (24. Aufl.). Springer Vieweg | `knowledge_base_boege_v7b.json`, Register entfernt | 7.526 (von 7.561) |
| **Zusammen** | `knowledge_base_fischer_boege_v7r.json`, Fingerabdruck `c2742e8c278f` | **8.805** |

## 5.2 Extraktion und Chunking

| Schritt | Einstellung | Bedeutung |
|---|---|---|
| Extraktion | MinerU 3.4.5, Backend `pipeline`, Methode `-m ocr` (`mineru -p <pdf> -o <ordner> -b pipeline -m ocr`) | Layout-Erkennung, OCR, Formeln als LaTeX, Tabellen strukturiert, Abbildungen als Bildausschnitte. Der OCR-Modus wurde gewählt, weil der Textmodus Zeichen wie Ω verlor. |
| Chunking | entlang der Dokumentstruktur (`pdf_struktur.strukturchunks`) | Nummerierte Überschriften beenden einen Abschnitt und bilden den Abschnittspfad; unnummerierte Überschriften (z. B. „Beispiel 2.3“) beginnen einen neuen Abschnitt |
| `ZIEL_WOERTER` | 200 | Obergrenze je Text-Abschnitt (ca. 260 Tokens); zu lange Absätze werden an Satzgrenzen geteilt |
| `MIN_WOERTER` | 40 | Kürzere Reste werden an den vorigen Abschnitt desselben Kapitels angehängt |
| `TABELLE_MAX_WOERTER` | 300 | Lange Tabellen werden geteilt |
| Überlappung | keine | – |
| Formeln | bleiben als LaTeX beim vorangehenden Text | – |
| Tabellen, Abbildungen | eigene Abschnitte mit Überschrift bzw. Bildunterschrift | Typen: `text`, `tabelle`, `abbildung` |

## 5.3 Bildbeschreibungen

| Einstellung | Wert |
|---|---|
| Modell | `qwen2.5vl:7b` (Qwen2.5-VL-7B) über Ollama |
| Prompt | B-v3 (wörtlich unten) |
| Optionen | `temperature 0`, `seed 42`, `num_predict 300`, `repeat_penalty 1.15` |
| Bildgröße | längste Kante auf höchstens 1024 Pixel verkleinert |
| Nachbearbeitung | Wortfolgen, die sich dreimal hintereinander wiederholen, werden abgeschnitten; höchstens 120 Wörter |
| Cache | Beschreibungen werden nur für dieselbe Prompt-Version und dasselbe Modell wiederverwendet |
| Kontrolle | 30 zufällige Beschreibungen zur Handprüfung |

Prompt B-v3:

```text
Beschreibe diese Abbildung aus einem technischen Lehrbuch in 2 bis 4 Sätzen. Gib nur wieder, was eindeutig zu sehen ist.

Erster Satz: Art der Abbildung (zum Beispiel Schaltplan, Ersatzschaltbild, Diagramm mit Achsen, Zeigerdiagramm, Schnittbild, Foto).
Danach: die lesbaren Beschriftungen und Formelzeichen, jede nur einmal.
Nur wenn die Abbildung ein Diagramm mit Achsen ist: welche Größen an den Achsen stehen und wie die Kurven verlaufen.

Erkläre keine Abkürzungen und keine Funktion. Nenne keine Bauteile, die nicht eindeutig erkennbar sind.
Ohne Markdown, ohne LaTeX, höchstens 80 Wörter, auf Deutsch.
Bildunterschrift (nur zur Orientierung, nicht wiederholen): <<BILDUNTERSCHRIFT>>
```

## 5.4 Register entfernen und Bücher zusammenführen

Inhalts- und Sachwortverzeichnis werden entfernt (`entferne_register.py`), wenn ein Abschnitt (a) mit „Inhaltsverzeichnis“ beginnt oder das Wort in den ersten 8 Wörtern enthält, oder (b) in den ersten 30 bzw. letzten 60 Seiten liegt, nicht mit „Tabelle“/„Abbildung“ beginnt, zu über 25 % aus Zahlen besteht und kaum Rechenzeichen enthält. Entfernt wurden 35 Abschnitte. Beim Zusammenführen erhalten die Abschnitt-IDs von Fischer das Präfix `fischer_`; jeder Abschnitt erhält das Feld `buch`.

# 6 Antwortweg einer Frage

## 6.1 Retrieval

Jede Frage durchläuft fünf Schritte (`rag_pipeline.retrieval`, Methode `hybrid_kg_rr`).

| Schritt | Einstellung | Bedeutung |
|---|---|---|
| Dense Retrieval | `paraphrase-multilingual-MiniLM-L12-v2` (Sentence-Transformers), normalisierte Vektoren, Kosinus-Ähnlichkeit | Rangliste aller 8.805 Abschnitte nach Bedeutungsähnlichkeit |
| BM25 | `rank_bm25.BM25Okapi` mit Standardwerten `k1 = 1,5`, `b = 0,75`, `epsilon = 0,25` | Rangliste aller Abschnitte nach gemeinsamen Wörtern. Die höchste Bewertung erhält ein Wort, das in der gesamten Wissensbasis selten ist, im Abschnitt mehrfach vorkommt und in einem kurzen Abschnitt steht. |
| Tokenisierung für BM25 | Silbentrennung zusammenführen, Kleinschreibung, Wörter und Zahlen ab 2 Zeichen, deutsche Stoppwortliste (ca. 150 Wörter), deutscher Snowball-Stemmer | „Widerstand“, „Widerstands“, „Widerstände“ fallen zusammen. Beispiel: „Die Wirkungsgrade der Motoren werden mit der Ver-lustleistung P_v berechnet; bei 2 Polen ist n = 1500 min⁻¹.“ wird nach Stoppwörtern und Einzelzeichen zu „wirkungsgrade motoren verlustleistung berechnet polen 1500 min“ und nach dem Stemmer zu „wirkungsgrad motor verlustleist berechn pol 1500 min“. |
| Begriffsgraph | siehe Tabelle unten | Liefert Werte nur für Abschnitte mit Graphbezug; Abschnitte mit Wert 0 erhalten keinen RRF-Beitrag |
| Fusion | Reciprocal Rank Fusion, `RRF_K = 5`, Gewicht der Graphliste `KG_GEWICHT = 1,0` | `RRF(d) = 1/(5 + Rang_dense) + 1/(5 + Rang_BM25) + 1/(5 + Rang_Graph)` |
| Re-Ranking | `BAAI/bge-reranker-v2-m3`, auf der CPU, `max_length 512`, `RERANK_KANDIDATEN = 50` | Die 50 besten Kandidaten der Fusion werden neu geordnet; die übrigen folgen in der Fusionsreihenfolge |
| Übergabe | `top_k = 4` | Die 4 besten Abschnitte gehen an das Sprachmodell (bei Rechenfragen kommen bis zu 2 Formelabschnitte hinzu, Abschnitt 7.1) |
| Relevanzschwelle | `RELEVANZ_SCHWELLE = 0,35` | Liegt die **höchste Kosinus-Ähnlichkeit der Frage zu irgendeinem Abschnitt der Wissensbasis** (Dense-Wert, unabhängig von der Rangfolge) unter 0,35, wird keine Antwort erzeugt |

RRF_K wurde empirisch gewählt (Entwicklungstest mit 25 Fragen: bei k = 60 verdrängten mittelmäßig rangierte Abschnitte die Spitzentreffer einzelner Listen; k = 5 ergab das beste Recall@4 für die Variante mit Graph).

Parameter des Begriffsgraphen (`wissensgraph.py`, Version `kg-v3`):

| Parameter | Wert | Bedeutung |
|---|---|---|
| Knoten | Fachbegriffe per Regel: großgeschriebene Wörter, Abkürzungen, Normen (DIN, EN, ISO, IEC, VDI, VDE); Snowball-Stamm als Schlüssel | Keine Extraktion mit Sprachmodell (deterministisch, schnell) |
| `KG_MAX_DF_ANTEIL` | 0,05 | Begriffe in mehr als 5 % aller Abschnitte sind zu allgemein |
| `KG_MIN_NOMEN_ANTEIL` | 0,2 | Begriff nur, wenn mindestens 20 % seiner Vorkommen mitten im Satz großgeschrieben sind |
| `KG_MIN_KOOKKURRENZ` | 2 | Kante erst ab 2 gemeinsamen Abschnitten; Gewicht = gemeinsame Abschnitte / √(df_i · df_j) |
| `KG_KOOK_NACHBARN` | 20 | Je Begriff nur die 20 stärksten Kanten |
| `KG_SYN_MODUS` | `aus` | Keine Synonymie-Kanten (brachten im Test keinen Nutzen) |
| `KG_WORT_SCHWELLE` | 0,75 | Fragewort ohne exakten Treffer → nächster Begriff im Embedding-Raum ab diesem Kosinus |
| `KG_FRAGE_NACHBARN` | 0 | Begriffe nahe an der ganzen Frage werden nicht zusätzlich gesetzt |
| Startgewichte | IDF der Begriffe | Seltene Fachbegriffe zählen mehr |
| `KG_DAEMPFUNG` | 0,5 | Personalized PageRank wie bei HippoRAG |
| `KG_ITERATIONEN` | 30 | – |
| Abschnittswert | Summe (PPR-Masse · IDF) der Begriffe im Abschnitt / √(Anzahl Begriffe im Abschnitt) | – |

## 6.2 Generierung

| Einstellung | Wert | Bedeutung |
|---|---|---|
| Modell | `qwen3.5:9b` über Ollama (laut Projektdokumentation Quantisierung Q4_K_M) | Lokales Sprachmodell |
| Aufruf | `POST /api/generate`, `stream: false`, `think: false` | Kein sichtbares Reasoning des Modells; die „verdeckte Überlegung“ ist das Feld ÜBERLEGUNG im Ausgabeformat |
| Optionen | `temperature 0`, `seed 42`, `num_ctx 8192` | Reproduzierbare, nicht variierende Antworten; Kontextfenster 8192 Tokens (Ollama-Standard 4096 schnitt lange Antworten ab) |
| Zeitgrenze | 300 s je Aufruf, bei Zeitüberschreitung oder Verbindungsfehler ein zweiter Versuch | – |
| Material im Prompt | Texte der Abschnitte ohne IDs und Kapitelüberschriften; Unicode-Normalisierung (NFKC), Silbentrennung zusammengeführt, Leerraum vereinheitlicht | – |
| Buchergebnisse | Bei Rechenfragen mit anderen Zahlen als im Buch werden Ergebniszeilen („Ergebnis:“, „ERG:“) aus den Abschnitten entfernt (`ohne_buchergebnisse`) | Verhindert, dass ein Buchergebnis mit anderen Werten übernommen wird |

Antwortprompt G-v6 (Bedingung B; derselbe Prompt in Bedingung D):

```text
Du bist ein Lernassistent für Auszubildende. Du beantwortest eine Frage ausschließlich mit dem
Lernmaterial unten und bereitest dazu einen Denkanstoß vor.

Regeln für die Lösung:
L1 Nutze nur Aussagen, die im Lernmaterial stehen oder direkt daraus folgen. Ergänze kein eigenes
   Wissen, auch keine zusätzlichen Begründungen.
L2 Nenne zuerst die Antwort, dann kurz die Begründung aus dem Lernmaterial.
L3 Bei einer Rechnung: Formel, eingesetzte Werte und Ergebnis mit Einheit.
L4 Schreibe verständlich für Auszubildende.
L5 Steht im Lernmaterial ein Rechenbeispiel mit anderen Zahlen, übernimm nur den Rechenweg und rechne mit
   den Werten aus der Frage.
L6 Gib Ergebnisse in der Einheit der gefragten Größe an und rechne Einheiten dafür ausdrücklich um.
L7 Nenne Zahlen und Eigenschaften nur zusammen mit dem Gegenstand, zu dem sie in derselben Textstelle stehen.
   Beschreibt eine Textstelle einen anderen Gegenstand oder eine andere Größe als gefragt, benenne das, statt es zu übertragen.
L8 Stehen alle Zahlenwerte, die für die gefragten Größen nötig sind, in der Frage, dann rechne die Größen aus.
   Steht die nötige Formel nicht im Lernmaterial, verwende eine allgemein gültige Grundgleichung der Physik oder
   Technik und kennzeichne sie mit „(Grundgleichung, nicht aus dem Lernmaterial)“. Schreibe nie, dass ein Wert
   fehlt, der in der Frage steht.
L9 Besteht die Frage aus mehreren Teilfragen, beantworte jede Teilfrage der Reihe nach und nenne im ersten Satz
   alle gefragten Ergebnisse.

Status:
- BEANTWORTET: Das Lernmaterial beantwortet die Frage.
- TEILWEISE: Das Lernmaterial beantwortet nur einen Teil. Beantworte diesen Teil und nenne, was fehlt.
- NICHT_IM_MATERIAL: Das Lernmaterial beantwortet die Frage nicht. Rate nicht.

Regeln für den Hinweis (die lernende Person sieht nur die Frage, nicht das Lernmaterial und nicht
die Lösung):
H1 Verrate die Lösung nicht, auch nicht mit anderen Worten.
H2 Lenke auf den Begriff, die Größe oder den nächsten Denkschritt, der zur Lösung führt.
H3 Die lernende Person sieht nur die Frage. Sie hat kein Lernmaterial, keine Tabelle, keine Abbildung
   und keinen Text vor sich. Fordere sie nie auf, etwas anzusehen oder nachzuschlagen.
H4 Rege zum Nachdenken über einen Zusammenhang an, ohne zu überfordern.
H5 Ein bis zwei kurze Sätze, sprich die lernende Person mit „du" an; du darfst mit einer Frage enden.
H6 Ist die Antwort ein einzelner Wert oder Begriff zum Nachschlagen, lenke auf das Verständnis dahinter:
   was die Größe bedeutet oder wovon sie abhängt, ohne den Wert zu nennen.

### Lernmaterial
<<TEXTABSCHNITT 1>>

<<TEXTABSCHNITT 2>>

<<TEXTABSCHNITT 3>>

<<TEXTABSCHNITT 4>>

### Frage
<<FRAGE>>

Antworte genau in diesem Format:
STATUS: BEANTWORTET oder TEILWEISE oder NICHT_IM_MATERIAL
LÖSUNG: <Lösung nach L1 bis L9; bei NICHT_IM_MATERIAL ein Satz, dass das Lernmaterial dazu nichts enthält>
ÜBERLEGUNG: <nur für dich: welche Kernaussage der Lösung darf der Hinweis nicht verraten, und welcher Denkschritt führt dorthin?>
HINWEIS: <Hinweis nach H1 bis H6; bei NICHT_IM_MATERIAL: –>
```

Die Antwort wird nach den Feldern STATUS, LÖSUNG, ÜBERLEGUNG und HINWEIS zerlegt. Die Lernenden sehen HINWEIS, auf Wunsch LÖSUNG mit Quellenangaben; ÜBERLEGUNG wird nie angezeigt, sondern nur protokolliert. Bewertet wurde in Studie 1 die LÖSUNG.

Feste Ablehnung, wenn die Relevanzschwelle nicht erreicht wird (Status `GATE`, ohne Sprachmodell):

```text
Dazu habe ich in den Lernmaterialien keine ausreichend passende Quelle gefunden und möchte deshalb keine geratene Antwort geben. Bitte wende dich an deine Lehrkraft oder formuliere die Frage genauer.
```

# 7 Formelsuche und Rechenprüfung (nur Rechenfragen)

Eine Frage gilt als **Rechenfrage**, wenn sie mindestens zwei Zahlen enthält (Verweise wie „Aufgabe 1.32“ oder „Abb. 2.69“ zählen nicht) und eine Rechenaufforderung („berechne“, „bestimme“, „ermittle“, „wie groß/viel/hoch …“ oder ein Fragezeichen).

## 7.1 Formelsuche vor der Antwort (V19-A)

Bei jeder Rechenfrage beschreibt ein kurzer Modellaufruf den Lösungsweg und nennt Suchbegriffe. Je Suchbegriff wird gesucht (`hybrid_kg` ohne Re-Ranking, je die ersten 300 Treffer), die Listen werden mit RRF (k = 10) fusioniert, nur Abschnitte mit einer Formel, die noch nicht im Kontext sind, bleiben (höchstens 20). Ein kleiner Cross-Encoder (`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, CPU) bewertet sie gegen die Suchbegriffe; **die 2 besten werden hinter die 4 Abschnitte der Hauptsuche gestellt**. Modelloptionen: `temperature 0`, `seed 42`, `num_predict 260`.

```text
Eine Rechenaufgabe aus der Technik soll gelöst werden. Beschreibe zuerst in 2 bis 4 kurzen Zeilen den Lösungsweg in Worten: welche Größe berechnet man nacheinander (z. B. "Strom aus Leistung und Spannung"). Keine Zahlen.
Schreibe danach eine Zeile "### Suchbegriffe" und darunter je Schritt einen Fachbegriff (2 bis 6 Wörter), unter dem die dafür nötige Beziehung in einem Lehrbuch steht (Gesetz, Größe, Bauteil, Schaltung). Keine Zahlen, keine Formeln.

### Aufgabe
<<FRAGE>>

### Lösungsweg
```

## 7.2 Formelsuche nach einem Fehlschlag (FS-v3)

Ausgelöst, wenn die erste Antwort auf eine Rechenfrage nicht BEANTWORTET ist, im Anfang der Lösung keine Zahl nennt, auf eine fehlende Formel hinweist oder ein Ergebnis aus einem Buchbeispiel mit anderen Werten übernimmt. Ein Modellaufruf nennt 2 bis 4 Suchbegriffe (Optionen `temperature 0`, `seed 42`, `num_predict 100`); je Suchbegriff wird unter den ersten 6 Treffern der erste Abschnitt mit Formel ergänzt (höchstens 2). Die Antwort wird einmal neu erzeugt und nur übernommen, wenn sie beantwortet ist, eine Zahl nennt, kein Buchergebnis übernimmt und die Nachrechnung die Formel im Material findet.

```text
Eine Rechenaufgabe aus der Technik soll gelöst werden. Nenne die physikalischen oder technischen Beziehungen (Formeln), die man dafür braucht, als kurze Suchbegriffe, so wie sie in einem Lehrbuch als Überschrift oder im Fließtext stehen.

Regeln:
- 2 bis 4 Zeilen, eine Beziehung pro Zeile.
- Je 2 bis 6 Wörter, nur Fachbegriffe (Gesetz, Größe, Bauteil). Keine Zahlen, keine Formeln, keine Einheiten, keine Sätze.
- Auch einfache Hilfsbeziehungen nennen (z. B. Masse aus Dichte und Volumen).
- Beispiele für die Form: "Kraft zwischen Kondensatorplatten", "Leistung im Drehstromnetz".
- Keine Erklärung, keine Nummerierung.

### Aufgabe
<<FRAGE>>

### Suchbegriffe
```

In Studie 1 erhielt das Sprachmodell dadurch bei 81 der 270 Buchfragen 6 Abschnitte und bei einer Frage 8 Abschnitte (bei 188 Fragen 4). Betroffen sind vor allem Rechenfragen (57 von 60), aber auch einige Fakten-, Konzept-, Tabellen- und Aufzählungsfragen, deren Wortlaut die Regel für Rechenfragen erfüllt.

## 7.3 Ablauf der Rechenprüfung (RP-v13)

Die Rechenprüfung läuft nach der Generierung und vor der Hinweisprüfung, nur bei Status BEANTWORTET oder TEILWEISE.

1. **Bereinigung:** Sichtbarer Denktext am Ende der Lösung („Warte“, „Korrektur:“ usw.) wird abgeschnitten.
2. **Nachrechnung (RB-v8):** Ein zweiter, unabhängiger Aufruf sieht Frage und Material, aber nicht die erste Antwort, und schreibt die Rechnung im festen Format (FORMEL, WERTE, RECHNUNG, ERGEBNIS, EINHEIT, QUELLE). Python wertet die RECHNUNG sicher aus (Syntaxbaum, nur `+ − * / **`, `sqrt`, `sin`, `cos`, `tan`, `exp`, `ln`, `log10`, `pi`; kein `eval`). Optionen `temperature 0`, `seed 42`, `num_predict 700`. Ist das Ergebnis nicht auswertbar, folgt ein zweiter Aufruf mit Fehlerbericht.
3. **Prüfungen der Antwort:** (a) jede ausgeschriebene Gleichungskette wird nachgerechnet (Toleranz 2 % relativ oder die Rundung der angegebenen Zahl); (b) der Wert im ersten Satz muss zum Endergebnis der eigenen Rechnung passen; (c) sichtbare Selbstkorrekturen; (d) jede Zahl mit Einheit im ersten Satz muss zu einem Ergebnis der Nachrechnung passen; (e) Ergebnis aus einem Buchbeispiel übernommen, ohne mit den Werten der Frage zu rechnen.
4. **Reaktion auf Befunde:** zuerst ein Neuschreiben mit dem Befund (Prompt unten). Gelingt das nicht, wird – je nach Lage – die Zahl im ersten Satz an die eigene, stimmige Rechnung angeglichen, oder die Nachrechnung ersetzt die Lösung. **Ersetzt wird nur**, wenn eine zweite, anders formulierte Nachrechnung dasselbe Ergebnis liefert (Vergleich in Grundeinheiten, 0,5 %) und – ohne Formel aus dem Material – die Antwort keine eigene oder eine nachweislich falsche Rechnung hat. Sonst erhält die Lösung einen sichtbaren Prüfvermerk („⚠ Automatische Prüfung: …“).
5. **Denkmodus:** Bleibt eine Rechenfrage nur „markiert“ oder konnte gar nicht geprüft werden („ungeprüft“), folgt ein einziger Aufruf mit Reasoning (`think: true`, `num_ctx 16384`, Zeitgrenze 900 s). Die neue Antwort gilt nur, wenn sie beantwortet ist, eine Zahl nennt und die Python-Prüfung ihrer eigenen Rechnung besteht.

Ergebnis der Rechenprüfung in Studie 1 (Bedingung B, 270 Buchfragen):

| Ausgang | Anzahl | Bedeutung |
|---|---|---|
| `ok` | 196 | Kein Befund (auch: keine Rechnung in der Antwort) |
| `nachgebessert` | 15 | Neuschreiben mit Befund war erfolgreich |
| `ersetzt` | 21 | Bestätigte Nachrechnung ersetzt die Lösung |
| `denkmodus` | 5 | Antwort aus dem Denkmodus übernommen |
| `markiert` | 6 | Lösung mit sichtbarem Prüfvermerk |
| `abweichung_ungestuetzt` | 7 | Nachrechnung widerspricht, ihre Formel steht aber nicht im Material; nur protokolliert |
| `ungeprueft` | 17 | Rechenfrage, aber nichts nachprüfbar (Denkmodus versucht, verworfen) |
| `bereinigt` | 2 | Nur Denktext abgeschnitten |
| leer | 1 | Nicht anwendbar (Status NICHT_IM_MATERIAL) |

Prompt für das Neuschreiben nach einem Befund (der letzte Satz nur, wenn die Nachrechnung widerspricht):

```text
<<G-v6-PROMPT DER FRAGE>>

### Prüfung deiner ersten Antwort
Deine erste Lösung war:
<<ERSTE LÖSUNG>>

Die automatische Prüfung hat ein Problem gefunden: <<BEFUND 1>>; <<BEFUND 2>>.
Antworte noch einmal vollständig im selben Format. Rechne mit den Werten aus der Frage und passe alle Angaben an, die vom Ergebnis abhängen. Die Lösung nennt zuerst das richtige Ergebnis und dann die Begründung, ohne Zwischenüberlegungen und ohne Korrekturen. Prüfe Formel und Werte der Nachrechnung; passen sie zur Frage, übernimm ihr Ergebnis und nenne es im ersten Satz.
```

Prompt der Nachrechnung, erster Aufruf (`<<LERNMATERIAL>>` hier mit Quellenzeile `[Quelle <id> – <Kapitel>]: <Text>` je Abschnitt, ohne Buchergebnisse):

```text
Du rechnest eine Aufgabe aus der Technik nach. Antworte NUR in diesem Format, ohne weiteren Text:

FORMEL: <die Formeln, die zur Frage passen>
WERTE:
<name> = <Zahl oder Rechenausdruck> <Einheit>
(eine Zeile je Größe; nur Zahlen aus der Frage oder dem Material; Umrechnungen in die Zahl schreiben,
z. B. n = 1000/60 für 1000 1/min in 1/s; Namen nur Buchstaben und Ziffern, ohne Leerzeichen und Unterstrich)
RECHNUNG:
<name> = <Python-Ausdruck mit den Namen aus WERTE und aus früheren Zeilen; erlaubt: + - * / ** ( ) sqrt() sin() cos() tan() exp() ln() log10() pi>
(eine Zeile je Zwischen- und Endergebnis, von oben nach unten)
ERGEBNIS: <Namen der gesuchten Größen, durch Komma getrennt, in der Reihenfolge der Frage>
EINHEIT: <Einheiten der gesuchten Größen, durch Komma getrennt, in derselben Reihenfolge>
QUELLE: <die Formel wörtlich aus dem Material als kurzer Auszug mit Gleichungszeichen (höchstens eine Zeile) oder GRUNDWISSEN, wenn sie nicht im Material steht>

Sind mehrere Größen gesucht (zum Beispiel Primär- und Sekundärstrom), rechne jede mit einer eigenen Zeile.
Beachte die genaue Bedingung der Frage (zum Beispiel Art der Last, welche Größe vernachlässigt wird) und setze sie in die Formel ein.
Ist die Frage keine Rechenaufgabe oder fehlt ein Wert, schreibe nur: RECHNUNG: KEINE

Material:
<<LERNMATERIAL: die vier abgerufenen Textabschnitte>>

Frage: <<FRAGE>>
```

Prompt der Nachrechnung beim Wiederholen mit Fehlerbericht. Ohne die erste Zeile ist dies zugleich der Prompt der **zweiten, bestätigenden Nachrechnung**:

```text
Deine erste Nachrechnung war nicht auswertbar: <<GRUND>> (<<DETAIL>>). Rechne dieselbe Aufgabe noch einmal und halte dich genau an die Schreibweise.

Du rechnest eine Aufgabe aus der Technik nach. Antworte NUR in diesem Format, ohne weiteren Text:

FORMEL: <die Formeln, die zur Frage passen>
WERTE:
<name> = <Zahl oder Rechenausdruck> <Einheit>
(eine Zeile je Größe; nur Zahlen aus der Frage oder dem Material; Umrechnungen in die Zahl schreiben,
z. B. n = 1000/60 für 1000 1/min in 1/s; Namen nur Buchstaben und Ziffern, ohne Leerzeichen und Unterstrich)
RECHNUNG:
<name> = <Python-Ausdruck mit den Namen aus WERTE und aus früheren Zeilen; erlaubt: + - * / ** ( ) sqrt() sin() cos() tan() exp() ln() log10() pi>
(eine Zeile je Zwischen- und Endergebnis, von oben nach unten)
ERGEBNIS: <Namen der gesuchten Größen, durch Komma getrennt, in der Reihenfolge der Frage>
EINHEIT: <Einheiten der gesuchten Größen, durch Komma getrennt, in derselben Reihenfolge>
QUELLE: <die Formel wörtlich aus dem Material als kurzer Auszug mit Gleichungszeichen (höchstens eine Zeile) oder GRUNDWISSEN, wenn sie nicht im Material steht>

Sind mehrere Größen gesucht (zum Beispiel Primär- und Sekundärstrom), rechne jede mit einer eigenen Zeile.
Beachte die genaue Bedingung der Frage (zum Beispiel Art der Last, welche Größe vernachlässigt wird) und setze sie in die Formel ein.
Ist die Frage keine Rechenaufgabe oder fehlt ein Wert, schreibe nur: RECHNUNG: KEINE

Schreibweise (wichtig, die Zeilen werden automatisch ausgewertet):
- WERTE: genau eine Größe je Zeile, Form „Name = Zahl Einheit“. Rechts vom = nur Zahlen oder Rechenausdrücke
  mit Zahlen, nie eine Variable oder Gleichung (nicht „n1 = n/10“, sondern „n1 = 1/10“). Keine Platzhalter.
- Mehrere Größen nie in einer Zeile trennen (nicht „A = 1 / B = 2“).
- Keine Wörter wie „unendlich“ oder „gesucht“. Fehlt eine Zahl, schreibe nur: RECHNUNG: KEINE
- RECHNUNG: nur Namen aus WERTE, Zahlen und + - * / ** ( ) sqrt() pi; Malzeichen immer ausschreiben; Wurzel als sqrt(x), nie √; Potenzen mit **; keine Einheiten in RECHNUNG.
- Beispiel:
  U = 230 V
  n = 1500/60 1/s
  RECHNUNG: w = 2*pi*n

Material:
<<LERNMATERIAL: die vier abgerufenen Textabschnitte>>

Frage: <<FRAGE>>
```

## 7.4 Zusatzregeln der Nachrechnung

| Schalter | Regel |
|---|---|
| RB-v8 | Einheiten werden in Grundeinheiten ohne Vorsilbe umgerechnet (37 mm → 0,037 m), außer bei Zahlenwertgleichungen; danach Dimensionsprüfung: Summe verschiedener Dimensionen, berechneter Ausdruck ≠ angegebene Einheit oder Ergebnis ≠ Einheit unter EINHEIT → nicht verwertbar, Wiederholung mit Befund |
| V18-A | strengere Schreibweise der Bestätigung |
| V18-D | jede Zahl in einem Rechenschritt, der eine Größe erstmals berechnet, muss aus Frage oder Material stammen, eine Strukturzahl sein (z. B. 0,5; 1,5) oder innerhalb 0,5 % bei einem schon berechneten Wert liegen |
| V18-E | ERGEBNIS muss eine tatsächlich berechnete Größe nennen (kein stiller Rückfall auf den letzten Schritt) |
| V18-K | Lesekorrektur für Hochzahlen nach Einheiten |
| V19-B | Einheit mit Exponent („kg*m**2“) wird gestrichen; unbenutzte Zwischenzeilen werden übersprungen |
| Herkunft der Werte | jede Zahl unter WERTE muss in Frage oder Material stehen oder eine Umrechnungskonstante sein (z. B. 60, 1000, 3600) |
| Formelquelle | QUELLE wird im Material gesucht; Ergebnis „Formel im Material“, „nicht im Material“ oder „ohne Quelle“ |

# 8 Hinweisprüfung (HP-v4)

Nach der Rechenprüfung wird der Hinweis regelbasiert geprüft (nur bei BEANTWORTET oder TEILWEISE). Ein Hinweis fällt durch, wenn er

* auf Material verweist, das Lernende nicht sehen (Muster u. a.: Kontext, Textstelle, im Text, Lernmaterial, im Buch, Abschnitt, Quelle, Tabelle, Liste, Übersicht, Abbildung, Diagramm, Grafik, nachschlagen, „schau dir … an“, Unterlagen, Formelsammlung, Tabellenbuch, Skript, Datenblatt, „bereitgestelltes Material“, „such in/nach“, „was siehst du“, „du hast … gesehen/gelesen“),
* eine Zahl aus der Lösung nennt, die nicht in der Frage steht, oder
* eine Wertangabe enthält (Zahlen, die nicht in der Frage stehen, oder Wörter wie „Zehntel“, „Größenordnung“, „im Bereich von“, „einstellig“, „untere/obere Grenze“).

Dann schreibt ein Aufruf den Hinweis einmal neu (Optionen `temperature 0`, `seed 42`). Fällt auch der neue Hinweis durch, erscheint ein fester Ersatztext. Die Prüfung erkennt keinen in Worten verratenen Lösungskern.

```text
Ein Hinweis für eine lernende Person ist unbrauchbar: Er verweist auf Material, das sie nicht hat,
oder er nennt Werte. Die Person sieht nur die Frage.

Schreibe einen neuen Hinweis:
- Lenke auf den Begriff, die Bedeutung der gesuchten Größe, wovon sie abhängt oder auf den nächsten
  Denkschritt, den die Frage verlangt.
- Nenne keine Zahlen, keine Bereiche, keine Größenordnungen und keine Einheiten.
- Nenne keine Fakten, die nicht in der Frage oder in der Lösung stehen.
- Verrate die Lösung nicht und fordere nicht auf, etwas anzusehen oder nachzuschlagen.
- Ein bis zwei kurze Sätze, sprich die Person mit „du" an.

### Frage
<<FRAGE>>

### Lösung (geheim)
<<LÖSUNG>>

### Bisheriger Hinweis (nicht verwenden)
<<BISHERIGER HINWEIS>>

Antworte genau in diesem Format:
HINWEIS: <neuer Hinweis>
```

Ersatztext:

```text
Für diese Frage habe ich keinen Hinweis, der ohne das Lernmaterial auskommt. Überlege kurz, was du schon über das Thema weißt, und öffne dann die Lösung.
```

# 9 Gestufte Lerninteraktion in der App

| Schritt | Umsetzung |
|---|---|
| 1 Hinweis | Erscheint zuerst; Lösung verdeckt |
| 2 Eigene Idee | Freiwillig, höchstens `MAX_VERSUCHE = 3` Ideen je Frage; nur wenn die Antwort BEANTWORTET oder TEILWEISE ist |
| Rückmeldung | Prompt IF-v5 (unten), Prüfung FP-v3: Zahlen aus der Lösung, neue Zahlen, Wertangaben oder Materialverweise führen zu einem Neuschreiben, sonst zu einem festen Ersatztext; Urteil RICHTIG wird nicht geprüft |
| 3 Lösung | Auf Knopfdruck („Lösung anzeigen“), jederzeit, auch ohne Idee; mit Quellen und Status |
| Protokoll | `interaktionen.csv`: u. a. Frage, Status, Hinweis, Lösung, Quellen, `scaffolding_stufe_erreicht` (1 = Hinweis, 2 = Lösung geöffnet), Ergebnis der Rechen- und Hinweisprüfung; `ideen_feedback.csv`: Idee, Versuch, Stufe beim Versuch, Urteil, Rückmeldung, Prüfung. Daraus lässt sich ablesen, ob die Lösung ohne eigene Idee geöffnet wurde |

Prompt der Rückmeldung zur eigenen Idee (IF-v5):

```text
Du gibst einer lernenden Person eine kurze Rückmeldung auf ihre eigene Idee zu einer Frage. Du kennst
die richtige Lösung; die lernende Person kennt sie nicht und hat bisher nur die Frage und den Hinweis
gesehen. Sie hat kein Lernmaterial, keine Tabellen und keine Abbildungen. Verweist der
Hinweis trotzdem darauf, gehe nicht darauf ein.

Regeln:
F1 Beurteile die Idee anhand der Lösung: RICHTIG, TEILWEISE, FALSCH oder KEINE_IDEE (keine fachliche Idee
   erkennbar).
F2 Benenne, was an der Idee stimmt, und wo genau eine Abweichung liegt.
F3 Gib einen konkreten nächsten Denkschritt, ohne die Lösung zu verraten, auch nicht mit anderen Worten
   und ohne Zahlenwerte aus der Lösung.
F4 Ist die Idee RICHTIG, bestätige sie und sage, dass die Lösung jetzt angezeigt werden kann.
F5 Zwei bis drei kurze Sätze, freundlich und sachlich, sprich die Person mit „du" an.
F6 Sagt die Person, dass sie nicht weiterkommt oder etwas nicht sehen kann, ist das KEINE_IDEE: widersprich
   ihr nicht, sondern gib einen kleinen zusätzlichen Denkanstoß aus der Frage.
F7 Nenne nur Fehlerursachen, die in der Idee erkennbar sind, und prüfe, dass deine Rückmeldung der Lösung
   nicht widerspricht.
F8 Maßgeblich ist nur die Lösung. Der Hinweis ist kein Beleg und kann ungenau sein. Formuliere Sachaussagen
   als Aussage des Lernmaterials („laut Lernmaterial"), nicht als allgemeine Tatsache oder „in der Praxis".
F9 Nenne keine Zahlen, Bereiche oder Größenordnungen, die nicht in der Idee stehen, und sage nicht, ob ein
   Wert näher an einer Grenze liegt.
F10 Bei TEILWEISE oder FALSCH: Nenne den fehlenden Teil nicht selbst, also keinen fehlenden Rechenschritt,
   kein fehlendes Vorzeichen und keinen fehlenden Begriff. Frage stattdessen gezielt nach der Stelle, an der
   er fehlt.

### Frage
<<FRAGE>>

### Hinweis (hat die lernende Person gesehen)
<<HINWEIS>>

### Lösung (geheim)
<<LÖSUNG>>

### Idee der lernenden Person
<<IDEE DER LERNENDEN PERSON>>

Antworte genau in diesem Format:
ÜBERLEGUNG: <nur für dich: was stimmt, was fehlt, wie lenke ich, ohne zu verraten?>
URTEIL: RICHTIG oder TEILWEISE oder FALSCH oder KEINE_IDEE
RÜCKMELDUNG: <Rückmeldung nach F2 bis F10>
```

Prompt für das Neuschreiben einer Rückmeldung (FP-v3):

```text
Eine Rückmeldung an eine lernende Person ist unbrauchbar: Sie nennt Zahlen, Bereiche oder
Größenordnungen, die die Person nicht selbst geschrieben hat, verrät Werte aus der Lösung oder verweist auf
Material, das die Person nicht hat. Die Person sieht nur die Frage, den Hinweis und ihre eigene Idee.

Schreibe eine neue Rückmeldung zum Urteil <<URTEIL>>:
- Benenne, was an der Idee stimmt und wo die Abweichung liegt, ohne den richtigen Wert zu nennen.
- Nenne keine Zahlen, Bereiche, Größenordnungen oder Vorzeichen, die nicht in der Idee stehen.
- Gib einen konkreten nächsten Denkschritt.
- Zwei bis drei kurze Sätze, freundlich, sprich die Person mit „du" an.

### Frage
<<FRAGE>>

### Lösung (geheim)
<<LÖSUNG>>

### Idee der lernenden Person
<<IDEE>>

### Bisherige Rückmeldung (nicht verwenden)
<<BISHERIGE RÜCKMELDUNG>>

Antworte genau in diesem Format:
RÜCKMELDUNG: <neue Rückmeldung>
```

Feste Texte: ohne Prüfung möglich „Danke für deine Idee! Ich konnte sie gerade nicht automatisch prüfen. Vergleiche sie mit der Lösung, wenn du sie öffnest.“; Ersatz bei KEINE_IDEE „Schreib ruhig eine Vermutung auf, auch wenn du unsicher bist, oder öffne die Lösung.“; sonst „Deine Idee stimmt noch nicht ganz. Überlege noch einmal genau, was gefragt ist, oder öffne die Lösung und vergleiche sie mit deiner Idee.“

Die Oberfläche bietet zusätzlich Anschlussfragen und eine Übungsfrage aus dem verwendeten Material (`lernhilfen.py`). Diese Funktionen sind nicht Teil der Studie.

# 10 Studie 1: Antworten

## 10.1 Testfragen

`daten/testfragen/fragen300.csv` (nicht im Repository): 300 Fragen, Fischer 135, Böge 135, außerhalb 30; Typen Konzept 75, Fakt 75, Rechnung 60, Tabellenabfrage 30, Aufzählung 30. Je Buchfrage: Referenzantwort, Buchstelle, gedruckte Seite und Abschnitt. Gegen die Bücher geprüft: 180 unverändert, 90 kleine Korrekturen. Der Fragensatz wurde nicht zur Abstimmung des Systems verwendet.

## 10.2 Bedingungen

| | Modell | Aufruf | Prompt | Retrieval und Prüfungen |
|---|---|---|---|---|
| A | `qwen3.5:9b`, Ollama | `temperature 0`, `seed 42`, `num_ctx 8192`, `think false` | O-v1 | keine |
| B | `qwen3.5:9b`, Ollama | wie A | G-v6 | vollständiges V20-System: Retrieval, Relevanzschwelle, Formelsuche, Rechenprüfung, Hinweisprüfung |
| C | `gpt-6.1-sol`, OpenAI-API `chat/completions` | Standardparameter, eine Nutzernachricht | O-v1 (wortgleich, im Skript geprüft) | keine; es gingen nur die Fragen an OpenAI |
| D | `gpt-6.1-sol`, OpenAI-API | Standardparameter, ein Aufruf je Frage | G-v6 | gleiche Suche, gleiche Relevanzschwelle, die ersten 4 Abschnitte, Buchergebnisse entfernt; **ohne** Formelsuche, Rechenprüfung und Hinweisprüfung (diese sind auf qwen abgestimmt). Bewertet wurde das Feld LÖSUNG. |

Prompt ohne Retrieval (O-v1, Bedingungen A und C):

```text
Du bist Fachlehrkraft für Elektrotechnik in der beruflichen Ausbildung. Beantworte die Frage einer oder eines Auszubildenden fachlich korrekt und knapp (höchstens 6 Sätze). Bei Rechenaufgaben: Formel, eingesetzte Werte, Ergebnis mit Einheit. Wenn du etwas nicht sicher weißt, sage das ausdrücklich, statt zu raten.

Frage: <<FRAGE>>

Antwort:
```

Durchführung: je Bedingung ein Durchlauf; protokolliert wurden Antwort, Gesamtzeit (Wanduhr), Ollama-Zeiten (Laden, Prompt lesen, Erzeugen), Zahl der Modellaufrufe, abgerufene Abschnitte, Status, Ergebnis der Rechenprüfung, Hinweis und ÜBERLEGUNG. Fehlgeschlagene Aufrufe wurden bis zu dreimal wiederholt (Pause 20 s); die Skripte setzen nach Abbruch fort.

## 10.3 Menschliche Bewertung

Alle 1.200 Antworten wurden vom Erstautor nach folgenden Regeln bewertet (`kriterien300.json`, wörtlich):

```text
Bewertungskriterien: Gleiche Regeln für alle Bewertenden und beide Bedingungen (ohne / mit RAG). Bewertet wird nur mit ja, teilweise oder nein (Spalten 1, 2, 3).
Buchfragen: ja: Alle Kernaussagen der Referenz sind sinngemäß enthalten; keine falsche Aussage, kein falscher Wert, keine falsche Einheit, kein Vorzeichen-, Formel- oder Rechenfehler. Richtige Zusatzinformationen sind zulässig. Rundungsabweichungen bis etwa 2 % und gleichwertige Einheiten sind zulässig. Genannte Antwortalternativen gelten. Ein richtiges Ergebnis mit eindeutig falschem Lösungsweg ist nicht „ja“.
Buchfragen: teilweise: Alles Gesagte ist richtig, aber mindestens eine Kernaussage fehlt. Es liegt nur eine Auslassung vor, etwa zwei von drei richtigen Bedingungen oder ein richtiger Rechenweg ohne Endergebnis.
Buchfragen: nein: Mindestens eine Aussage, ein Wert, eine Einheit oder ein Rechenschritt ist falsch; auch eine falsche Nebenaussage genügt. Ebenso: Widerspruch zur Referenz/Buchstelle, Verfehlung der Frage, Ablehnung, bloße Rückfrage oder keine Antwort.
Grenzfälle: Falsch und unvollständig ergibt „nein“. Eine unklare, nicht eindeutig falsche Aussage zählt als fehlend. Eine fachlich präzisere richtige Antwort ist auch bei vereinfachter Buchreferenz zulässig. Passende Einschränkungen wie „etwa“ oder „in der Regel“ sind erlaubt. Automatische Warnhinweise gehören zur bewerteten Antwort.
Außerhalb: ja: Die Antwort lehnt die inhaltliche Beantwortung ab oder nennt die Begrenzung auf das Lernmaterial/Fachgebiet, ohne die Sachantwort zu geben.
Außerhalb: nein: Die Sachantwort wird gegeben, auch wenn zuvor auf die fehlende Materialgrundlage hingewiesen wird. „Teilweise“ wird für Außerhalb-Fragen nicht verwendet.
Punkte und Auswertung: Buchfragen: ja = 1, teilweise = 0,5, nein = 0. Außerhalb-Fragen werden separat als Ablehnungsquote ausgewertet. Leere Bewertungen sind fehlende Werte, keine Nullpunkte.
Fragetypen: Konzept: Zusammenhang oder Begründung. Fakt: benennbarer Einzelwert, Begriff oder Merkmal. Rechnung: rechnerische Herleitung. Tabellenabfrage: Auswahl oder Vergleich tabellierter Richtwerte. Aufzählung: mehrere gleichrangige Elemente. Bei Mischfragen gilt die überwiegende Anforderung. Aus V4 übernommene Typen sind unverändert; Q174, Q229, Q2, Q281 und Q216 sind eher Rechenaufgaben.
Seite: Gedruckte Seite im Buch (Fischer: Fischer_Elektrotechnik(2).pdf; Böge: Böge_Maschinebau(2).pdf).
Kontextabhängige Fragen: Q106 Brückentopologie, Q279 Transistorbezeichnungen, Q47 Bremshebelanordnung; bei Q199 hängt die Dimensionierung vom Lastfall ab; Q229 unterscheidet Messpunkt und grafischen MPP. Beim Interpretieren getrennt betrachten.
Automatische Spalten (grau): Antworten, Zeit, Rang und Faithfulness füllt der Auswertungslauf. Zeit: Sekunden je Antwort. Rang der Buchstelle: Platz des ersten abgerufenen Abschnitts aus Buch und Seite der Frage in der Trefferliste (1 = bester Treffer; das Sprachmodell erhält die ersten 4); 0 = nicht unter den ersten 50. Faithfulness: Anteil der Aussagen einer Antwort, die durch die abgerufenen Abschnitte gestützt sind (0–1); beide Antworten gegen dieselben Abschnitte.
```

## 10.4 Modellbewertungen (Gemini, Mistral)

| Einstellung | Gemini | Mistral |
|---|---|---|
| Modell | `gemini-4-argon` | `mistral-large-4` |
| Schnittstelle | `google-genai`: Interactions-API mit JSON-Schema, falls im SDK vorhanden, sonst `generate_content` mit JSON-Ausgabe | `https://api.mistral.ai/v1/chat/completions` |
| Temperatur | nicht gesetzt (Standard des Anbieters) | `temperature 0` und JSON-Modus wurden vom Modell abgelehnt („top_p must be 1 when using greedy sampling“); danach ohne Temperatur und ohne JSON-Modus, Standard des Anbieters |
| Eingabe je Frage | Rubrik, Frage mit Typ, Referenzantwort, Buchstelle (OCR-Auszug), die vier Antworten als A–D | gleich |
| Reihenfolge | zufällig je Frage und Bewerter, reproduzierbar (Zufallsgenerator mit Startwert `<anbieter>|<Frage-ID>`) | gleich |
| Verdeckung | keine Namen der Systeme oder Bedingungen | gleich |
| Ausgabe | je Antwort `ja`, `teilweise` oder `nein` mit Begründung (JSON) | gleich |
| Wiederholung | bis zu 6 Versuche je Frage, Wartezeit 5 · 2^n s (höchstens 120 s) | gleich |

Systemanweisung:

```text
Du bist ein strenger, unabhängiger Prüfer für Antworten auf Fachfragen aus der beruflichen Bildung (Elektrotechnik, Maschinenbau, Regelungstechnik, Werkstoffe). Du bewertest ausschließlich nach den Bewertungsregeln, der Referenzantwort und der Buchstelle. Rechne Zahlenwerte selbst nach.
```

Rubrik (`bewertung/antworten/rubrik.md`, wörtlich):

```text
# Bewertungsregeln (streng, wie der Forscher sie anwendet)

Jede Frage hat vier anonymisierte Antworten A, B, C, D (jede Antwort stammt von einem anderen System; du weißt nicht, von welchem) (Reihenfolge zufällig). Bewerte JEDE Antwort unabhängig mit
genau einem Urteil: ja | teilweise | nein. Maßstab ist die Referenzantwort (und die Buchstelle); sie gelten als richtig.

**ja**: Alle gefragten Teile sind fachlich richtig beantwortet, es gibt KEINE falsche Aussage. Zusätzliche richtige
Inhalte sind in Ordnung. Rundungsunterschiede (z. B. 31,35 vs 31,4; π ≈ 3,14) sind in Ordnung. Formatierung (LaTeX,
Fettdruck) ist egal. Gibt die Referenz einen Bereich an (z. B. 5–10), ist ein Wert innerhalb des Bereichs richtig.

**teilweise**: Nur bei mehrteiligen Fragen/Aufzählungen: einige Teile richtig, andere fehlen, bleiben offen
("kann ich nicht sicher nennen") oder sind zu vage – aber KEINE falsche Aussage. Bei Aufzählungen: ein Element fehlt
oder ist durch ein anderes (sachlich zutreffendes, aber nicht zur Referenz passendes) ersetzt → teilweise.

**nein**:
- irgendeine sachlich falsche Aussage, auch als Nebenbemerkung neben einem richtigen Kern (z. B. richtige Formel,
  aber falsche Begründung; falsche Richtung eines Zusammenhangs; falsche Einheit);
- falsches Endergebnis einer Rechnung oder Rechnung ohne Endergebnis;
- Zahlenwerte, die der Referenz widersprechen (ein "allgemein üblicher" Wert, der vom Buchwert abweicht, z. B. 20 kHz
  statt 16 kHz, gilt als falsch);
- einteilige Frage nicht beantwortet, oder Ablehnung ("nicht im Material") obwohl die Frage im Buch beantwortet wird.

**Fragen vom Typ "Außerhalb"** (Referenz: "Außerhalb der beiden Lehrbücher …"): ja NUR, wenn die Antwort die Frage
ablehnt bzw. sagt, dass das nicht in den Lernmaterialien steht. Beantwortet sie die Frage inhaltlich (auch korrekt) → nein.

Sei genau: prüfe Zahlen und Rechenwege nach, lies die ganze Antwort (falsche Nebensätze stehen oft am Ende).
Im Zweifel zwischen ja und teilweise/nein: lies die Referenz noch einmal und entscheide streng.
```

Aufbau des Prompts je Frage (nach der Rubrik):

```text
## Frage (<<ID>>, Typ: <<TYP>>)
<<FRAGE>>

## Referenzantwort (gilt als richtig)
<<REFERENZ>>

## Buchstelle (Auszug aus dem Lehrbuch, OCR)
<<BUCHSTELLE>>

## Antwort A
<<ANTWORT>>
## Antwort B … ## Antwort D

## Ausgabe
Antworte NUR mit einem JSON-Objekt, ohne weiteren Text, genau in dieser Form:
{"A": {"urteil": "ja|teilweise|nein", "begruendung": "..."}, "B": {...}, "C": {...}, "D": {...}}
Begründung: 1–2 Sätze auf Deutsch; bei teilweise/nein konkret, was falsch ist oder fehlt; bei ja kurz.
```

Hinweis: Dabei werden Buchauszüge an Google bzw. Mistral übertragen; vorher ist die Freigabe für das Material zu klären.

## 10.5 Retrieval-Qualität (Recall@k, MRR)

`rang300.py` nutzt dieselbe Suche wie die App (`hybrid_kg_rr`, ohne Formelsuche). Ein Abschnitt zählt als Treffer, wenn mindestens 40 % seiner Wortfolgen aus 4 Wörtern (normalisiert: NFKC, Kleinschreibung, Silbentrennung zusammengeführt) auf der hinterlegten Buchseite stehen (Seitentext aus dem PDF; bei zwei Seiten beide). Rang = Platz des ersten Treffers unter den ersten 50; 0 = nicht gefunden. Recall@k = Anteil der Fragen mit Rang 1 bis k; MRR = Mittel von 1/Rang (0 bei nicht gefunden).

## 10.6 Faithfulness

| Einstellung | Wert |
|---|---|
| Bewertungsmodell | `gemma4:12b` (Gemma 4, 12B) über Ollama, lokal |
| Optionen | `temperature 0`, `seed 42` |
| Verfahren | Antwort in Aussagen zerlegen (Prompt 1), jede Aussage gegen den Kontext prüfen (Prompt 2); F = gestützte / prüfbare Aussagen; Meta-Aussagen über das Material werden verworfen und gezählt |
| Kontext | qwen-Antworten (A und B): die Abschnitte, die Bedingung B erhielt (Spalte `quellen_mit`, 4 bis 8 Abschnitte); GPT-Antworten (C und D): die Abschnitte, die Bedingung D erhielt (4). Je Modell werden beide Antworten gegen denselben Kontext geprüft. Bei 188 von 270 Fragen sind beide Kontexte gleich |
| Umfang | 1.080 Antworten (270 Buchfragen × 4 Bedingungen) |

Prompt 1 (Aussagen zerlegen):

```text
Zerlege die Antwort in einzelne Aussagen.

Regeln:
- Jede Aussage enthält genau einen Sachverhalt.
- Jede Aussage ist ohne die anderen verständlich: ersetze Pronomen durch das gemeinte Nomen.
- Lass Aufforderungen an Lernende, Fragen und Aussagen über das Lernmaterial weg.
- Ergänze nichts, was nicht in der Antwort steht.

### Frage
<<FRAGE>>

### Antwort
<<ANTWORT>>

Gib jede Aussage in einer eigenen Zeile aus, beginnend mit „- ". Sonst nichts.
```

Prompt 2 (Aussage prüfen):

```text
Prüfe, ob die Aussage durch den Kontext gestützt ist. Nutze ausschließlich den Kontext, nicht dein
eigenes Wissen.

JA: Der Kontext enthält den Sachverhalt, auch mit anderen Worten, oder er folgt direkt daraus.
NEIN: Der Sachverhalt fehlt im Kontext, widerspricht ihm oder geht deutlich über ihn hinaus.

### Kontext
<<KONTEXT: die vier abgerufenen Textabschnitte>>

### Aussage
<<AUSSAGE>>

Antworte genau in diesem Format:
BEGRÜNDUNG: <ein Satz>
URTEIL: JA oder NEIN
```

## 10.7 Statistik

Gerechnet in R (Skripte `Statistik.R` und `Abb06`–`Abb10`; Abbildungen und Kennwerte werden direkt aus der Datentabelle berechnet und laufen auch im jamovi-Modul Rj). Punktanteil: ja = 1, teilweise = 0,5, nein = 0, in Prozent der erreichbaren Punkte. 95-%-Konfidenzintervalle nach Wilson (`prop.test(…, correct = FALSE)`). Vorzeichentest zweiseitig über die Fragen mit unterschiedlichem Punktwert (`binom.test`). Cohens κ ungewichtet über drei Kategorien. Antwortzeit: Median und Mittelwert über alle 300 Fragen. Rundung kaufmännisch.

# 11 Studie 2: Hinweise

| Einstellung | Wert |
|---|---|
| Material | Erster Hinweis des Prototyps (Bedingung B, Studie 1, Spalte `hinweis_mit`) zu allen Buchfragen; 269 Hinweise (eine Buchfrage wurde als NICHT_IM_MATERIAL abgewiesen) |
| Geschützter Kern | Je Frage vor der Bewertung festgelegt: der entscheidende Zusammenhang, die Formel oder das Ergebnis; dazu eine Liste von Angaben, die genannt werden dürfen (Werte und Begriffe aus der Frage) |
| Bewertung | Erstautor, Bewertungsbogen `Hinweise_Bewertung_B1_B2.xlsx`, zufällige Reihenfolge |
| Akzeptabel | Prüfpunkte 1, 2 und 4 = ja und Prüfpunkt 3 mindestens teilweise |
| Stark | akzeptabel und Prüfpunkt 3 = ja |

Bewertungsanleitung (Blatt „Anleitung“, wörtlich):

```text
Aufgabe
Du bewertest den ERSTEN HINWEIS eines KI-Lernassistenten für Auszubildende (Elektrotechnik, Maschinenbau).
Lernende sehen nur die Frage und diesen Hinweis – nicht das Lehrbuch, nicht die Referenzantwort. Der Hinweis soll
zum eigenen Weiterdenken anregen, ohne die Lösung vorwegzunehmen.
Für jede Frage bekommst du: Frage, Referenzantwort, Buchstelle, den GESCHÜTZTEN KERN (darf nicht verraten werden),
die Angaben, die genannt werden DÜRFEN, und den Hinweis. Bewerte immer alle vier Prüfpunkte, auch wenn ein früherer
Prüfpunkt nicht erfüllt ist.
Prüfpunkt 1 – Fachlich korrekt (P5): ja / nein / –
Sind alle Aussagen des Hinweises fachlich richtig und auf die Aufgabe anwendbar? Ein falscher Begriff, eine falsche
Formel, ein falscher Zahlenwert oder eine irreführende Richtung → nein. „–“ nur, wenn ohne das Material nicht
entscheidbar ist (z. B. reiner Verweis auf eine Tabelle, deren Inhalt du nicht prüfen kannst).
Prüfpunkt 2 – Lösung bleibt offen (P1): ja / nein
Bleibt der geschützte Kern offen, wenn man den Hinweis ZUSAMMEN mit der Frage liest? Nennt der Hinweis die Formel
(auch in Worten, z. B. „teile die Spannung durch den Abstand“), das Ergebnis, den gesuchten Begriff oder die
Kernaussage – oder macht er sie durch eine Ja/Nein-Leitfrage eindeutig („Ist es nicht der spezifische …?“) → nein.
Angaben aus der Liste „darf genannt werden“ verraten nichts.
Prüfpunkt 3 – Hilfreicher nächster Schritt (P2–P4): ja / teilweise / nein
Gibt der Hinweis einen konkreten Schritt, den die lernende Person selbst gehen kann (eine bestimmte Größe, Einheit,
Beziehung oder Teilfrage, auf die sie achten soll)?
- ja: konkreter, umsetzbarer Schritt, der zur Lösung führt.
- teilweise: es gibt einen Schritt, aber er ist zu vage (allgemeines „überlege, wie … zusammenhängt“) ODER er gibt zu
  viel Hilfe (nimmt mehrere Denkschritte ab, ohne den Kern zu verraten). Dann in 3b „zu vage“ oder „zu viel Hilfe“.
- nein: kein Schritt (nur Umformulierung der Frage, „schau dir die Größen an“, allgemeine Ermutigung).
Prüfpunkt 3 bewertet NUR, wie konkret und umsetzbar der Schritt ist; ob er etwas verrät, entscheidet allein Prüfpunkt 2.
Prüfpunkt 4 – Verständlich und nutzbar (P6): ja / nein
Ist der Hinweis mit dem, was Lernende sehen (Frage + Hinweis), verständlich und umsetzbar? Verweise auf Text, Buch,
Lernmaterial, Tabelle, Abbildung, Spalte oder „du hast gesehen / aus dem Text / laut Material“ → nein, denn Lernende
haben das Material nicht vor sich. Unverständliche oder widersprüchliche Formulierung → nein.
Sonderfall
Der Standardtext „Für diese Frage habe ich keinen Hinweis …“ (Ersatztext der automatischen Prüfung) wird normal
bewertet: typisch 1 ja, 2 ja, 3 nein, 4 ja.
Beispiele (aus der Bewertungsanleitung)
Frage: Zwei Platten, 2 cm Abstand, 500 V. Wie groß ist die Feldstärke?
Geschützter Kern: E = U/d (auch in Worten); Ergebnis 25 kV/m. Darf genannt werden: U = 500 V, d = 2 cm, Begriff Feldstärke, Einheit V/m.
A „Du kannst die Feldstärke berechnen, wenn du die Spannung durch den Plattenabstand teilst.“
   → 1 ja, 2 nein, 3 ja, 4 ja (verrät E = U/d in Worten)
B „In welcher Einheit solltest du den Plattenabstand einsetzen, wenn das Ergebnis in V/m angegeben werden soll?“
   → 1 ja, 2 ja, 3 ja, 4 ja
C „Überleg, wie Spannung und Abstand bei den Platten zusammenhängen könnten.“
   → 1 ja, 2 ja, 3 teilweise (zu vage), 4 ja
D „Schau dir die gegebenen Größen an.“
   → 1 ja, 2 ja, 3 nein, 4 ja (kein konkreter Schritt)
E „Nutze die Formel aus Tabelle 1.3, die du gelesen hast.“
   → 1 –, 2 ja, 3 teilweise (zu vage), 4 nein (Verweis auf eine Tabelle)
Weitere typische Fälle (erfundene Fragen, nicht aus dem Fragensatz):
F Frage: „Wie heißt das Bauteil, das Wechselspannung in pulsierende Gleichspannung umwandelt?“ Kern: Gleichrichter.
   Hinweis: „Welches Bauteil sorgt dafür, dass aus Wechselspannung Gleichspannung wird?“
   → 1 ja, 2 ja, 3 nein, 4 ja (nur Umformulierung der Frage, kein neuer Denkanstoß)
G Frage: „Welche Größe ist bei einer Reihenschaltung von Widerständen an allen Widerständen gleich?“ Kern: der Strom.
   Hinweis: „Durch alle Widerstände fließt derselbe Strom – prüfe, ob das auch für die Spannung gilt.“
   → 1 ja, 2 nein, 3 ja, 4 ja (nennt den Kern direkt)
H Frage: „Wie groß ist der spezifische Widerstand von Kupfer?“ Kern: 0,0178 Ω·mm²/m.
   Hinweis: „Lies in der Tabelle in der Zeile ‚Kupfer‘ den Wert in der zweiten Spalte ab.“
   → 1 –, 2 ja, 3 ja, 4 nein (Verweis auf eine Tabelle, die Lernende nicht sehen)
Akzeptabel: Prüfpunkte 1, 2 und 4 = ja und Prüfpunkt 3 mindestens teilweise. Stark: akzeptabel und Prüfpunkt 3 = ja (stark ist Teil von akzeptabel).
```

Die 269 Hinweise mit Frage, Referenz, geschütztem Kern, erlaubten Angaben, ÜBERLEGUNG des Modells und Bewertung stehen in der Anlage `Anhang_Hinweise_Studie2.xlsx`.
