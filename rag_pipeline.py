"""
rag_pipeline.py
----------------
Kernlogik des KI-Lernassistenten (Pilotstudie, Phase 2 nach Design-Based
Research, siehe Reeves 2006 / Design-Based Research Collective 2003).

Diese Version ist für die Nutzung durch Auszubildende in einer kontrollierten
Evaluation gedacht — NICHT mehr für Demo-Zwecke. Entsprechend wurden alle
"unter die Haube schauen"-Funktionen (Chunking-Demo, PDF-Upload, TF-IDF-
Vergleich, Embedding-Visualisierung) entfernt: Alle Proband:innen sollen
exakt dieselbe, kontrollierte Wissensbasis nutzen — das ist eine bewusste
Entscheidung zur internen Validität der Studie, nicht eine technische
Einschränkung.

Jede wesentliche Design-Entscheidung ist unten mit einer Quelle referenziert.
Eine konsolidierte Übersicht steht zusätzlich in
Design_Entscheidungen_Literatur.md.
"""

import json
import os
import re
import subprocess
import csv
import datetime
from pathlib import Path

import requests
from sklearn.metrics.pairwise import cosine_similarity

MODEL_NAME = "qwen3.5:9b"


# =============================================================================
# Verbindung zum lokalen LLM (Ollama)
# =============================================================================
def _kandidaten_hosts():
    """Mögliche Ollama-Adressen, siehe WSL-Netzwerk-Hinweis in README."""
    kandidaten = []
    manuell = os.environ.get("OLLAMA_HOST")
    if manuell:
        kandidaten.append(manuell)
    kandidaten.append("localhost")
    try:
        result = subprocess.run(["ip", "route"], capture_output=True, text=True, timeout=2)
        for zeile in result.stdout.splitlines():
            if zeile.startswith("default"):
                kandidaten.append(zeile.split()[2])
                break
    except Exception:
        pass
    return kandidaten


def _finde_funktionierenden_host():
    for host in _kandidaten_hosts():
        try:
            r = requests.get(f"http://{host}:11434", timeout=1.5)
            if r.status_code == 200:
                return host
        except requests.exceptions.RequestException:
            continue
    return "localhost"


_OLLAMA_HOST = _finde_funktionierenden_host()
OLLAMA_URL = f"http://{_OLLAMA_HOST}:11434/api/generate"


# =============================================================================
# Wissensbasis-Aufbau aus echten PDF-Quellen (Offline-Werkzeug für die
# Forscherin/den Forscher, NICHT Teil der Studien-App selbst)
# =============================================================================
# Wichtig: Diese Funktionen werden von baue_wissensbasis.py genutzt, um
# EINMALIG, vor Beginn der Studie, aus echten curricularen PDFs eine feste
# Wissensbasis zu erzeugen. Studierende laden selbst keine PDFs hoch — das
# würde die Anforderung "identische Wissensbasis für alle Proband:innen"
# verletzen (siehe Design_Entscheidungen_Literatur.md, Punkt 4).
def lese_pdf_text(pfad):
    """Extrahiert reinen Text aus einer PDF-Datei, Seite für Seite."""
    from pypdf import PdfReader
    reader = PdfReader(pfad)
    seiten_texte = [seite.extract_text() or "" for seite in reader.pages]
    return "\n\n".join(seiten_texte), len(reader.pages)


def lese_pdf_gliederung(reader):
    """
    Extrahiert die im PDF eingebettete Gliederung (Bookmarks/Outline) als
    flache Liste von (Titel, Seitennummer), aufsteigend nach Seite sortiert.

    Wichtig für umfangreiche Fachbücher (z. B. ein Springer-Handbuch), die
    ein einzelnes Dokument sind, aber viele unterschiedliche Themen
    abdecken: Ohne Gliederungserkennung würde der gesamte Inhalt fälschlich
    EIN Thema (den Dateinamen) erhalten. Fachbücher aus wissenschaftlichen
    Verlagen enthalten praktisch immer eine navigierbare Gliederung im
    PDF selbst — diese wird hier statt des Dateinamens als Themenquelle
    genutzt. Das entspricht dem in der ursprünglichen Chunking-Dokumentation
    bereits als Ziel benannten "semantischen/abschnittsbasierten Chunking"
    (siehe chunke_text-Docstring), hier umgesetzt über die vom Verlag
    bereits vorhandene Struktur statt über eigene NLP-Heuristiken.
    """
    eintraege = []

    def durchlaufe(liste):
        for item in liste:
            if isinstance(item, list):
                durchlaufe(item)
            else:
                try:
                    seite = reader.get_destination_page_number(item) + 1  # 1-indiziert
                    titel = str(item.title).strip()
                    if titel:
                        eintraege.append((titel, seite))
                except Exception:
                    continue

    try:
        if reader.outline:
            durchlaufe(reader.outline)
    except Exception:
        pass

    eintraege.sort(key=lambda x: x[1])
    return eintraege


