"""
ideen_feedback.py
-----------------
"Deine Idee?" — Rückmeldung auf einen eigenen Lösungsversuch der/des Lernenden
(Scaffolding-Spezifikation S-v1, Entscheidung D2; claude/Scaffolding_Spezifikation.md).

Ablauf in der Studien-App: Hinweis -> (optional) eigene Idee eintippen ->
kurze Rückmeldung, die die Lösung NICHT verrät -> Lösung (ab V4 zwei Stufen;
die Rückmeldung ersetzt die frühere Erklärungs-Stufe).
Bis zu MAX_VERSUCHE Ideen pro Frage, solange die Lösung noch nicht geöffnet ist.

Warum (Quellen aus der Notion-Leseliste, Details in der Spezifikation):
  - Eigener Versuch vor jeder Hilfestufe: Vendrell & Johnston (2026), P1 + P8.
  - Rückmeldung = Stufe 2 der Hint-Leiter ("targeted feedback": einen Schritt
    der/des Lernenden prüfen): Zourlidou et al. (2026, AIED).
  - Kompetenzförderliche Rückmeldung (erst was stimmt, dann was fehlt): Klein et
    al. (2026, CHI), P4.
  - "Answer-aware": das Modell bekommt die (geheime) Lösung, damit es die Idee
    beurteilen kann, ohne sie zu verraten: Bhaskar & Hamouda (2025); kleine
    Modelle (Qwen3-8B) geben bessere Tutor-Antworten mit Musterlösung:
    Petukhova, Nguyen & Kochmar (2026).
  - Erst eine kurze Überlegung, dann die Antwort ("pedagogical reasoning"):
    senkte das Verraten der Lösung bei Qwen-32B von 46 % auf 2 %
    (Zhao, Knežević & Käser, 2026). Die Überlegung wird NICHT angezeigt.
  - Bewertungsdimensionen (Mistake Identification, Revealing Answer, Providing
    Guidance, Actionability, Tone): Maurya et al. (2025, MRBench).
  - Bei echten Lernenden waren Rückmeldungen auf eigene Versuche ("verification
    feedback") die wirksamste Antwortart: Abrar, Sharmin & Barmaki (2027).

Datenschutz: Die Ideen sind Lernendendaten -> evaluationsdaten/ideen_feedback.csv
gehört in .gitignore (wie interaktionen.csv und fragebogen.csv).
"""
import csv
import datetime
import re
import time

from rag_pipeline import frage_llm, GENERIERUNGS_OPTIONEN, MODEL_NAME, LOG_VERZEICHNIS

FEEDBACK_PROMPT_VERSION = "IF-v1"
MAX_VERSUCHE = 3
IDEEN_LOG = LOG_VERZEICHNIS / "ideen_feedback.csv"
URTEILE = ("richtig", "teilweise", "falsch", "keine_idee")
IDEEN_LOG_FELDER = [
    "zeitstempel", "sitzungs_id", "frage_nr", "frage", "versuch_nr", "stufe_beim_versuch",
    "idee", "urteil", "rueckmeldung", "ueberlegung", "geparst", "leck_zahlen",
    "sekunden", "prompt_version", "modell", "kb_hash",
]

# Wird angezeigt, wenn das Modell das Format nicht einhält. Der Rohtext wird NIE
# angezeigt, weil er die (geheime) Überlegung mit der Lösung enthalten kann.
FALLBACK_RUECKMELDUNG = (
    "Danke für deine Idee! Ich konnte sie gerade nicht automatisch prüfen. "
    "Vergleiche sie mit der Lösung, wenn du sie öffnest."
)


def baue_feedback_prompt(frage, top_chunks, hinweis, loesung, idee):
    kontext = "\n\n".join(f"[{c['thema']}]: {c['text']}" for c in top_chunks)
    return f"""Du bist ein Lernassistent für Auszubildende in technischen Berufen. Ein:e Auszubildende:r hat eine Frage gestellt, einen Hinweis bekommen und schreibt jetzt eine eigene Idee zur Antwort. Gib eine kurze Rückmeldung zu dieser Idee.

=== Nur für dich (die/der Auszubildende sieht das NICHT) ===
Lernmaterial:
{kontext}

Musterlösung (geheim):
{loesung}

=== Was die/der Auszubildende gesehen und geschrieben hat ===
Frage: {frage}
Hinweis: {hinweis}
Eigene Idee: {idee}

Regeln:
1. Beurteile die Idee nur anhand des Lernmaterials und der Musterlösung.
2. Verrate die Lösung NICHT: keine Ergebnisse, Zahlenwerte oder Formeln aus der Musterlösung und nicht die gesuchte Kernaussage, wenn sie nicht schon in der Idee steht.
3. Beginne mit dem, was an der Idee stimmt (falls etwas stimmt).
4. Ist die Idee teilweise richtig oder falsch: nenne genau EINE Stelle, die nicht stimmt oder fehlt, ohne sie zu korrigieren. Stelle dann eine Frage oder nenne einen nächsten Denkschritt.
5. Ist die Idee richtig: bestätige das kurz.
6. Ist keine Idee erkennbar (z. B. „keine Ahnung"): ermutige und nenne einen ersten kleinen Denkschritt.
7. Sprich die/den Auszubildende:n mit „du" an. Höchstens 3 Sätze. Schreibe nicht „der Kontext", „das Lernmaterial" oder „die Musterlösung", denn die/der Auszubildende sieht sie nicht.

Antworte GENAU in diesem Format:
UEBERLEGUNG: <kurz, nur für dich: Was stimmt, was fehlt, wie lenke ich, ohne die Lösung zu verraten?>
URTEIL: <richtig | teilweise | falsch | keine_idee>
RUECKMELDUNG: <deine Rückmeldung an die/den Auszubildende:n>"""


