"""
Lernhilfen (UI Drop 2): Anschlussfragen, Übungsfrage, Auswertung des Nutzungsprotokolls.

- Anschlussfragen und Übungsfrage entstehen NUR aus den Textabschnitten, die auch für die Antwort
  verwendet wurden (kein Fremdwissen). Die Übungsfrage ist nie eine Rechenaufgabe; ihre Musterantwort
  muss sich im Material wiederfinden (Prüfung `_im_material`), sonst wird sie verworfen.
- Die Antwort auf die Übungsfrage wird wie eine "Idee" bewertet (ideen_feedback.gib_feedback, IF-v5/FP-v3).
- Protokoll: evaluationsdaten/lernhilfen.csv (eigene Datei, interaktionen.csv bleibt unverändert).
Datenschutz: wie interaktionen.csv (nur Sitzungs-ID, kein Name) -> in .gitignore.
"""
import csv
import datetime
import re
import time

from rag_pipeline import frage_llm, GENERIERUNGS_OPTIONEN, _kontext_text, LOG_VERZEICHNIS

LERNHILFEN_LOG = LOG_VERZEICHNIS / "lernhilfen.csv"
LERNHILFEN_FELDER = ["zeitstempel", "sitzungs_id", "frage_nr", "typ", "text", "antwort", "urteil", "sekunden"]


def protokolliere(sitzungs_id, frage_nr, typ, text="", antwort="", urteil="", sekunden=""):
    neu = not LERNHILFEN_LOG.exists()
    with open(LERNHILFEN_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LERNHILFEN_FELDER)
        if neu:
            w.writeheader()
        w.writerow({"zeitstempel": datetime.datetime.now().isoformat(timespec="seconds"),
                    "sitzungs_id": sitzungs_id, "frage_nr": frage_nr, "typ": typ, "text": text,
                    "antwort": antwort, "urteil": urteil, "sekunden": sekunden})


_ZAHL = re.compile(r"(?<![A-Za-zÄÖÜäöüß_])\d")  # Ziffern in Bezeichnungen (A1, B2, F1) zählen nicht


def _hat_zahl(text):
    return bool(_ZAHL.search(text or ""))


def _woerter(text):
    return set(re.findall(r"[a-zäöüß]{4,}", (text or "").lower()))


def _stamm(woerter, n=6):
    return {w[:n] for w in woerter}


def _im_material(text, kontext, anteil=0.7):
    """Mindestens `anteil` der Inhaltswörter von `text` kommen im Material vor (Vergleich über die ersten
    sechs Buchstaben, damit Endungen wie Bauteil/Bauteils nicht stören)."""
    w = _stamm(_woerter(text))
    return bool(w) and len(w & _stamm(_woerter(kontext))) / len(w) >= anteil


def ist_numerisch(ergebnis):
    """Rechenaufgaben bekommen keine Übungsfrage (die Rechenprüfung deckt nur die Antwort ab)."""
    return _hat_zahl(ergebnis.get("frage", "") + " " + ergebnis.get("loesung", "")[:200])


# --- Anschlussfragen ----------------------------------------------------------------------------------
def baue_folgefragen_prompt(frage, top_chunks):
    return f"""Du hilfst Auszubildenden beim Lernen. Unten steht Lernmaterial und die Frage, die gerade gestellt wurde.

Schlage genau drei kurze Anschlussfragen vor, mit denen die Person das Thema weiter vertiefen kann.
Regeln:
- Jede Frage muss sich allein mit dem Lernmaterial unten beantworten lassen.
- Jede Frage muss für sich allein verständlich sein (kein „wie oben", kein „davon").
- Keine Rechenaufgaben, keine Zahlen in der Frage, keine Wiederholung der gestellten Frage.
- Höchstens 15 Wörter pro Frage.

### Gestellte Frage
{frage}

### Lernmaterial
{_kontext_text(top_chunks)}

Antworte genau so:
1. <Frage>
2. <Frage>
3. <Frage>"""


def parse_folgefragen(roh, frage, kontext):
    """Bis zu drei Fragen; verworfen werden Wiederholungen der Frage, Zahlenfragen und Fragen,
    deren Begriffe im Material nicht vorkommen."""
    ergebnis = []
    for zeile in (roh or "").splitlines():
        m = re.match(r"\s*\d+[.)]\s*(.+\?)\s*$", zeile)
        if not m:
            continue
        q = m.group(1).strip()
        if _hat_zahl(q) or len(q.split()) > 18:
            continue
        if _woerter(q) <= _woerter(frage) or not _im_material(q, kontext, anteil=0.5):
            continue
        ergebnis.append(q)
    return ergebnis[:3]