def thema_fuer_seite(seiten_nr, gliederung, fallback_thema):
    """Gibt den Titel des letzten Gliederungseintrags zurück, dessen
    Seite <= seiten_nr ist (d. h. das Kapitel/den Abschnitt, in dem sich
    diese Seite befindet). Fällt auf fallback_thema zurück, wenn keine
    Gliederung vorhanden ist oder die Seite vor dem ersten Eintrag liegt."""
    passende = [titel for titel, s in gliederung if s <= seiten_nr]
    return passende[-1] if passende else fallback_thema


def verarbeite_pdf_seitenweise(datei, max_saetze_pro_chunk, fallback_thema, methode="semantisch",
                                aehnlichkeits_schwelle=0.55, ueberlapp_saetze=1):
    """
    Verarbeitet eine PDF seitenweise: extrahiert Text pro Seite, ordnet
    jede Seite über die Gliederung ihrem Kapitel/Abschnitt zu, chunked den
    Seiteninhalt separat. Rückgabe: (chunks_ohne_id, anzahl_seiten,
    gliederung, hat_gliederung).

    methode="semantisch" (Standard): automatische, inhaltsbasierte
    Chunk-Grenzen über Embedding-Ähnlichkeit (siehe
    chunke_text_semantisch) — keine geratene Satzanzahl nötig.
    methode="fest": einfaches Chunking mit fester Satzanzahl
    (siehe chunke_text) als schnellere, aber gröbere Alternative.

    ueberlapp_saetze: Sätze, die am Ende eines Chunks auch am Anfang des
    nächsten wiederholt werden (siehe _gruppen_zu_chunks, Modran 2025).
    Mindert (löst aber NICHT vollständig) das eigene Testbefund-Muster,
    dass mehrschrittige Rechenbeispiele über mehrere Chunks fragmentiert
    werden — wirkt nur INNERHALB einer Seite, nicht über Seitengrenzen
    hinweg (siehe Trade-off unten).

    Seitenweises statt dokumentweites Chunking ist hier bewusst gewählt,
    damit jeder Chunk zuverlässig einer einzelnen Seite und damit einem
    eindeutigen Thema zugeordnet werden kann. Trade-off: Sätze, die exakt
    auf einem Seitenumbruch geteilt sind, können an der Seitengrenze leicht
    unsauber getrennt werden — für ein mehrere hundert Seiten umfassendes
    Handbuch ist die zuverlässige Themenzuordnung wichtiger als diese
    seltene Randunsauberkeit.
    """
    from pypdf import PdfReader
    reader = PdfReader(datei)
    gliederung = lese_pdf_gliederung(reader)
    hat_gliederung = len(gliederung) > 0

    alle_chunks = []
    for seiten_nr, seite in enumerate(reader.pages, start=1):
        text = seite.extract_text() or ""
        if not text.strip():
            continue
        thema = thema_fuer_seite(seiten_nr, gliederung, fallback_thema) if hat_gliederung else fallback_thema
        if methode == "semantisch":
            seiten_chunks = chunke_text_semantisch(
                text, aehnlichkeits_schwelle=aehnlichkeits_schwelle, max_saetze_pro_chunk=max_saetze_pro_chunk,
                ueberlapp_saetze=ueberlapp_saetze,
            )
        else:
            seiten_chunks = chunke_text(text, max_saetze_pro_chunk=max_saetze_pro_chunk, ueberlapp_saetze=ueberlapp_saetze)
        for c in seiten_chunks:
            if len(c["text"]) < 25:
                continue
            alle_chunks.append({"thema": thema, "text": c["text"], "seite": seiten_nr})

    return alle_chunks, len(reader.pages), gliederung, hat_gliederung


ABKUERZUNGEN = [
    "Univ.-Prof.", "apl. Prof.", "Prof.", "Dr.", "PD", "StD", "SR", "SD",
    "bzw.", "ca.", "z.B.", "u.a.", "usw.", "Nr.", "Str.", "geb.",
    "Ing.", "etc.", "vgl.", "Abs.", "Art.", "Kap.", "Hrsg.",
]
_PLATZHALTER = "\x00"


def _satzsplit(rohtext):
    """Zerlegt Text in Sätze, mit Schutz bekannter Abkürzungen (siehe
    Phase-1-Erkenntnis: "Prof. Dr. Bernd Zinn" wurde ohne diesen Schutz
    in drei Fragmente zerrissen)."""
    rohtext = rohtext.strip()
    geschuetzt = rohtext
    for abk in ABKUERZUNGEN:
        geschuetzt = geschuetzt.replace(abk, abk.replace(".", _PLATZHALTER))
    saetze = re.split(r'(?<=[.!?])\s+', geschuetzt)
    return [s.replace(_PLATZHALTER, ".").strip() for s in saetze if s.strip()]


