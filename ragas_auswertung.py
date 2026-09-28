"""
ragas_auswertung.py
-------------------
Offline-Auswertung der protokollierten Interaktionen nach RAGAS
(Es, James, Espinosa-Anke & Schockaert, 2023, arXiv:2309.15217).

NICHT Teil der Studien-App — läuft nach der Datenerhebung auf
evaluationsdaten/interaktionen.csv.

Stand: Schritt 5 (Datenschicht + Faithfulness v2 + Answer Relevance v3 +
Context Relevance v1).

Bewusste Abweichungen vom Original (im Methodenteil zu nennen):
  - Richter-LLM lokal (Standard qwen3.5:9b, per --judge austauschbar) statt GPT-3.5
  - Prompts auf Deutsch (Quellmaterial deutschsprachig)
  - Aussagenprüfung einzeln pro Aussage statt gebündelt (robuster bei kleinen Modellen)
  - Bewerteter Antworttext = Hinweis + Erklärung + Lösung (alles, was Lernende sehen)
  - Meta-Aussagen (Tipps an Lernende, Aussagen über den Kontext) werden verworfen und gezählt
  - Modellseitige Verweigerungen werden erkannt und NICHT bewertet (weder Faithfulness
    noch Answer Relevance), sondern separat gezählt
  - Answer Relevance: Embedding-Modell paraphrase-multilingual-MiniLM-L12-v2 (dasselbe
    wie im Retrieval) statt OpenAI text-embedding-ada-002; bewertet wird nur die
    Lösung (Stufe 3), da der Hinweis absichtlich indirekt ist
  - Context Relevance: Richter wählt benötigte Sätze per NUMMER statt sie wörtlich
    zu extrahieren (robuster bei kleinen Modellen, kein Abgleich von Textkopien nötig);
    Satzzerlegung mit _satzsplit aus rag_pipeline (dieselbe wie beim Chunking);
    identische Sätze aus der 1-Satz-Überlappung benachbarter Chunks zählen nur einmal
  - Context Relevance wird auch für modellseitige Verweigerungen berechnet (braucht
    keine Antwort); Gate-Verweigerungen haben keinen geloggten Kontext und entfallen

Prompt-Historie:
  v1: einfache Zerlegung + strikte Prüfung -> Meta-Aussagen, unaufgelöste
      Pronomen, zu wörtliche Prüfung, verstümmelte Formeln (TEST-01, F001 = 0.25
      bei inhaltlich korrekter Antwort). Ergebnisse: ragas_*_prompt_v1.csv
  v2: Few-Shot-Zerlegung, Meta-Filter, Prüfregeln für Umformulierung/Rechnung,
      Hinweis auf PDF-Extraktionsartefakte. Danach eingefroren (keine weitere
      Anpassung an dieselben Testfälle, um Überanpassung zu vermeiden).
  Answer Relevance v1: Erstversion. Befund: themengleiche, aber ausweichende
      Antwort (F007) erhielt hohen Score (0.82).
  Answer Relevance v2: zusätzliches Urteil AUSWEICHEND (noncommittal) wie in der
      ragas-Referenzimplementierung; ausweichend -> Score 0, Rohwert bleibt als ar_roh erhalten.
      Befund: Frage und Antwort im selben Prompt -> Richter kopierte die Originalfrage
      teils wörtlich (Kosinus 1.00), Score aufgebläht (F002: 0.61 -> 0.78).
  Answer Relevance v3: zwei getrennte Aufrufe — Fragengenerierung sieht NUR die Antwort
      (wie Es et al. 2023), Ausweich-Urteil separat mit Frage + Antwort.
  Context Relevance v1: Erstversion.

Start:
  python ragas_auswertung.py TEST --limit 5      # erst 5 Fälle, Details prüfen
  python ragas_auswertung.py TEST                # alle Fälle
  python ragas_auswertung.py TEST --judge mistral-nemo:12b
  python ragas_auswertung.py TEST --metriken ar --limit 5   # nur Answer Relevance testen
  python ragas_auswertung.py TEST --metriken cr --limit 5   # nur Context Relevance testen
  Hinweis: Jeder Lauf überschreibt ragas_ergebnisse.csv mit den Metriken DIESES Laufs.
"""
import argparse
import csv
import re
import time
from collections import Counter

