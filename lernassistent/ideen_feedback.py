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

FEEDBACK_PROMPT_VERSION = "IF-v4"  # IF-v2 bleibt wählbar (Reproduktion); Änderungen siehe baue_feedback_prompt
MAX_VERSUCHE = 3
IDEEN_LOG = LOG_VERZEICHNIS / "ideen_feedback.csv"
URTEILE = ("richtig", "teilweise", "falsch", "keine_idee")
IDEEN_LOG_FELDER = [
    "zeitstempel", "sitzungs_id", "frage_nr", "frage", "versuch_nr", "stufe_beim_versuch",
    "idee", "urteil", "rueckmeldung", "ueberlegung", "geparst", "leck_zahlen",
    "sekunden", "prompt_version", "modell", "kb_hash",
    "neue_zahlen", "verweis_material",  # ab IF-v4 (nur Diagnose)
]

# Wird angezeigt, wenn das Modell das Format nicht einhält. Der Rohtext wird NIE
# angezeigt, weil er die (geheime) Überlegung mit der Lösung enthalten kann.
FALLBACK_RUECKMELDUNG = (
    "Danke für deine Idee! Ich konnte sie gerade nicht automatisch prüfen. "
    "Vergleiche sie mit der Lösung, wenn du sie öffnest."
)


def baue_feedback_prompt(frage, top_chunks, hinweis, loesung, idee, version=None):
    """Fester Prompt-Satz G2 (claude/Prompt_Set_Spezifikation.md §4.2). Die Lösung ist die Referenz;
    das Lernmaterial wird nicht mitgeschickt (top_chunks bleibt nur für die Schnittstelle).
    Regeln F1–F5: Petukhova et al. (2026); Kochmar et al. (2025); Maurya et al. (2025); Wood et al. (1976);
    Abrar et al. (2027); Knievel et al. (2025). ÜBERLEGUNG zuerst: Zhao, Knežević & Käser (2026).

    IF-v3 (14 Oct 2026), Anlass manuelle Tests (Fischer v7b):
      - Einleitung: Lernende haben kein Material. Die Rückmeldung hatte einer Person, die richtig
        sagte "ich habe keine Tabelle", widersprochen ("Deine Aussage ist nicht korrekt"), weil der
        Hinweis eine Tabelle erwähnte.
      - F6: "komme nicht weiter / sehe das nicht" = KEINE_IDEE, nicht widersprechen, kleiner Denkanstoß.
      - F7: nur Ursachen nennen, die in der Idee erkennbar sind (erfundene Diagnose bei "ungefähr 90 %"),
        und nicht der Lösung widersprechen (Zähler/Nenner vertauscht in einer Rückmeldung).
        F7 stammt aus eigenen Beobachtungen, nicht aus der Literatur.

    IF-v4 (14 Oct 2026), Anlass Test mit HP-v1: (a) die Rückmeldung stützte sich auf einen falschen
    Hinweis ("da der Hinweis … Zehntel andeutet") und übernahm eine falsche Einheit; (b) sie verriet den
    Wert als Bereich ("zwischen 0,02 und 0,03, näher an der unteren Grenze"; neue Zahlen, die der
    Zahlen-Check nicht erkennt, weil sie nicht in der Lösung stehen); (c) sie erklärte einen heute
    üblichen Wert (PV 18–25 %) mit "in der Praxis deutlich niedriger" für falsch, weil das Lehrbuch
    (2019) 10–13 % nennt. F8: nur die Lösung zählt, Aussagen als "laut Lernmaterial". F9: keine neuen
    Zahlen/Bereiche. F6 ohne "Grundwissen" (Quelle erfundener Fakten). Eigene Beobachtungen.
    Neue Protokollspalten: neue_zahlen (Zahlen in der Rückmeldung, die weder in Idee, Frage noch Hinweis
    stehen) und verweis_material."""
    version = version or FEEDBACK_PROMPT_VERSION
    if version not in ("IF-v2", "IF-v3", "IF-v4"):
        raise ValueError(f"Unbekannte Feedback-Prompt-Version {version} (verfügbar: IF-v2, IF-v3, IF-v4)")
    if version == "IF-v2":
        einleitung_extra, regeln_extra, nummern = "", "", "F2 bis F5"
    else:
        einleitung_extra = (" Sie hat kein Lernmaterial, keine Tabellen und keine Abbildungen. Verweist der"
                            "\nHinweis trotzdem darauf, gehe nicht darauf ein.")
        regeln_extra = """
F6 Sagt die Person, dass sie nicht weiterkommt oder etwas nicht sehen kann, ist das KEINE_IDEE: widersprich
   ihr nicht, sondern gib einen kleinen zusätzlichen Denkanstoß aus der Frage und dem Grundwissen.
F7 Nenne nur Fehlerursachen, die in der Idee erkennbar sind, und prüfe, dass deine Rückmeldung der Lösung
   nicht widerspricht."""
        nummern = "F2 bis F7"
        if version == "IF-v4":
            regeln_extra = """
F6 Sagt die Person, dass sie nicht weiterkommt oder etwas nicht sehen kann, ist das KEINE_IDEE: widersprich
   ihr nicht, sondern gib einen kleinen zusätzlichen Denkanstoß aus der Frage.
F7 Nenne nur Fehlerursachen, die in der Idee erkennbar sind, und prüfe, dass deine Rückmeldung der Lösung
   nicht widerspricht.
F8 Maßgeblich ist nur die Lösung. Der Hinweis ist kein Beleg und kann ungenau sein. Formuliere Sachaussagen
   als Aussage des Lernmaterials („laut Lernmaterial"), nicht als allgemeine Tatsache oder „in der Praxis".
F9 Nenne keine Zahlen, Bereiche oder Größenordnungen, die nicht in der Idee stehen, und sage nicht, ob ein
   Wert näher an einer Grenze liegt."""
            nummern = "F2 bis F9"
    return f"""Du gibst einer lernenden Person eine kurze Rückmeldung auf ihre eigene Idee zu einer Frage. Du kennst
die richtige Lösung; die lernende Person kennt sie nicht und hat bisher nur die Frage und den Hinweis
gesehen.{einleitung_extra}

Regeln:
F1 Beurteile die Idee anhand der Lösung: RICHTIG, TEILWEISE, FALSCH oder KEINE_IDEE (keine fachliche Idee
   erkennbar).
F2 Benenne, was an der Idee stimmt, und wo genau eine Abweichung liegt.
F3 Gib einen konkreten nächsten Denkschritt, ohne die Lösung zu verraten, auch nicht mit anderen Worten
   und ohne Zahlenwerte aus der Lösung.
F4 Ist die Idee RICHTIG, bestätige sie und sage, dass die Lösung jetzt angezeigt werden kann.
F5 Zwei bis drei kurze Sätze, freundlich und sachlich, sprich die Person mit „du" an.{regeln_extra}

### Frage
{frage}

### Hinweis (hat die lernende Person gesehen)
{hinweis}

### Lösung (geheim)
{loesung}

### Idee der lernenden Person
{idee}

Antworte genau in diesem Format:
ÜBERLEGUNG: <nur für dich: was stimmt, was fehlt, wie lenke ich, ohne zu verraten?>
URTEIL: RICHTIG oder TEILWEISE oder FALSCH oder KEINE_IDEE
RÜCKMELDUNG: <Rückmeldung nach {nummern}>"""


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