def _gruppen_zu_chunks(gruppen, ueberlapp_saetze=0):
    """
    Wandelt rohe Satzgruppen in fertige Chunk-Dicts um und fügt dabei
    optional Überlappung zwischen aufeinanderfolgenden Chunks ein: die
    letzten 'ueberlapp_saetze' Sätze des vorherigen Chunks werden dem
    nächsten Chunk vorangestellt.

    Begründung/Quelle: Modran, H. A. (2025). Leveraging RAG with ACP & MCP
    for Adaptive Intelligent Tutoring — nutzt chunk_size=1200 Tokens mit
    overlap=200 Tokens. Wir übertragen dasselbe Prinzip auf unsere
    satzbasierte Chunking-Einheit statt auf Token-Zählung. Zweck: ein
    Fakt, der exakt an einer Chunk-Grenze liegt, verschwindet dadurch
    nicht vollständig, sondern erscheint in BEIDEN benachbarten Chunks —
    direkte Gegenmaßnahme gegen das eigene Testbefund-Muster (mehrschrittige
    Rechenbeispiele werden über mehrere Chunks fragmentiert, siehe
    Design_Entscheidungen_Literatur.md, Punkt 14).

    Wichtig: löst NICHT das Seitengrenzen-Problem (Chunks werden weiterhin
    nie über Seiten hinweg gebildet, siehe verarbeite_pdf_seitenweise) —
    wirkt nur INNERHALB einer Seite zwischen benachbarten Chunks.
    """
    if not gruppen:
        return []

    chunks = []
    for i, gruppe in enumerate(gruppen):
        if ueberlapp_saetze > 0 and i > 0:
            vorherige_gruppe = gruppen[i - 1]
            n = min(ueberlapp_saetze, len(vorherige_gruppe))
            ueberlappende_saetze = vorherige_gruppe[-n:] if n > 0 else []
            volle_gruppe = ueberlappende_saetze + gruppe
        else:
            volle_gruppe = gruppe
        chunks.append({"text": " ".join(volle_gruppe), "anzahl_saetze": len(volle_gruppe)})
    return chunks


def chunke_text(rohtext, max_saetze_pro_chunk=3, ueberlapp_saetze=1):
    """
    Satzbasiertes Chunking mit FESTER Satzanzahl pro Chunk. Einfach und
    schnell, aber die Chunk-Grenzen sind willkürlich (Satz 3 und Satz 4
    können thematisch stärker zusammengehören als Satz 2 und 3, werden
    aber trotzdem getrennt). Für neue Wissensbasis-Erstellung wird daher
    standardmäßig chunke_text_semantisch() empfohlen (siehe dort); diese
    Funktion bleibt als einfachere Alternative und für Abwärtskompatibilität
    erhalten.

    ueberlapp_saetze: siehe _gruppen_zu_chunks — Standardwert 1 statt 0,
    damit Grenzfälle abgefedert werden, ohne die einfache Methode
    grundlegend zu verändern.
    """
    saetze = _satzsplit(rohtext)
    gruppen = [saetze[i:i + max_saetze_pro_chunk] for i in range(0, len(saetze), max_saetze_pro_chunk)]
    return _gruppen_zu_chunks(gruppen, ueberlapp_saetze=ueberlapp_saetze)


def _segmentiere_nach_aehnlichkeit(saetze, aehnlichkeiten, schwelle, max_saetze_pro_chunk, min_saetze_pro_chunk):
    """
    Reine Segmentierungslogik (ohne Embedding-Berechnung), bewusst als
    eigene Funktion, damit sie ohne Embedding-Modell testbar ist.

    aehnlichkeiten[i] = Kosinus-Ähnlichkeit zwischen Satz i und Satz i+1.
    Fällt die Ähnlichkeit unter 'schwelle', wird das als thematischer
    Bruch gewertet und ein neuer Chunk begonnen. max_saetze_pro_chunk
    wirkt nur noch als Sicherheitsobergrenze (verhindert einen einzigen
    riesigen Chunk bei durchgehend ähnlichem Text), min_saetze_pro_chunk
    verhindert Ein-Wort-Chunks bei sehr kurzen, thematisch isolierten
    Sätzen (z. B. Überschriften).

    Gibt ROHE Satzgruppen zurück (Liste von Satzlisten), NICHT fertige
    Chunk-Dicts — die Umwandlung inkl. optionaler Überlappung übernimmt
    _gruppen_zu_chunks() (siehe dort), damit dieselbe Überlappungslogik für
    beide Chunking-Methoden (fest/semantisch) einheitlich gilt.
    """
    if not saetze:
        return []

    gruppen = []
    aktuelle_gruppe = [saetze[0]]

    for i in range(1, len(saetze)):
        aehnlichkeit = aehnlichkeiten[i - 1]
        bruch = aehnlichkeit < schwelle or len(aktuelle_gruppe) >= max_saetze_pro_chunk
        if bruch and len(aktuelle_gruppe) >= min_saetze_pro_chunk:
            gruppen.append(aktuelle_gruppe)
            aktuelle_gruppe = [saetze[i]]
        else:
            aktuelle_gruppe.append(saetze[i])

    gruppen.append(aktuelle_gruppe)
    return gruppen