from rag_pipeline import (
    lade_wissensbasis, berechne_kb_hash, frage_llm, _lade_embedding_modell, _satzsplit,
    INTERAKTIONS_LOG, LOG_VERZEICHNIS,
)

KB_PFAD = "knowledge_base.json"
JUDGE_MODELL_STANDARD = "mistral-nemo"
JUDGE_OPTIONEN = {"temperature": 0, "seed": 42}
PROMPT_VERSION = "F-v2/AR-v3/CR-v1"
AR_ANZAHL_FRAGEN = 3
ERGEBNIS_DATEI = LOG_VERZEICHNIS / "ragas_ergebnisse.csv"
DETAIL_DATEI = LOG_VERZEICHNIS / "ragas_faithfulness_details.csv"
AR_DETAIL_DATEI = LOG_VERZEICHNIS / "ragas_answer_relevance_details.csv"
CR_DETAIL_DATEI = LOG_VERZEICHNIS / "ragas_context_relevance_details.csv"


# =============================================================================
# Schritt 2: Datenschicht
# =============================================================================
def lade_interaktionen(pfad=INTERAKTIONS_LOG, sitzungs_praefix=None):
    with open(pfad, encoding="utf-8") as f:
        zeilen = list(csv.DictReader(f))
    if sitzungs_praefix:
        zeilen = [z for z in zeilen if z["sitzungs_id"].startswith(sitzungs_praefix)]
    return zeilen


def dedupliziere(zeilen):
    """
    Eine Zeile pro freigeschalteter Scaffolding-Stufe -> eine Frage-Antwort-
    Einheit darf nur EINMAL bewertet werden. Schlüssel (sitzungs_id, frage,
    loesung), damit wiederholte Fragen mit neuer Generierung getrennt zählen.
    Behalten: höchste erreichte Stufe, frühester Zeitstempel.
    """
    faelle = {}
    for z in zeilen:
        schluessel = (z["sitzungs_id"], z["frage"], z["loesung"])
        stufe = int(z["scaffolding_stufe_erreicht"] or 1)
        if schluessel not in faelle:
            faelle[schluessel] = {**z, "stufe_max": stufe}
        else:
            f = faelle[schluessel]
            f["stufe_max"] = max(f["stufe_max"], stufe)
            f["zeitstempel"] = min(f["zeitstempel"], z["zeitstempel"])
    return sorted(faelle.values(), key=lambda f: f["zeitstempel"])


def rekonstruiere_kontext(fall, lookup):
    ids = [i.strip() for i in fall["quellen"].split(";") if i.strip()]
    return [lookup[i] for i in ids if i in lookup], [i for i in ids if i not in lookup]


def bereite_faelle_vor(zeilen, chunks, kb_hash_aktuell):
    """
    Teilt deduplizierte Fälle in 'bewertbar' und 'ausgeschlossen' (mit Grund).
    Gate-Verweigerungen sind gewolltes Verhalten (RELEVANZ_SCHWELLE) und
    werden als Rejection Rate berichtet (Brown, Roman & Devereux 2025, §IV-C).
    """
    lookup = {c["id"]: c for c in chunks}
    bewertbar, ausgeschlossen = [], []
    for nr, fall in enumerate(dedupliziere(zeilen), start=1):
        fall["fall_id"] = f"F{nr:03d}"
        if fall["genuegend_relevanz"] != "True":
            ausgeschlossen.append({**fall, "grund": "gate_verweigerung"})
            continue
        if fall.get("kb_hash", "") != kb_hash_aktuell:
            ausgeschlossen.append({**fall, "grund": "kb_hash_abweichend"})
            continue
        kontext, fehlend = rekonstruiere_kontext(fall, lookup)
        if fehlend or not kontext:
            ausgeschlossen.append({**fall, "grund": "chunks_fehlen"})
            continue
        fall["kontext_chunks"] = kontext
        fall["geparst"] = bool(fall["hinweis"].strip() and fall["erklaerung"].strip())
        bewertbar.append(fall)
    return bewertbar, ausgeschlossen


