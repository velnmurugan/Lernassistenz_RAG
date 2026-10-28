"""
formelsuche.py
--------------
FS-v1 (V12, 23 Oct 2026): konzeptbasierte Formelsuche für Rechenaufgaben.

Anlass: Aufgabe 1.32 (Magnetkran) im App-Test. Die Formel F = B²·A/(2μ₀) steht im Material (Böge, Chunk pdf_2620),
wurde aber nicht gefunden: Die Frage spricht von Kran, Träger, Dichte, der Formelabschnitt von Tragkraft und
Hubmagnet. Die Suche mit der Frage trifft Aufgaben mit denselben Wörtern, nicht die Formel. Ohne Formel im Kontext
verweigert das Modell die Rechnung, und der Rechenbaustein (RB-v2) startet gar nicht erst.

Ablauf (nur bei Rechenfragen):
  1. Ein kurzer Aufruf nennt 2-4 Beziehungen, die zur Lösung nötig sind, als Suchbegriffe (ohne Zahlen).
  2. Je Suchbegriff eine eigene Suche (gleiche Methode wie die Hauptsuche, mit Reranker).
  3. Aus den Treffern je Suchbegriff wird der bestbewertete Chunk übernommen, der eine Formel enthält
     (Gleichheitszeichen mit Rechenausdruck) und noch nicht im Kontext ist. Höchstens FS_MAX_ZUSATZ Chunks.
  4. Die Zusatz-Chunks stehen HINTER den ursprünglichen Chunks im Kontext (Reihenfolge der Hauptsuche bleibt).

Kosten: ein kurzer Modellaufruf (ca. 3-6 s) plus 2-4 Suchen. Bei keinem Fund ändert sich nichts.
Schalter: Umgebungsvariable LERNASSISTENT_FS:
  "FS-v2" (Standard, ab V12.1) = nur nach Fehlschlag: erst die normale Antwort; nur wenn sie keine Zahl liefert, nicht beantwortet
            oder eine fehlende Formel meldet, wird gesucht und EINMAL neu erzeugt (angenommen nur bei Zahl im Ergebnis UND wenn
            die Nachrechnung die Formel im Material belegt, ab V12.3).
  "FS-v1" = immer vor der Antwort (A/B-Test 23 Oct 2026: 15 -> 12 richtige von 22, doppelte Laufzeit, daher nicht Standard).
  "aus"   = wie V11b.
Grund für FS-v2: im A/B-Lauf verschlechterten Zusatz-Chunks bei bereits lösbaren Fragen die Antwort (2, 4, 7, 55 von richtig auf falsch).
"""
import os
import re
import time

FORMELSUCHE_VERSION = os.environ.get("LERNASSISTENT_FS", "FS-v2")  # "FS-v2" = nur nach Fehlschlag (Standard), "FS-v1" = immer, "aus" = ohne,
# "FS-v3" (V13.2) = FS-v2 + Auslöser "Ergebnis aus einem Buchbeispiel übernommen" (siehe braucht_suche_v3)
FS_MAX_PHRASEN = 4
FS_KANDIDATEN = 6        # Treffer je Suchbegriff, die auf eine Formel geprüft werden
FS_MAX_ZUSATZ = 2        # höchstens so viele Chunks werden ergänzt
FS_OPTIONEN = {"temperature": 0, "seed": 42, "num_predict": 100}
# V19 (28 Oct 2026), Schalter LERNASSISTENT_V19 (Standard aus). Buchstabe A = Formelsuche VORAB bei jeder Rechenfrage (siehe suche_v19):
# Lösungsweg in Worten -> Suchbegriffe -> billige Suche je Begriff (ohne Reranker) -> kleiner Cross-Encoder wählt die 2 besten Formel-Chunks.
V19_A = "A" in os.environ.get("LERNASSISTENT_V19", "")
V19_KANDIDATEN = 20      # so viele Formel-Chunks (fusionierte Ränge der Suchbegriffe) bewertet der kleine Cross-Encoder
V19_MODELL = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"   # ~118 Mio. Parameter, CPU, ca. 1,5 s für 20 Chunks (A/B 28 Oct: gleich gut wie bge, 10x schneller)
V19_OPTIONEN = {"temperature": 0, "seed": 42, "num_predict": 260}

_VERWEIS = re.compile(r"\b(?:Aufgabe|Aufg\.|Beispiel|Bsp\.|Abb\.|Abbildung|Tab\.|Tabelle|Gl\.|Gleichung|Kap\.|Kapitel)"
                      r"\s*\d+(?:[.,]\d+)*", re.I)