def chunke_text_semantisch(rohtext, aehnlichkeits_schwelle=0.55, max_saetze_pro_chunk=8,
                            min_saetze_pro_chunk=1, ueberlapp_saetze=1):
    """
    Automatisches, inhaltsbasiertes Chunking — Alternative zu chunke_text()
    mit fester Satzanzahl. Statt eine Chunk-Größe zu raten, wird die
    Embedding-Ähnlichkeit zwischen aufeinanderfolgenden Sätzen gemessen;
    ein deutlicher Ähnlichkeitsabfall wird als thematischer Bruch
    interpretiert und dort ein neuer Chunk begonnen.

    Nutzt dasselbe Embedding-Modell, das ohnehin für das Retrieval geladen
    wird — es entsteht kein zusätzliches Modell, nur zusätzliche (einmalige,
    da nur beim Wissensbasis-Aufbau genutzte) Rechenzeit für die
    Satz-Embeddings.

    aehnlichkeits_schwelle=0.55 ist ein Startwert, kein empirisch
    kalibrierter Wert (siehe RELEVANZ_SCHWELLE-Hinweis zur Kalibrierung) —
    beim Wissensbasis-Aufbau mit echtem Material stichprobenartig prüfen,
    ob die entstehenden Chunks inhaltlich sinnvoll wirken, und bei Bedarf
    anpassen.

    ueberlapp_saetze: siehe _gruppen_zu_chunks (Modran 2025-Prinzip,
    Chunk-Grenzen-Überlappung).
    """
    saetze = _satzsplit(rohtext)
    if len(saetze) <= 1:
        return [{"text": s, "anzahl_saetze": 1} for s in saetze]

    modell = _lade_embedding_modell()
    embeddings = modell.encode(saetze, convert_to_numpy=True, normalize_embeddings=True)

    aehnlichkeiten = [
        float(cosine_similarity(embeddings[i:i + 1], embeddings[i + 1:i + 2])[0][0])
        for i in range(len(saetze) - 1)
    ]

    gruppen = _segmentiere_nach_aehnlichkeit(
        saetze, aehnlichkeiten, aehnlichkeits_schwelle, max_saetze_pro_chunk, min_saetze_pro_chunk
    )
    return _gruppen_zu_chunks(gruppen, ueberlapp_saetze=ueberlapp_saetze)


# =============================================================================
# Konfiguration
# =============================================================================
# Relevanz-Schwelle für Embedding-Retrieval. Ein System, das bei fehlender
# Evidenz lieber ablehnt statt zu raten, adressiert direkt das "Tug-of-War"-
# Phänomen (Modell ignoriert Retrieval-Evidenz zugunsten von internem
# Wissen), das Oche et al. (2025, "A Systematic Review of Key
# Retrieval-Augmented Generation (RAG) Systems") als zentrales RAG-Risiko
# beschreiben. Kalibriert empirisch während der Prototyp-Tests (Phase 1).
RELEVANZ_SCHWELLE = 0.35

# Schlüsselwortbasierte Sicherheitsprüfung. Bewusst einfache Version für
# Phase 1/2 (siehe Systemkonzept-Säule "Sicherheit"); eine echte
# Klassifikator-Lösung ist für Phase 3 vorgesehen.
SICHERHEITS_SCHLUESSELWOERTER = [
    
]

EMBEDDING_MODELL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

LOG_VERZEICHNIS = Path("evaluationsdaten")
LOG_VERZEICHNIS.mkdir(exist_ok=True)
INTERAKTIONS_LOG = LOG_VERZEICHNIS / "interaktionen.csv"
FRAGEBOGEN_LOG = LOG_VERZEICHNIS / "fragebogen.csv"