# =============================================================================
# Modellseitige Verweigerung erkennen
# =============================================================================
# Abgeleitet aus den tatsächlichen Formulierungen von qwen3.5:9b im Testlauf
# TEST-01. Nur die ersten 300 Zeichen der Lösung werden geprüft.
# Teilantworten ("lässt sich nicht vollständig beantworten ... erwähnt lediglich")
# enthalten prüfbaren Inhalt und zählen NICHT als Verweigerung. Bewusst eng
# gefasst: Wörter wie "lediglich" allein reichen nicht, da auch vollständige
# Verweigerungen sie zur Begründung nutzen ("da der Text lediglich ... erklärt").
# Muss bei neuem Generatormodell erneut gegen echte Fälle geprüft werden.
_VERWEIGERUNG = re.compile(
    r"(kontext|textausschnitt|lernmaterial|dokument)\w*.{0,120}?(nicht|kein\w*).{0,80}?"
    r"(beantwort|antwort|finden|enthält|enthalten|informationen|angaben|fehlt|fehlen)"
    r"|(nicht|kein\w*)\s+(\w+\s+){0,3}beantwort",
    re.IGNORECASE | re.DOTALL,
)
_TEILANTWORT = re.compile(r"nicht vollständig|nur teilweise|nur zum teil", re.IGNORECASE)


def ist_modell_verweigerung(loesung):
    anfang = loesung[:300]
    return bool(_VERWEIGERUNG.search(anfang)) and not _TEILANTWORT.search(anfang)


# =============================================================================
# Schritt 3: Faithfulness
# =============================================================================
def richter(prompt, modell):
    return frage_llm(prompt, model=modell, options=JUDGE_OPTIONEN)


def antworttext(fall):
    """Alles, was Lernende sehen können. Beim Parse-Fallback steht die volle
    Rohantwort bereits in 'loesung'."""
    teile = [fall["hinweis"], fall["erklaerung"], fall["loesung"]]
    return "\n".join(t.strip() for t in teile if t.strip())


def kontexttext(fall):
    # Bewusst OHNE Thema-Titel: Die Kapitelzuordnung ist teilweise fehlerhaft
    # (siehe thema_fuer_seite-Befund) und soll das Urteil nicht beeinflussen.
    return "\n\n".join(c["text"] for c in fall["kontext_chunks"])


# Aussagen über den Lernprozess / den Kontext selbst, keine Sachaussagen.
# Werden verworfen und gezählt (Transparenz im Methodenteil).
_META_AUSSAGE = re.compile(
    r"^(du |dir |dich |achte|überlege|denke|suche|schau|versuche|um die frage|"
    r"der kontext|im kontext|aus dem kontext|im (vorliegenden )?text|der text|die texte|die quellen|die frage)",
    re.IGNORECASE,
)


def extrahiere_statements(frage, antwort, modell):
    """Rückgabe: (sachaussagen, anzahl_verworfener_metaaussagen)."""
    prompt = f"""Zerlege die Antwort in einfache, eigenständige SACHAUSSAGEN über das Fachthema.

Regeln:
1. Jede Aussage enthält genau EINEN Sachverhalt.
2. Jede Aussage muss ohne die anderen verständlich sein: Ersetze "er", "sie", "dies", "diese", "dabei" immer durch das gemeinte Nomen.
3. Formuliere Fakten direkt, ohne Verweis auf die Quelle ("Aus dem Kontext folgt, dass X" -> "X").
4. Lass WEG: Aufforderungen und Tipps an Lernende ("Achte auf...", "Überlege..."), Fragen, Aussagen über den Text, den Kontext oder die Frage selbst, Floskeln.
5. Nichts ergänzen, was nicht in der Antwort steht.
6. Eine Aussage pro Zeile, beginnend mit "- ". Sonst nichts ausgeben.

Beispiel
Antwort: Überlege, welche Größen du kennst. Aus dem Kontext folgt, dass ein Drehstrommotor einen hohen Anlaufstrom hat. Deshalb wird er über einen Frequenzumrichter gestartet.
Aussagen:
- Ein Drehstrommotor hat einen hohen Anlaufstrom.
- Ein Drehstrommotor wird wegen seines hohen Anlaufstroms über einen Frequenzumrichter gestartet.

Frage: {frage}

Antwort:
{antwort}

Aussagen:"""
    roh = richter(prompt, modell)
    aussagen, gesehen, verworfen = [], set(), 0
    for zeile in roh.splitlines():
        z = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", zeile).strip()
        if len(z) < 10:
            continue
        if _META_AUSSAGE.match(z):
            verworfen += 1
            continue
        schluessel = z.lower().rstrip(".")
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            aussagen.append(z)
    return aussagen, verworfen