_MARKER = {
    "ueberlegung": re.compile(r"\b(?:UEBERLEGUNG|ÜBERLEGUNG)\s*:", re.IGNORECASE),
    "urteil": re.compile(r"\bURTEIL\s*:", re.IGNORECASE),
    "rueckmeldung": re.compile(r"\b(?:RUECKMELDUNG|RÜCKMELDUNG)\s*:", re.IGNORECASE),
}


def parse_feedback(rohtext):
    """Zerlegt die Modellantwort. Ohne RUECKMELDUNG-Marker: geparst=False und
    Fallback-Text (nie den Rohtext zeigen)."""
    positionen = {}
    for feld, muster in _MARKER.items():
        m = muster.search(rohtext)
        if m:
            positionen[feld] = (m.start(), m.end())
    teile = {"ueberlegung": "", "urteil": "", "rueckmeldung": ""}
    sortiert = sorted(positionen.items(), key=lambda x: x[1][0])
    for i, (feld, (_, ende)) in enumerate(sortiert):
        stop = sortiert[i + 1][1][0] if i + 1 < len(sortiert) else len(rohtext)
        teile[feld] = rohtext[ende:stop].strip()

    urteil_roh = teile["urteil"].lower().replace("-", "_").replace(" ", "_")
    urteil = next((u for u in URTEILE if urteil_roh.startswith(u)), "unbekannt")
    if urteil == "unbekannt" and urteil_roh.startswith("keine"):
        urteil = "keine_idee"
    geparst = bool(teile["rueckmeldung"])
    return {
        "ueberlegung": teile["ueberlegung"],
        "urteil": urteil,
        "rueckmeldung": teile["rueckmeldung"] if geparst else FALLBACK_RUECKMELDUNG,
        "geparst": geparst,
    }


_ZAHL = re.compile(r"\d+(?:[.,]\d+)?")


def _zahlen(text):
    return {z.replace(",", ".") for z in _ZAHL.findall(text or "")}


def leck_zahlen(rueckmeldung, loesung, *sichtbar):
    """Einfacher Regel-Check auf verratene Ergebnisse: Zahlen in der Rückmeldung,
    die in der Lösung stehen, aber nicht in dem, was die/der Lernende schon
    gesehen oder geschrieben hat (Frage, Hinweis, Idee).
    Wird nur PROTOKOLLIERT, nicht eingegriffen (erst messen, dann entscheiden).
    Erfasst keine verratenen Begriffe -> menschliche Bewertung bleibt nötig."""
    bekannt = set().union(*(_zahlen(t) for t in sichtbar))
    return sorted((_zahlen(rueckmeldung) & _zahlen(loesung)) - bekannt)


def gib_feedback(ergebnis, idee, sichtbar_extra=""):
    """ergebnis: Rückgabe von beantworte_frage (mit top_chunks, hinweis, loesung).
    sichtbar_extra: weiterer bereits sichtbarer Text (für den Leck-Check; ab V4 meist leer)."""
    t0 = time.time()
    prompt = baue_feedback_prompt(ergebnis["frage"], ergebnis["top_chunks"],
                                  ergebnis["hinweis"], ergebnis["loesung"], idee)
    fb = parse_feedback(frage_llm(prompt, options=GENERIERUNGS_OPTIONEN))
    fb["idee"] = idee
    fb["sekunden"] = round(time.time() - t0, 1)
    fb["leck_zahlen"] = leck_zahlen(fb["rueckmeldung"], ergebnis["loesung"],
                                    ergebnis["frage"], ergebnis["hinweis"], idee, sichtbar_extra)
    return fb


def idee_moeglich(ergebnis):
    """Ideen-Feld nur, wenn es etwas zu lernen gibt: Gate bestanden, 3 Stufen
    geparst und keine Modell-Verweigerung (Detektor v2 aus ragas_auswertung.py)."""
    if not ergebnis.get("genuegend_relevanz") or not ergebnis.get("vollstaendig_geparst"):
        return False
    try:
        from ragas_auswertung import ist_modell_verweigerung
    except Exception as e:  # Feld lieber zeigen als die App abbrechen, aber sichtbar melden
        print(f"WARNUNG ideen_feedback: Verweigerungs-Detektor nicht geladen ({e})")
        return True
    return not ist_modell_verweigerung(ergebnis.get("loesung", ""))


def protokolliere_idee(sitzungs_id, frage_nr, ergebnis, versuch_nr, stufe, fb, pfad=None):
    """Eigene Datei statt neuer Spalten in interaktionen.csv (deren Format nutzen
    RAGAS und alle Auswertungsskripte). Verknüpfung: sitzungs_id + frage_nr
    (= n-te Frage der Sitzung) + frage."""
    pfad = pfad or IDEEN_LOG
    neu = not pfad.exists()
    with open(pfad, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=IDEEN_LOG_FELDER)
        if neu:
            w.writeheader()
        w.writerow({
            "zeitstempel": datetime.datetime.now().isoformat(timespec="seconds"),
            "sitzungs_id": sitzungs_id, "frage_nr": frage_nr, "frage": ergebnis["frage"],
            "versuch_nr": versuch_nr, "stufe_beim_versuch": stufe,
            "idee": fb["idee"], "urteil": fb["urteil"], "rueckmeldung": fb["rueckmeldung"],
            "ueberlegung": fb["ueberlegung"], "geparst": fb["geparst"],
            "leck_zahlen": "; ".join(fb["leck_zahlen"]), "sekunden": fb["sekunden"],
            "prompt_version": FEEDBACK_PROMPT_VERSION, "modell": MODEL_NAME,
            "kb_hash": ergebnis.get("kb_hash", ""),
        })