# =============================================================================
# Wissensbasis
# =============================================================================
def lade_wissensbasis(pfad="knowledge_base.json"):
    """
    Lädt die kuratierte, für ALLE Proband:innen identische Wissensbasis.

    Identische Wissensbasis für alle Teilnehmenden ist eine Grundvoraussetzung
    für die interne Validität eines kontrollierten Vergleichs (Standard in der
    empirischen Bildungsforschung; vgl. auch das methodische Vorgehen bei
    Modran 2025 und Happe et al. 2025, die ebenfalls mit einer festen,
    vorab kuratierten Wissensbasis pro Studiendurchlauf arbeiten).
    """
    with open(pfad, "r", encoding="utf-8") as f:
        daten = json.load(f)
    return daten["chunks"]


# =============================================================================
# Retrieval (Embeddings)
# =============================================================================
# Embedding-basiertes statt wortbasiertes (TF-IDF) Retrieval als alleinige
# Methode im Studien-Prototyp. Begründung:
#   1. Grundlagenarbeit: Reimers & Gurevych (2019), "Sentence-BERT:
#      Sentence Embeddings using Siamese BERT-Networks" — Embeddings
#      erfassen Bedeutung statt reiner Wortoberfläche.
#   2. Eigene empirische Erkenntnis aus Phase 1: TF-IDF versagt bei
#      deutschen Wortformvarianten (z. B. "einfachwirkenden" vs.
#      "einfachwirkender"), was für Auszubildende mit natürlicher,
#      variabler Frageformulierung praxisrelevant ist.
_embedding_modell = None
_chunk_embedding_cache = {}


def _lade_embedding_modell():
    global _embedding_modell
    if _embedding_modell is None:
        from sentence_transformers import SentenceTransformer
        _embedding_modell = SentenceTransformer(EMBEDDING_MODELL_NAME)
    return _embedding_modell


def _embeddings_fuer_chunks(chunks):
    modell = _lade_embedding_modell()
    schluessel = tuple(c["text"] for c in chunks)
    if schluessel not in _chunk_embedding_cache:
        embeddings = modell.encode(list(schluessel), convert_to_numpy=True, normalize_embeddings=True)
        _chunk_embedding_cache[schluessel] = embeddings
    return _chunk_embedding_cache[schluessel]


def retrieval(frage, chunks, top_k=4):
    """
    Embedding-basiertes Retrieval. top_k=4 (statt z. B. 2) reduziert das in
    Phase 1 beobachtete Risiko, dass ein einzelner, kurzer Fakt (z. B. eine
    konkrete ECTS-Zahl) durch eng verwandte, aber nicht antworttragende
    Passagen aus dem Kontext verdrängt wird (siehe eigene Testbefunde zur
    "Retrieval-Vollständigkeit", dokumentiert in Design_Entscheidungen_Literatur.md).
    """
    modell = _lade_embedding_modell()
    chunk_embeddings = _embeddings_fuer_chunks(chunks)
    frage_embedding = modell.encode([frage], convert_to_numpy=True, normalize_embeddings=True)
    scores = cosine_similarity(frage_embedding, chunk_embeddings)[0]

    ergebnisse = [{**chunk, "score": float(score)} for chunk, score in zip(chunks, scores)]
    ergebnisse.sort(key=lambda x: x["score"], reverse=True)
    return ergebnisse[:top_k], ergebnisse


# =============================================================================
# Prompt & Generierung
# =============================================================================
def baue_prompt(frage, ausgewaehlte_chunks):
    """
    Nicht-abgestuftes Prompt-Design (direkte Antwort). Bleibt als einfachere
    Alternative verfügbar; für die Studien-App wird standardmäßig
    baue_scaffolding_prompt() genutzt (siehe dort).
    """
    kontext = "\n\n".join(
        f"[Quelle {c['id']} – {c['thema']}]: {c['text']}" for c in ausgewaehlte_chunks
    )
    return f"""Du bist ein Lernassistent für die technische und berufliche Bildung.
Beantworte die folgende Frage NUR auf Basis des gegebenen Kontexts.
Wenn der Kontext die Frage nicht ausreichend beantwortet, sage das ehrlich,
anstatt zu raten. Erkläre verständlich, auf dem Niveau von Auszubildenden.

Kontext:
{kontext}

Frage: {frage}

Antwort:"""