def pruefe_statement_gestuetzt(aussage, kontext, modell):
    """Rückgabe: (True/False/None, Begründung). None = Urteil nicht lesbar."""
    prompt = f"""Prüfe, ob die Aussage durch den Kontext gestützt ist. Nutze AUSSCHLIESSLICH den Kontext, nicht dein eigenes Wissen.

Als GESTÜTZT (JA) gilt:
- Der Kontext enthält den Sachverhalt, auch mit anderen Worten.
- Die Aussage folgt direkt aus dem Kontext, z. B. durch Einsetzen der Zahlen aus dem Kontext in eine Formel aus dem Kontext oder durch einfaches Nachrechnen.
Als NICHT GESTÜTZT (NEIN) gilt:
- Der Sachverhalt fehlt im Kontext oder widerspricht ihm.
- Die Aussage verallgemeinert deutlich über den Kontext hinaus.

Hinweis: Der Kontext stammt aus einer PDF-Extraktion. Formeln können verstümmelt sein, z. B. "D" statt "=", "/SOH" statt "·", "/NUL" statt "−", fehlende Brüche oder Leerzeichen. Lies Formeln sinngemäß.

Kontext:
{kontext}

Aussage: {aussage}

Antworte in genau diesem Format:
BEGRÜNDUNG: <ein Satz>
URTEIL: JA oder NEIN"""
    roh = richter(prompt, modell)
    urteile = re.findall(r"URTEIL:\s*\**\s*(JA|NEIN)", roh, re.IGNORECASE)
    begruendung = re.search(r"BEGRÜNDUNG:\s*(.+)", roh)
    urteil = {"JA": True, "NEIN": False}[urteile[-1].upper()] if urteile else None
    return urteil, (begruendung.group(1).strip() if begruendung else roh[:200])


def berechne_faithfulness(fall, modell):
    """Rückgabe: (score oder None, Details-Liste, anzahl verworfener Metaaussagen)."""
    aussagen, verworfen = extrahiere_statements(fall["frage"], antworttext(fall), modell)
    kontext = kontexttext(fall)
    details = []
    for a in aussagen:
        urteil, begruendung = pruefe_statement_gestuetzt(a, kontext, modell)
        details.append({"aussage": a, "urteil": urteil, "begruendung": begruendung})
    gueltig = [d for d in details if d["urteil"] is not None]
    score = sum(d["urteil"] for d in gueltig) / len(gueltig) if gueltig else None
    return score, details, verworfen


# =============================================================================
# Schritt 4: Answer Relevance
# =============================================================================
# Idee (Es et al. 2023): Passt die Antwort zur Frage, dann lassen sich aus
# der Antwort Fragen rekonstruieren, die der Originalfrage ähneln. Gemessen
# wird NICHT die Korrektheit, sondern ob die Antwort das Gefragte adressiert.
# Eine sachlich gestützte, aber am Thema vorbeigehende Antwort (z. B. F002:
# allgemeine Metalleigenschaften statt der gefragten Gittertypen) soll hier
# niedrig abschneiden, obwohl ihre Faithfulness ordentlich ist.
def generiere_fragen(loesung, modell, n=AR_ANZAHL_FRAGEN):
    """Rekonstruiert Fragen AUS DER ANTWORT ALLEIN. Die Originalfrage wird dem
    Richter hier bewusst NICHT gezeigt: In AR-v2 (Frage im selben Prompt)
    kopierte das Modell sie teils wörtlich (Kosinus 1.00 bei F002/F007) und
    blähte so den Score auf. Entspricht dem Vorgehen bei Es et al. (2023)."""
    prompt = f"""Hier ist eine Antwort eines Lernassistenten für die technische Berufsausbildung.
Formuliere {n} unterschiedliche Fragen, auf die genau diese Antwort passt.
- Die Fragen sollen so klingen, wie Auszubildende sie stellen würden.
- Nutze nur, was in der Antwort steht.
- Eine Frage pro Zeile, beginnend mit "- ". Schreibe sonst nichts.

Antwort:
{loesung}

Fragen:"""
    roh = richter(prompt, modell)
    fragen = []
    for zeile in roh.splitlines():
        z = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", zeile).strip()
        if len(z) >= 10 and z not in fragen:
            fragen.append(z)
    return fragen[:n]