_ZAHL = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)?(?![\w])|\d+[.,]\d+")
_RECHENWORT = re.compile(r"\?|berechne|bestimme|ermittle|wie (?:groß|viel|hoch|lang|schnell|oft|stark|breit|weit)|"
                         r"welche[rsnm]?\b|wann|wieviel|gesucht|beträgt|muss", re.I)


def ist_rechenfrage(frage):
    """Frage mit mindestens zwei Zahlen (ohne Verweise wie "Aufgabe 1.32", "Abb. 2.69") und einer Fragestruktur."""
    t = _VERWEIS.sub(" ", frage or "")
    zahlen = re.findall(r"\d+(?:[.,]\d+)?", t)
    return len(zahlen) >= 2 and bool(_RECHENWORT.search(t))


_KEINE_ZAHL_HINWEIS = re.compile(r"nicht (?:direkt )?(?:im|in den) (?:Lern)?material|keine (?:passende |konkrete )?(?:Formel|Angabe|Beziehung)|"
                                 r"fehlt (?:die|eine|der)|nicht (?:exakt |direkt )?(?:beantwortet|gelöst|berechnet) werden|kann nicht", re.I)


def braucht_suche(frage, stufen):
    """FS-v2-Auslöser: Rechenfrage und die erste Antwort ist ein Fehlschlag (Status nicht BEANTWORTET, keine Zahl im
    Anfang der Lösung oder Hinweis auf fehlende Formel)."""
    if not ist_rechenfrage(frage):
        return False
    loesung = (stufen or {}).get("loesung", "") or ""
    kopf = loesung[:300]
    if (stufen or {}).get("status") in ("TEILWEISE", "NICHT_IM_MATERIAL"):
        return True
    return (not re.search(r"\d", kopf)) or bool(_KEINE_ZAHL_HINWEIS.search(kopf))


def braucht_suche_v3(frage, stufen, kontext):
    """FS-v3-Auslöser (V13.2): wie FS-v2, zusätzlich wenn die erste Antwort ein Ergebnis aus dem Lernmaterial übernimmt, ohne
    mit den Werten der Frage zu rechnen (rechenpruefung.pruefe_uebernahme). Anlass: Entwicklungsfall Käfigläufer (26 Oct 2026):
    Antwort 1401 min⁻¹ aus Buchaufgabe 4.9 mit anderen Werten; die Formelsuche fand die durchgerechnete Lösung (S. 452),
    die Hauptsuche hatte sie nicht im Top 4."""
    if braucht_suche(frage, stufen):
        return True
    if not ist_rechenfrage(frage) or (stufen or {}).get("status") != "BEANTWORTET":
        return False
    import rechenpruefung
    return bool(rechenpruefung.pruefe_uebernahme((stufen or {}).get("loesung", ""), frage, kontext))


def antwort_hat_ergebnis(stufen):
    """Neue Antwort wird nur angenommen, wenn sie beantwortet ist und im Anfang der Lösung eine Zahl nennt."""
    loesung = (stufen or {}).get("loesung", "") or ""
    return (stufen or {}).get("status") == "BEANTWORTET" and bool(re.search(r"\d", loesung[:300])) \
        and not _KEINE_ZAHL_HINWEIS.search(loesung[:300])


def baue_prompt(frage):
    return f"""Eine Rechenaufgabe aus der Technik soll gelöst werden. Nenne die physikalischen oder technischen Beziehungen (Formeln), die man dafür braucht, als kurze Suchbegriffe, so wie sie in einem Lehrbuch als Überschrift oder im Fließtext stehen.

Regeln:
- 2 bis 4 Zeilen, eine Beziehung pro Zeile.
- Je 2 bis 6 Wörter, nur Fachbegriffe (Gesetz, Größe, Bauteil). Keine Zahlen, keine Formeln, keine Einheiten, keine Sätze.
- Auch einfache Hilfsbeziehungen nennen (z. B. Masse aus Dichte und Volumen).
- Beispiele für die Form: "Kraft zwischen Kondensatorplatten", "Leistung im Drehstromnetz".
- Keine Erklärung, keine Nummerierung.

### Aufgabe
{frage}

### Suchbegriffe"""