# =============================================================================
# Pädagogisches Scaffolding: Hinweis -> Erklärung -> Lösung
# =============================================================================
# Statt die vollständige Antwort sofort zu zeigen, generiert das System DREI
# aufeinander aufbauende Stufen in einer Antwort, die im Interface schrittweise
# freigeschaltet werden. Dies setzt die im Systemkonzept (Säule
# "Lernunterstützung") bereits benannte Struktur tatsächlich um.
#
# Quellen:
#   - Happe, L., Fuchß, D., Hüttner, L., Marquardt, K. & Koziolek, A. (2025).
#     An Experience Report on a Pedagogically Controlled, Curriculum-
#     Constrained AI Tutor for SE Education. — nutzen exakt diese Struktur
#     (Hints, Explanations, Solutions als getaggte Abschnitte), dort jedoch
#     von Kursautor:innen VORAUTORIERT statt vom LLM generiert. Da uns diese
#     manuelle Autorenkapazität in Phase 2 fehlt (siehe eigene Notiz zu
#     Happe et al.: "Qualität des Scaffoldings hängt direkt vom
#     Autorenaufwand ab"), wird die Stufung hier stattdessen dynamisch per
#     Prompting erzeugt — pragmatischer Kompromiss, keine Behauptung
#     gleichwertiger Qualität.
#   - Modran, H. A. (2025). Leveraging RAG with ACP & MCP for Adaptive
#     Intelligent Tutoring. — nutzt ein steuerbares hinting_level statt
#     fester Tags; unser dreistufiges Modell ist eine vereinfachte,
#     nicht-kontinuierliche Variante desselben Grundgedankens.
#   - Neagu, A., Wong, J. T. H., Messer, M., Nelson, R. & Johnson, P. B.
#     (2026). Rethinking Scaffolding in LLM Tutors. — zeigen, dass Lernende
#     angebotenes Scaffolding in echten Deployments häufig umgehen und
#     direkte Antworten verlangen. Deshalb wird hier nicht nur ANGEBOTEN,
#     sondern auch PROTOKOLLIERT, wie weit einzelne Proband:innen die
#     Stufen tatsächlich durchlaufen (siehe protokolliere_interaktion,
#     Feld "scaffolding_stufe_erreicht") — als eigenes Uptake-Maß analog
#     zu Neagu et al., nicht nur als Angebot ohne Wirkungskontrolle.
SCAFFOLDING_MARKER = {"hinweis": "STUFE1_HINWEIS:", "erklaerung": "STUFE2_ERKLAERUNG:", "loesung": "STUFE3_LOESUNG:"}


def baue_scaffolding_prompt(frage, ausgewaehlte_chunks):
    """Fordert das Modell auf, EINE Antwort in drei klar markierten,
    aufeinander aufbauenden Stufen zu liefern (siehe Modulkommentar oben)."""
    kontext = "\n\n".join(
        f"[Quelle {c['id']} – {c['thema']}]: {c['text']}" for c in ausgewaehlte_chunks
    )
    return f"""Du bist ein Lernassistent für die technische und berufliche Bildung.
Beantworte die folgende Frage NUR auf Basis des gegebenen Kontexts, in DREI
aufeinander aufbauenden Stufen. Wenn der Kontext die Frage nicht ausreichend
beantwortet, sage das ehrlich in allen drei Stufen, anstatt zu raten.

{SCAFFOLDING_MARKER['hinweis']} Ein kurzer Hinweis (1-2 Sätze), der in die
richtige Richtung lenkt, OHNE die Antwort direkt zu verraten. Soll zum
eigenen Nachdenken anregen.

{SCAFFOLDING_MARKER['erklaerung']} Eine ausführlichere Erklärung des
relevanten Konzepts aus dem Kontext (3-4 Sätze), die der Antwort schon
näherkommt, aber noch nicht die vollständige, direkte Antwort ist.

{SCAFFOLDING_MARKER['loesung']} Die vollständige, direkte Antwort auf die
Frage, verständlich auf dem Niveau von Auszubildenden erklärt.

Halte dich EXAKT an dieses Format mit allen drei Markern.

Kontext:
{kontext}

Frage: {frage}"""


def parse_scaffolding_antwort(rohtext):
    """
    Zerlegt die vom Modell gelieferte, dreistufige Rohantwort in die
    einzelnen Stufen. Bewusst als reine, vom LLM-Aufruf getrennte Funktion,
    damit sie ohne Modell getestet werden kann.

    Fallback: Liefert das Modell nicht alle drei Marker (LLMs halten
    Formatvorgaben nicht immer exakt ein), wird der GESAMTE Rohtext als
    'loesung' verwendet und Hinweis/Erklärung leer gelassen — die
    Studien-App zeigt in diesem Fall direkt die volle Antwort, statt
    Proband:innen mit einer leeren Stufe hängenzulassen.
    """
    marker_positionen = {}
    for stufe, marker in SCAFFOLDING_MARKER.items():
        pos = rohtext.find(marker)
        if pos != -1:
            marker_positionen[stufe] = pos

    if len(marker_positionen) < 3:
        return {"hinweis": "", "erklaerung": "", "loesung": rohtext.strip(), "vollstaendig_geparst": False}

    sortiert = sorted(marker_positionen.items(), key=lambda x: x[1])
    ergebnis = {"vollstaendig_geparst": True}
    for i, (stufe, pos) in enumerate(sortiert):
        start = pos + len(SCAFFOLDING_MARKER[stufe])
        ende = sortiert[i + 1][1] if i + 1 < len(sortiert) else len(rohtext)
        ergebnis[stufe] = rohtext[start:ende].strip()

    return ergebnis