def ist_ausweichend(frage, loesung, modell):
    """Eigener Richteraufruf (Frage + Antwort): liefert die Antwort das Gefragte
    konkret? 'Ausweichend' (noncommittal) = bleibt beim Thema, liefert aber das
    Gesuchte nicht ("Die Texte nennen keine Vergleichswerte"). Solche Antworten
    erzeugen themengleiche Fragen und damit HOHE Kosinuswerte, obwohl sie nichts
    beantworten (Testbefund F007, AR-v1: 0.82). Die ragas-Referenzimplementierung
    erfasst dies ebenfalls als eigenes Urteil und setzt den Score auf 0.
    Rückgabe: True/False/None (None = Urteil nicht lesbar)."""
    prompt = f"""Prüfe, ob die Antwort die Frage konkret beantwortet.

AUSWEICHEND = JA, wenn die Antwort das Gefragte nicht liefert, z. B.
- sie sagt, dass dazu keine Angaben/Werte vorliegen,
- sie bleibt allgemein, obwohl nach einem konkreten Wert, einer Liste oder einem Verfahren gefragt ist.
AUSWEICHEND = NEIN, wenn die Antwort das Gefragte liefert (Richtigkeit spielt hier keine Rolle).

Frage: {frage}

Antwort:
{loesung}

Antworte in genau diesem Format:
BEGRÜNDUNG: <ein Satz>
AUSWEICHEND: JA oder NEIN"""
    roh = richter(prompt, modell)
    urteil = re.findall(r"AUSWEICHEND:\s*\**\s*(JA|NEIN)", roh, re.IGNORECASE)
    return (urteil[-1].upper() == "JA") if urteil else None


def berechne_answer_relevance(fall, modell):
    """Rückgabe: (score oder None, roh_score oder None, ausweichend, [(generierte_frage, cosinus), ...]).
    score = 0 bei ausweichender Antwort, sonst mittlerer Kosinus (roh_score).
    Embeddings sind normalisiert -> Skalarprodukt = Kosinus-Ähnlichkeit."""
    fragen = generiere_fragen(fall["loesung"], modell)
    ausweichend = ist_ausweichend(fall["frage"], fall["loesung"], modell)
    if not fragen:
        return None, None, ausweichend, []
    emb = _lade_embedding_modell().encode(
        [fall["frage"]] + fragen, convert_to_numpy=True, normalize_embeddings=True
    )
    cosinus = [float(emb[0] @ emb[i]) for i in range(1, len(emb))]
    roh = sum(cosinus) / len(cosinus)
    score = 0.0 if ausweichend else roh
    return score, roh, ausweichend, list(zip(fragen, cosinus))


# =============================================================================
# Schritt 5: Context Relevance
# =============================================================================
# Idee (Es et al. 2023): Welcher Anteil des abgerufenen Kontexts wird tatsächlich
# gebraucht, um die Frage zu beantworten? Misst die PRÄZISION des Retrievals
# (wie viel Ballast bekommt das Modell), nicht den Recall. Braucht keine Antwort
# und ist daher auch für modellseitige Verweigerungen berechenbar — dort
# erwartet man Werte nahe 0 (Retrieval hat das Gesuchte nicht gefunden).
def kontext_saetze(fall):
    """Abgerufener Kontext -> Satzliste. Zeilenumbrüche aus der PDF-Extraktion
    werden zu Leerzeichen; identische Sätze (1-Satz-Überlappung benachbarter
    Chunks) werden nur einmal gezählt, sonst würde der Nenner künstlich wachsen."""
    saetze, gesehen = [], set()
    for c in fall["kontext_chunks"]:
        for satz in _satzsplit(re.sub(r"\s+", " ", c["text"])):
            if len(satz) < 3 or satz in gesehen:
                continue
            gesehen.add(satz)
            saetze.append(satz)
    return saetze


def parse_benoetigt(roh, n_saetze):
    """'BENÖTIGT: 2, 5' -> [2, 5]; 'BENÖTIGT: KEINE' -> []; unlesbar -> None.
    Nummern außerhalb 1..n_saetze werden verworfen (Halluzinierte Indizes)."""
    treffer = re.findall(r"BEN(?:Ö|OE|O)TIGT:\s*\**\s*([^\n]*)", roh, re.IGNORECASE)
    if not treffer:
        return None
    wert = treffer[-1]
    nummern = [int(x) for x in re.findall(r"\d+", wert)]
    if not nummern:
        return [] if re.search(r"KEIN", wert, re.IGNORECASE) else None
    return sorted({n for n in nummern if 1 <= n <= n_saetze})