def neue_zahlen(rueckmeldung, *sichtbar):
    """Zahlen in der Rückmeldung, die nirgends im Sichtbaren (Frage, Hinweis, Idee) stehen, z. B. ein
    verratener Bereich "zwischen 0,02 und 0,03". Nur Protokoll."""
    bekannt = set().union(*(_zahlen(t) for t in sichtbar))
    return sorted(_zahlen(rueckmeldung) - bekannt)


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
    from rag_pipeline import verweist_auf_material
    fb["verweis_material"] = verweist_auf_material(fb["rueckmeldung"])  # nur Diagnose (stufen_check zählt aus dem Log)
    fb["neue_zahlen"] = neue_zahlen(fb["rueckmeldung"], ergebnis["frage"], ergebnis["hinweis"], idee, sichtbar_extra)
    return fb


def idee_moeglich(ergebnis):
    """Ideen-Feld nur, wenn es etwas zu lernen gibt: Gate bestanden, 3 Stufen
    geparst und keine Modell-Verweigerung (Detektor v2 aus ragas_auswertung.py)."""
    if not ergebnis.get("genuegend_relevanz") or not ergebnis.get("vollstaendig_geparst"):
        return False
    if ergebnis.get("status"):  # ab G-v1: STATUS statt Detektor
        return ergebnis["status"] in ("BEANTWORTET", "TEILWEISE")
    try:
        from ragas_auswertung import ist_modell_verweigerung
    except Exception as e:  # Feld lieber zeigen als die App abbrechen, aber sichtbar melden
        print(f"WARNUNG ideen_feedback: Verweigerungs-Detektor nicht geladen ({e})")
        return True
    return not ist_modell_verweigerung(ergebnis.get("loesung", ""))


def _ideen_spalten_sicherstellen(pfad):
    """Ab IF-v4 zwei neue Spalten; ein älteres Log wird einmalig umgeschrieben (Sicherungskopie vorher)."""
    if not pfad.exists():
        return
    with open(pfad, encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames == IDEEN_LOG_FELDER:
            return
        zeilen = list(r)
    import shutil
    shutil.copy2(pfad, pfad.with_name(f"{pfad.stem}_vor_spalten_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv"))
    with open(pfad, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=IDEEN_LOG_FELDER, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(zeilen)
    print(f"{pfad.name} auf neue Spalten umgestellt")


def protokolliere_idee(sitzungs_id, frage_nr, ergebnis, versuch_nr, stufe, fb, pfad=None):
    """Eigene Datei statt neuer Spalten in interaktionen.csv (deren Format nutzen
    RAGAS und alle Auswertungsskripte). Verknüpfung: sitzungs_id + frage_nr
    (= n-te Frage der Sitzung) + frage."""
    pfad = pfad or IDEEN_LOG
    _ideen_spalten_sicherstellen(pfad)
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
            "neue_zahlen": "; ".join(fb.get("neue_zahlen", [])),
            "verweis_material": "; ".join(fb.get("verweis_material", [])),
        })