def parse(roh):
    """Zeilen -> Suchbegriffe (ohne Aufzählungszeichen, Anführungszeichen, Zahlen). Höchstens FS_MAX_PHRASEN."""
    phrasen = []
    for zeile in (roh or "").splitlines():
        z = re.sub(r"^[\s\-–—*•\d.)(:]+", "", zeile).strip().strip("\"'„“”`*").strip(" .;:")
        if not (3 <= len(z) <= 70) or re.search(r"\d|=", z):
            continue
        if re.match(r"(?i)(suchbegriffe|aufgabe|regeln|beispiel)", z):
            continue
        if z.lower() not in [p.lower() for p in phrasen]:
            phrasen.append(z)
    return phrasen[:FS_MAX_PHRASEN]


# Gleichung: kurzes Formelzeichen, "=", dann etwas mit Rechenzeichen oder Klammer/Bruch/Hochzahl/Wurzel
_FORMEL = re.compile(r"[A-Za-zα-ωΑ-ΩΔηφϑ][A-Za-z0-9α-ωΑ-Ω_₀-₉′'^]{0,6}\s*=\s*[^=\n]{0,60}[·*/÷×+\-−√²³()]")


def hat_formel(text):
    """True, wenn der Text eine Formel (Zeichen = Ausdruck mit Rechenzeichen) enthält."""
    t = text or ""
    return bool(_FORMEL.search(t))


def suche(frage, chunks, top_chunks, retrieval_fn, llm_fn, methode=None, max_zusatz=None):
    """Rückgabe (zusatz_chunks, info). info: phrasen, ids, sekunden, fehler. Wirft keine Ausnahme nach außen."""
    max_zusatz = FS_MAX_ZUSATZ if max_zusatz is None else max_zusatz
    info = {"phrasen": [], "ids": [], "sekunden": 0.0, "fehler": ""}
    t0 = time.perf_counter()
    zusatz = []
    try:
        info["phrasen"] = parse(llm_fn(baue_prompt(frage), options=FS_OPTIONEN))
        vorhanden = {c["id"] for c in top_chunks}
        for phrase in info["phrasen"]:
            if len(zusatz) >= max_zusatz:
                break
            treffer, _ = retrieval_fn(phrase, chunks, top_k=FS_KANDIDATEN, methode=methode)
            for c in treffer:
                if c["id"] in vorhanden or not hat_formel(c.get("text", "")):
                    continue
                zusatz.append({**c, "fs_phrase": phrase})
                vorhanden.add(c["id"])
                break  # ein Chunk je Suchbegriff
        info["ids"] = [c["id"] for c in zusatz]
    except Exception as e:  # darf die Antwort nie verhindern
        info["fehler"] = str(e)[:120]
        zusatz = []
    info["sekunden"] = round(time.perf_counter() - t0, 1)
    return zusatz, info


def notiz(info):
    """Kurzer Protokolltext für rechen_befund (kein Muster, das die Oberfläche als Chip liest)."""
    if info.get("fehler"):
        return "FS Fehler"
    ids = ", ".join(info.get("ids", [])) or "kein Zusatz"
    text = f"Suchbegriffe: {'; '.join(info.get('phrasen', []))} | ergänzt: {ids}"
    if info.get("ausgeloest"):
        grund = ("FS-v3 ausgelöst (erste Antwort ohne Ergebnis oder aus Buchbeispiel übernommen)" if info.get("version", FORMELSUCHE_VERSION) == "FS-v3"
                 else "FS-v2 ausgelöst (erste Antwort ohne Ergebnis)")
        return (f"{grund} {text} | neu erzeugt: {'ja' if info.get('neu') else 'nein'}"
                f" | angenommen: {'ja' if info.get('angenommen') else 'nein'}")
    return f"FS-v1 {text}"


# ---------------------------------------------------------------------------------------------------------------------
# V19a: Formelsuche vorab (28 Oct 2026). Anlass: Fälle, in denen die Hauptsuche die nötige Formel nicht findet, die erste Antwort
# aber trotzdem eine Zahl nennt (falsche Physik) – FS-v2/v3 startet dann nie. Messung (diagnose_formelsuche_varianten.py, 11 gültige
# Aufgaben): Formel im Kontext Hauptsuche Top-4 8/11; + 2 Chunks nach diesem Verfahren 10/11 (Kosten ca. 1,5 s + 1 kurzer Modellaufruf).
# ---------------------------------------------------------------------------------------------------------------------
_P_WEG = """Eine Rechenaufgabe aus der Technik soll gelöst werden. Beschreibe zuerst in 2 bis 4 kurzen Zeilen den Lösungsweg in Worten: welche Größe berechnet man nacheinander (z. B. "Strom aus Leistung und Spannung"). Keine Zahlen.
Schreibe danach eine Zeile "### Suchbegriffe" und darunter je Schritt einen Fachbegriff (2 bis 6 Wörter), unter dem die dafür nötige Beziehung in einem Lehrbuch steht (Gesetz, Größe, Bauteil, Schaltung). Keine Zahlen, keine Formeln.

### Aufgabe
{frage}

### Lösungsweg"""
_ce = [None]