def berechne_context_relevance(fall, modell):
    """Rückgabe: (score oder None, n_saetze, benoetigte_nummern oder None, saetze, begruendung)."""
    saetze = kontext_saetze(fall)
    if not saetze:
        return None, 0, None, [], ""
    nummeriert = "\n".join(f"[{i}] {satz}" for i, satz in enumerate(saetze, start=1))
    prompt = f"""Hier sind eine Frage und nummerierte Sätze aus Lernmaterialien, die ein Suchsystem zu dieser Frage gefunden hat.
Welche Sätze werden TATSÄCHLICH benötigt, um die Frage zu beantworten?

Regeln:
- Wähle nur Sätze, die direkt zur Antwort beitragen (der gefragte Fakt, Wert, Formel oder die gefragte Begründung).
- Sätze, die nur zum selben Thema gehören, aber nichts zur Antwort beitragen, NICHT wählen.
- Beantwortet kein Satz die Frage (auch nicht teilweise), antworte mit KEINE.
- Nutze nur die Sätze, nicht dein eigenes Wissen.

Hinweis: Die Sätze stammen aus einer PDF-Extraktion. Formeln können verstümmelt sein, z. B. "D" statt "=", "/SOH" statt "·", "/NUL" statt "−". Lies sie sinngemäß.

Frage: {fall["frage"]}

Sätze:
{nummeriert}

Antworte in genau diesem Format:
BEGRÜNDUNG: <ein Satz>
BENÖTIGT: <Nummern kommagetrennt, z. B. 2, 5> oder KEINE"""
    roh = richter(prompt, modell)
    benoetigt = parse_benoetigt(roh, len(saetze))
    begruendung = re.search(r"BEGRÜNDUNG:\s*(.+)", roh)
    begruendung = begruendung.group(1).strip() if begruendung else roh[:200]
    score = len(benoetigt) / len(saetze) if benoetigt is not None else None
    return score, len(saetze), benoetigt, saetze, begruendung


def _mittel(werte):
    return sum(werte) / len(werte) if werte else None