def frage_llm(prompt, model=MODEL_NAME):
    """think=False: unterdrückt Qwen3.5s sichtbare Reasoning-Kette, damit
    Proband:innen eine direkte, nicht durch Zwischenschritte verlängerte
    Antwort erhalten (relevant für Antwortzeit als Usability-Faktor,
    vgl. Perceived Ease of Use im TAM, Davis 1989)."""
    response = requests.post(
        OLLAMA_URL,
        json={"model": model, "prompt": prompt, "stream": False, "think": False},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["response"].strip()


def sicherheitspruefung(text):
    text_klein = text.lower()
    treffer = [w for w in SICHERHEITS_SCHLUESSELWOERTER if w in text_klein]
    return (len(treffer) > 0), treffer


def beantworte_frage(frage, chunks, top_k=4):
    """
    Vollständige Pipeline: Retrieval -> Schwellenwert-Prüfung -> gestufte
    Generierung (Scaffolding) -> Sicherheitsprüfung. Verweigerung statt
    Raten bei bester_score < Schwelle ist die zentrale Sicherheitsmaßnahme
    des Systems (Systemkonzept-Säule "Sicherheit"; siehe auch
    Grounding-Prinzip bei Lewis et al. 2020). Die dreistufige Antwort
    (Hinweis/Erklärung/Lösung) setzt die Säule "Lernunterstützung" um
    (siehe baue_scaffolding_prompt-Modulkommentar für Quellen).
    """
    top_chunks, alle_chunks = retrieval(frage, chunks, top_k=top_k)
    bester_score = top_chunks[0]["score"] if top_chunks else 0.0
    genuegend_relevanz = bester_score >= RELEVANZ_SCHWELLE

    ergebnis = {
        "frage": frage,
        "bester_score": bester_score,
        "genuegend_relevanz": genuegend_relevanz,
        "top_chunks": top_chunks,
    }

    if not genuegend_relevanz:
        verweigerung = (
            "Dazu habe ich in den Lernmaterialien keine ausreichend passende "
            "Quelle gefunden und möchte deshalb keine geratene Antwort geben. "
            "Bitte wende dich an deine Lehrkraft oder formuliere die Frage genauer."
        )
        ergebnis["hinweis"] = ""
        ergebnis["erklaerung"] = ""
        ergebnis["loesung"] = verweigerung
        ergebnis["vollstaendig_geparst"] = False
        ergebnis["quellen"] = []
        ergebnis["sicherheitshinweis"] = None
        return ergebnis

    prompt = baue_scaffolding_prompt(frage, top_chunks)
    rohantwort = frage_llm(prompt)
    stufen = parse_scaffolding_antwort(rohantwort)
    ist_relevant, treffer = sicherheitspruefung(frage + " " + stufen["loesung"])

    ergebnis.update(stufen)
    ergebnis["quellen"] = [{"id": c["id"], "thema": c["thema"]} for c in top_chunks]
    ergebnis["sicherheitshinweis"] = treffer if ist_relevant else None
    return ergebnis


# =============================================================================
# Evaluationsdaten: Interaktionsprotokoll
# =============================================================================
# Protokollierung von Nutzungsdaten (Frage, genutzte Quellen, Antwort,
# Sicherheitshinweis, Zeitstempel) ist im eigenen Forschungskonzept explizit
# als Datenquelle vorgesehen ("Interviews und Nutzungsdaten" im
# methodischen Vorgehen). Pseudonymisierte Sitzungs-ID statt Klarnamen
# entspricht Standardpraxis der Forschungsethik (DSGVO-konform) und dem
# in Design_Entscheidungen_Literatur.md dokumentierten Datenschutzprinzip.
def protokolliere_interaktion(sitzungs_id, ergebnis, scaffolding_stufe_erreicht=1):
    """
    scaffolding_stufe_erreicht: wie weit die/der Proband:in tatsächlich
    geklickt hat (1 = nur Hinweis gesehen, 2 = + Erklärung, 3 = + volle
    Lösung). Eigenes Uptake-Maß analog zu Neagu et al. (2026), die zeigen,
    dass Lernende angebotenes Scaffolding in der Praxis oft umgehen —
    dieses Feld macht messbar, ob dasselbe hier passiert, statt nur zu
    protokollieren, DASS Scaffolding angeboten wurde.
    """
    neu = not INTERAKTIONS_LOG.exists()
    with open(INTERAKTIONS_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if neu:
            writer.writerow([
                "zeitstempel", "sitzungs_id", "frage", "bester_score",
                "genuegend_relevanz", "hinweis", "erklaerung", "loesung",
                "scaffolding_stufe_erreicht", "quellen", "sicherheitshinweis",
            ])
        writer.writerow([
            datetime.datetime.now().isoformat(timespec="seconds"),
            sitzungs_id,
            ergebnis["frage"],
            round(ergebnis["bester_score"], 4),
            ergebnis["genuegend_relevanz"],
            ergebnis.get("hinweis", ""),
            ergebnis.get("erklaerung", ""),
            ergebnis.get("loesung", ""),
            scaffolding_stufe_erreicht,
            "; ".join(q["id"] for q in ergebnis["quellen"]),
            "; ".join(ergebnis["sicherheitshinweis"]) if ergebnis["sicherheitshinweis"] else "",
        ])


# =============================================================================
# Evaluationsdaten: Fragebogen (Technology Acceptance Model)
# =============================================================================
# Das TAM (Technology Acceptance Model, Davis 1989, "Perceived Usefulness,
# Perceived Ease of Use, and User Acceptance of Information Technology",
# MIS Quarterly) ist DAS Standardinstrument zur Akzeptanzmessung von
# Informationssystemen und wird in genau diesem Anwendungsfeld bereits von
# Happe et al. (2025) für die Evaluation eines KI-Tutors eingesetzt
# (13 Teilnehmende, PU/PEOU/ITU auf 5-Punkte-Likert-Skala) — direktes
# methodisches Vorbild für dieses Instrument.
FRAGEBOGEN_ITEMS = [
    {"id": "PU1", "dimension": "Wahrgenommener Nutzen (Perceived Usefulness)",
     "text": "Der Lernassistent hat mir geholfen, die Lerninhalte besser zu verstehen."},
    {"id": "PU2", "dimension": "Wahrgenommener Nutzen (Perceived Usefulness)",
     "text": "Die Nutzung des Lernassistenten würde meine Lerneffizienz steigern."},
    {"id": "PEOU1", "dimension": "Wahrgenommene Benutzerfreundlichkeit (Perceived Ease of Use)",
     "text": "Die Bedienung des Lernassistenten war für mich einfach und klar."},
    {"id": "PEOU2", "dimension": "Wahrgenommene Benutzerfreundlichkeit (Perceived Ease of Use)",
     "text": "Es fiel mir leicht, passende Fragen an den Lernassistenten zu formulieren."},
    {"id": "TRUST1", "dimension": "Vertrauen (Trust)",
     "text": "Ich vertraue den Antworten des Lernassistenten."},
    {"id": "TRUST2", "dimension": "Vertrauen (Trust)",
     "text": "Es war für mich nachvollziehbar, woher eine Antwort stammt (Quellenangabe)."},
    {"id": "TRUST3", "dimension": "Vertrauen (Trust)",
     "text": "Ich fand es gut, dass der Assistent auch mal 'Ich weiß es nicht' sagt, statt zu raten."},
    # Scaffolding-Items: operationalisieren direkt die Systemkonzept-Säule
    # "Lernunterstützung" (Hinweis -> Erklärung -> Lösung). SCAFF2 misst
    # bewusst nicht nur Zustimmung, sondern das Bypass-Verhalten selbst
    # (vgl. Neagu et al. 2026, Instrumentelles vs. exekutives Hilfesuchen).
    {"id": "SCAFF1", "dimension": "Lernunterstützung / Scaffolding",
     "text": "Die abgestuften Hinweise (Hinweis → Erklärung → Lösung) haben mir beim eigenständigen Lernen geholfen."},
    {"id": "SCAFF2", "dimension": "Lernunterstützung / Scaffolding",
     "text": "Ich habe meistens versucht, erst mit dem Hinweis selbst weiterzukommen, bevor ich die volle Lösung angesehen habe."},
    {"id": "ITU1", "dimension": "Nutzungsabsicht (Intention to Use)",
     "text": "Ich würde diesen Lernassistenten auch zukünftig für mein Lernen nutzen wollen."},
]


def speichere_fragebogen(sitzungs_id, antworten):
    """antworten: dict {item_id: wert (1-5)}"""
    neu = not FRAGEBOGEN_LOG.exists()
    with open(FRAGEBOGEN_LOG, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["zeitstempel", "sitzungs_id"] + [item["id"] for item in FRAGEBOGEN_ITEMS]
        if neu:
            writer.writerow(header)
        zeile = [datetime.datetime.now().isoformat(timespec="seconds"), sitzungs_id]
        zeile += [antworten.get(item["id"], "") for item in FRAGEBOGEN_ITEMS]
        writer.writerow(zeile)