def folgefragen(ergebnis):
    roh = frage_llm(baue_folgefragen_prompt(ergebnis["frage"], ergebnis["top_chunks"]), options=GENERIERUNGS_OPTIONEN)
    return parse_folgefragen(roh, ergebnis["frage"], _kontext_text(ergebnis["top_chunks"]))


# --- Übungsfrage --------------------------------------------------------------------------------------
def baue_uebung_prompt(frage, top_chunks):
    return f"""Du erstellst eine Übungsfrage für Auszubildende zum selben Thema wie die gerade gestellte Frage.

Regeln:
- Die Übungsfrage muss sich mit dem Lernmaterial unten in ein bis zwei Sätzen beantworten lassen.
- Keine Rechenaufgabe, keine Zahlen in der Frage.
- Es darf nicht dieselbe Frage sein wie die gestellte.
- Die Musterantwort besteht aus ein bis zwei Sätzen, die so im Material stehen.

### Gestellte Frage
{frage}

### Lernmaterial
{_kontext_text(top_chunks)}

Antworte genau so:
FRAGE: <Übungsfrage>
MUSTERANTWORT: <Antwort>"""


def parse_uebung(roh, frage, kontext):
    m = re.search(r"(?is)FRAGE\s*:\s*(.+?)\s*MUSTERANTWORT\s*:\s*(.+)", roh or "")
    if not m:
        return None
    q, a = m.group(1).strip(), m.group(2).strip()
    if "?" not in q or _hat_zahl(q) or _woerter(q) <= _woerter(frage):
        return None
    if not _im_material(a, kontext):
        return None
    return {"frage": q, "loesung": a}


def uebungsfrage(ergebnis):
    """-> {"frage", "loesung"} oder None (nicht passend / nicht belegt)."""
    roh = frage_llm(baue_uebung_prompt(ergebnis["frage"], ergebnis["top_chunks"]), options=GENERIERUNGS_OPTIONEN)
    return parse_uebung(roh, ergebnis["frage"], _kontext_text(ergebnis["top_chunks"]))


def uebung_bewerten(uebung, antwort, top_chunks):
    from ideen_feedback import gib_feedback
    pseudo = {"frage": uebung["frage"], "hinweis": "", "loesung": uebung["loesung"], "top_chunks": top_chunks}
    return gib_feedback(pseudo, antwort)


# --- Auswertung -----------------------------------------------------------------------------------------
def lies_csv(pfad):
    if not pfad.exists():
        return []
    with open(pfad, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def auswertung(sitzung=None):
    """Kennzahlen aus den Protokollen (alle Sitzungen oder eine). Rückgabe: dict."""
    from rag_pipeline import INTERAKTIONS_LOG
    from ideen_feedback import IDEEN_LOG
    ok = (lambda r: True) if not sitzung else (lambda r: r.get("sitzungs_id") == sitzung)
    inter = [r for r in lies_csv(INTERAKTIONS_LOG) if ok(r)]
    ideen = [r for r in lies_csv(IDEEN_LOG) if ok(r)]
    hilfen = [r for r in lies_csv(LERNHILFEN_LOG) if ok(r)]
    ohne_demo = [r for r in inter if not str(r.get("sitzungs_id", "")).startswith("TEST")] if not sitzung else inter
    # Mehrere Zeilen je Frage (Stufe 1, dann Stufe 2): pro (Sitzung, Frage) die höchste Stufe
    je_frage = {}
    for r in inter:
        k = (r.get("sitzungs_id"), r.get("frage"))
        je_frage[k] = max(je_frage.get(k, 0), int(r.get("scaffolding_stufe_erreicht") or 1))
    status = {}
    for r in inter:
        if str(r.get("scaffolding_stufe_erreicht")) == "1":
            status[r.get("status") or "?"] = status.get(r.get("status") or "?", 0) + 1
    urteile = {}
    for r in ideen:
        urteile[r.get("urteil")] = urteile.get(r.get("urteil"), 0) + 1
    typen = {}
    for r in hilfen:
        typen[r["typ"]] = typen.get(r["typ"], 0) + 1
    return {
        "sitzungen": len({r.get("sitzungs_id") for r in inter}),
        "fragen": len(je_frage),
        "loesung_geoeffnet": sum(1 for s in je_frage.values() if s >= 2),
        "status": status, "ideen": len(ideen), "urteile": urteile, "hilfen": typen,
        "tabelle": [{"Zeit": r["zeitstempel"][11:16], "Frage": r["frage"],
                     "Stufe": r.get("scaffolding_stufe_erreicht"), "Status": r.get("status")} for r in inter][-30:],
        "ohne_demo": len(ohne_demo),
    }