def baue_prompt_weg(frage):
    return _P_WEG.format(frage=frage)


def parse_weg(roh):
    """Suchbegriffe nach der Zeile '### Suchbegriffe' (ohne Zahlen/Gleichungen, höchstens FS_MAX_PHRASEN). Ohne Marke: leer."""
    teil = (roh or "").split("### Suchbegriffe", 1)[1] if "### Suchbegriffe" in (roh or "") else ""
    return parse(teil)


def fuse_raenge(listen, k=10):
    """Reciprocal Rank Fusion (Cormack et al. 2009) über mehrere ID-Listen."""
    score = {}
    for liste in listen:
        for n, i in enumerate(liste, 1):
            score[i] = score.get(i, 0.0) + 1.0 / (k + n)
    return [i for i, _ in sorted(score.items(), key=lambda x: -x[1])]


def _bewerte_klein(query, texte):
    """Relevanzwerte des kleinen Cross-Encoders (lädt beim ersten Aufruf; Texte wie in reranker.py bereinigt)."""
    if _ce[0] is None:
        from sentence_transformers import CrossEncoder
        _ce[0] = CrossEncoder(V19_MODELL, max_length=512, device="cpu")
    paare = [(query, re.sub(r"\s+", " ", re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)).strip()) for t in texte]
    return [float(w) for w in _ce[0].predict(paare, batch_size=16, show_progress_bar=False)]


def suche_v19(frage, chunks, top_chunks, retrieval_fn, llm_fn, bewerte_fn=None):
    """Rückgabe (zusatz_chunks, info). info: phrasen, ids, kandidaten, sekunden, fehler. Wirft keine Ausnahme nach außen.
    Ablauf: 1 kurzer Modellaufruf (Lösungsweg -> Suchbegriffe); je Suchbegriff eine Suche OHNE Reranker (hybrid_kg, ca. 0,2 s);
    Rangfusion; nur Chunks mit Formel, die noch nicht im Kontext sind (höchstens V19_KANDIDATEN); der kleine Cross-Encoder
    bewertet sie GEGEN DIE ZUSAMMENGESETZTEN Suchbegriffe; die 2 besten werden ergänzt (FS_MAX_ZUSATZ)."""
    info = {"phrasen": [], "ids": [], "kandidaten": 0, "sekunden": 0.0, "fehler": ""}
    t0 = time.perf_counter()
    zusatz = []
    try:
        info["phrasen"] = parse_weg(llm_fn(baue_prompt_weg(frage), options=V19_OPTIONEN))
        if info["phrasen"]:
            vorhanden = {c["id"] for c in top_chunks}
            listen, byid = [], {}
            for phrase in info["phrasen"]:
                _, voll = retrieval_fn(phrase, chunks, top_k=6, methode="hybrid_kg")
                listen.append([c["id"] for c in voll[:300]])
                for c in voll[:300]:
                    byid.setdefault(c["id"], c)
            kand = [i for i in fuse_raenge(listen) if i not in vorhanden and hat_formel(byid[i].get("text", ""))][:V19_KANDIDATEN]
            info["kandidaten"] = len(kand)
            if kand:
                werte = (bewerte_fn or _bewerte_klein)(" ".join(info["phrasen"]), [byid[i]["text"] for i in kand])
                beste = [i for i, _ in sorted(zip(kand, werte), key=lambda x: -x[1])][:FS_MAX_ZUSATZ]
                zusatz = [{**byid[i], "fs_phrase": "V19a"} for i in beste]
                info["ids"] = beste
    except Exception as e:  # darf die Antwort nie verhindern
        info["fehler"] = f"{type(e).__name__}: {e}"[:120]
        zusatz = []
    info["sekunden"] = round(time.perf_counter() - t0, 1)
    return zusatz, info


def notiz_v19(info):
    """Kurzer Protokolltext für rechen_befund (kein Muster, das die Oberfläche als Chip liest)."""
    if info.get("fehler"):
        return "Formelsuche vorab Fehler: " + info["fehler"]
    return (f"Formelsuche vorab (V19a): Suchbegriffe: {'; '.join(info.get('phrasen', [])) or 'keine'} | Kandidaten: {info.get('kandidaten', 0)}"
            f" | ergänzt: {', '.join(info.get('ids', [])) or 'kein Zusatz'}")