# =============================================================================
# main
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("praefix", nargs="?", default=None, help="nur Sitzungen mit diesem Präfix, z. B. TEST")
    ap.add_argument("--limit", type=int, default=None, help="nur die ersten N Fälle")
    ap.add_argument("--judge", default=JUDGE_MODELL_STANDARD, help="Richter-Modell (Ollama-Tag)")
    ap.add_argument("--metriken", default="f,ar,cr",
                    help="Kommagetrennt: f = Faithfulness, ar = Answer Relevance, "
                         "cr = Context Relevance (Standard: alle)")
    args = ap.parse_args()
    args.metriken = [m.strip() for m in args.metriken.split(",") if m.strip()]
    mit_f, mit_ar, mit_cr = ("f" in args.metriken), ("ar" in args.metriken), ("cr" in args.metriken)

    chunks = lade_wissensbasis(KB_PFAD)
    kb_hash = berechne_kb_hash(KB_PFAD)
    zeilen = lade_interaktionen(sitzungs_praefix=args.praefix)
    bewertbar, ausgeschlossen = bereite_faelle_vor(zeilen, chunks, kb_hash)
    n_faelle = len(bewertbar) + len(ausgeschlossen)

    for f in bewertbar:
        f["modell_verweigerung"] = ist_modell_verweigerung(f["loesung"])
    verweigert = [f for f in bewertbar if f["modell_verweigerung"]]
    inhaltlich = [f for f in bewertbar if not f["modell_verweigerung"]]
    gate = sum(a["grund"] == "gate_verweigerung" for a in ausgeschlossen)

    print(f"kb_hash={kb_hash}  Filter={args.praefix or '(alle)'}  Richter={args.judge}  Prompt={PROMPT_VERSION}")
    print(f"Log-Zeilen {len(zeilen)} -> Fälle {n_faelle}")
    for grund, n in Counter(a["grund"] for a in ausgeschlossen).items():
        print(f"  ausgeschlossen ({grund}): {n}")
    print(f"Verweigerung Gate:   {gate}/{n_faelle}")
    print(f"Verweigerung Modell: {len(verweigert)}/{n_faelle}")
    for f in verweigert:
        print(f"    {f['fall_id']}: {f['frage'][:70]}")
    print(f"Inhaltliche Antworten (Faithfulness/AR-bewertbar): {len(inhaltlich)}")

    # Faithfulness/AR nur für inhaltliche Antworten; Context Relevance für ALLE
    # bewertbaren Fälle (braucht keine Antwort).
    kandidaten = bewertbar if mit_cr else inhaltlich
    ziel = kandidaten[:args.limit] if args.limit else kandidaten
    ergebnisse, f_details, ar_details, cr_details = [], [], [], []
    print(f"\nMetriken {args.metriken} für {len(ziel)} Fälle ...\n")

    for f in ziel:
        t0 = time.time()
        vw = f["modell_verweigerung"]
        zeile = {
            "fall_id": f["fall_id"], "sitzungs_id": f["sitzungs_id"], "frage": f["frage"],
            "stufe_max": f["stufe_max"], "geparst": f["geparst"], "richter": args.judge,
            "prompt_version": PROMPT_VERSION, "modell_verweigerung": vw,
        }
        ausgabe = [f["fall_id"] + (" [Verweigerung]" if vw else "")]
        details, paare, cr_info = [], [], None
        try:
            if mit_f and not vw:
                score, details, verworfen = berechne_faithfulness(f, args.judge)
                n_ja = sum(d["urteil"] is True for d in details)
                n_ungueltig = sum(d["urteil"] is None for d in details)
                zeile.update({
                    "n_aussagen": len(details), "n_gestuetzt": n_ja, "n_unlesbar": n_ungueltig,
                    "n_meta_verworfen": verworfen,
                    "faithfulness": round(score, 4) if score is not None else "",
                })
                f_details += [{"fall_id": f["fall_id"], **d} for d in details]
                ausgabe.append(f"faith={score:.2f} ({n_ja}/{len(details) - n_ungueltig})" if score is not None
                               else "faith=--")
            if mit_ar and not vw:
                ar, ar_roh, ausweichend, paare = berechne_answer_relevance(f, args.judge)
                zeile["answer_relevance"] = round(ar, 4) if ar is not None else ""
                zeile["ar_roh"] = round(ar_roh, 4) if ar_roh is not None else ""
                zeile["ausweichend"] = ausweichend if ausweichend is not None else ""
                ar_details += [{"fall_id": f["fall_id"], "frage_original": f["frage"],
                                "generierte_frage": q, "cosinus": round(c, 4)} for q, c in paare]
                if ar is None:
                    ausgabe.append("ar=--")
                else:
                    ausgabe.append(f"ar={ar:.2f}" + (f" (ausweichend, roh {ar_roh:.2f})" if ausweichend else ""))
            if mit_cr:
                cr, n_saetze, benoetigt, saetze, cr_begr = berechne_context_relevance(f, args.judge)
                cr_info = (benoetigt, saetze, cr_begr)
                zeile.update({
                    "n_kontext_saetze": n_saetze,
                    "n_benoetigt": len(benoetigt) if benoetigt is not None else "",
                    "context_relevance": round(cr, 4) if cr is not None else "",
                })
                cr_details.append({
                    "fall_id": f["fall_id"], "frage": f["frage"], "n_kontext_saetze": n_saetze,
                    "benoetigt_nr": "; ".join(map(str, benoetigt)) if benoetigt is not None else "unlesbar",
                    "benoetigte_saetze": " || ".join(saetze[i - 1] for i in (benoetigt or [])),
                    "begruendung": cr_begr,
                })
                ausgabe.append(f"cr={cr:.2f} ({len(benoetigt)}/{n_saetze})" if cr is not None else "cr=--")
        except Exception as e:
            print(f"{f['fall_id']} FEHLER: {e}")
            continue

        print(f"{'  '.join(ausgabe)}  {time.time() - t0:5.1f}s  {f['frage'][:50]}")
        if args.limit:  # im Prüfmodus Details direkt anzeigen
            for d in details:
                mark = {True: "JA  ", False: "NEIN", None: "??  "}[d["urteil"]]
                print(f"      [{mark}] {d['aussage']}")
                if d["urteil"] is not True:
                    print(f"             -> {d['begruendung'][:150]}")
            if paare:
                print(f"      Original:  {f['frage']}")
                for q, c in paare:
                    print(f"      [{c:.2f}] {q}")
            if cr_info:
                benoetigt, saetze, cr_begr = cr_info
                if benoetigt is None:
                    print(f"      CR unlesbar -> {cr_begr[:150]}")
                elif not benoetigt:
                    print(f"      CR: kein Satz benötigt -> {cr_begr[:150]}")
                for i in (benoetigt or []):
                    print(f"      [benötigt {i:>2}] {saetze[i - 1][:160]}")
        ergebnisse.append(zeile)

    # Verweigerungen, die nicht bearbeitet wurden (kein CR-Lauf), ohne Scores aufnehmen
    bearbeitet = {e["fall_id"] for e in ergebnisse}
    for f in verweigert:
        if f["fall_id"] not in bearbeitet:
            ergebnisse.append({"fall_id": f["fall_id"], "sitzungs_id": f["sitzungs_id"], "frage": f["frage"],
                               "stufe_max": f["stufe_max"], "geparst": f["geparst"], "richter": args.judge,
                               "prompt_version": PROMPT_VERSION, "modell_verweigerung": True})

    felder = ["fall_id", "sitzungs_id", "frage", "stufe_max", "geparst", "richter", "prompt_version",
              "modell_verweigerung", "n_aussagen", "n_gestuetzt", "n_unlesbar", "n_meta_verworfen",
              "faithfulness", "answer_relevance", "ar_roh", "ausweichend",
              "n_kontext_saetze", "n_benoetigt", "context_relevance"]
    with open(ERGEBNIS_DATEI, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=felder, restval="")
        w.writeheader()
        w.writerows(sorted(ergebnisse, key=lambda e: e["fall_id"]))
    if mit_f:
        with open(DETAIL_DATEI, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["fall_id", "aussage", "urteil", "begruendung"])
            w.writeheader()
            w.writerows(f_details)
    if mit_ar:
        with open(AR_DETAIL_DATEI, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["fall_id", "frage_original", "generierte_frage", "cosinus"])
            w.writeheader()
            w.writerows(ar_details)
    if mit_cr:
        with open(CR_DETAIL_DATEI, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["fall_id", "frage", "n_kontext_saetze", "benoetigt_nr",
                                               "benoetigte_saetze", "begruendung"])
            w.writeheader()
            w.writerows(cr_details)

    # --- Zusammenfassung ---
    def werte(spalte, bedingung=lambda e: True):
        return [e[spalte] for e in ergebnisse if e.get(spalte, "") != "" and bedingung(e)]

    print()
    f_w = werte("faithfulness")
    if f_w:
        print(f"Faithfulness Mittelwert:          {_mittel(f_w):.3f}  (n={len(f_w)})")
    ar_alle = [e for e in ergebnisse if e.get("answer_relevance", "") != ""]
    if ar_alle:
        n_ausw = sum(e.get("ausweichend") is True for e in ar_alle)
        roh_ok = [e["ar_roh"] for e in ar_alle if e.get("ausweichend") is not True and e.get("ar_roh", "") != ""]
        print(f"Answer Relevance Mittelwert:      {_mittel([e['answer_relevance'] for e in ar_alle]):.3f}  (n={len(ar_alle)})")
        print(f"  davon ausweichend:              {n_ausw}/{len(ar_alle)}")
        if roh_ok:
            print(f"  Rohwert nicht ausweichender:    {_mittel(roh_ok):.3f}  (n={len(roh_ok)})")
    cr_alle = werte("context_relevance")
    if cr_alle:
        cr_inh = werte("context_relevance", lambda e: not e["modell_verweigerung"])
        cr_vw = werte("context_relevance", lambda e: e["modell_verweigerung"])
        print(f"Context Relevance Mittelwert:     {_mittel(cr_alle):.3f}  (n={len(cr_alle)})")
        if cr_inh:
            print(f"  bei inhaltlichen Antworten:     {_mittel(cr_inh):.3f}  (n={len(cr_inh)})")
        if cr_vw:
            print(f"  bei Modell-Verweigerungen:      {_mittel(cr_vw):.3f}  (n={len(cr_vw)})")
        n_null = sum(v == 0 for v in cr_alle)
        print(f"  Fälle ohne benötigten Satz:     {n_null}/{len(cr_alle)}")
    print(f"Ergebnisse: {ERGEBNIS_DATEI}")


if __name__ == "__main__":
    main()