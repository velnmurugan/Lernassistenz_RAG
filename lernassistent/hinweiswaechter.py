"""
hinweiswaechter.py  –  Hinweis-Wächter HG-v1 (optional, in V20 aus)
-----------------------------------------------------------------
Zweck: Ein Hinweis soll die Lösung nicht verraten. Nach dem fertigen Hinweis prüft ein Prüfer (Prompt C2, Modell
qwen3.5:9b, T=0, Seed 42), ob ein zentraler Teil der Lösung ablesbar ist ("leck"). Bei "leck" wird der Hinweis höchstens
MAX_NEU-mal neu geschrieben (mit dem Befund des Prüfers im Prompt); bleibt es "leck", ersetzt ein neutraler Ersatzhinweis.
"teilweise" und "kein_leck" bleiben unverändert.

Schalter (Standard aus):
    export LERNASSISTENT_HG=HG-v1
    export LERNASSISTENT_HG_MODELL=qwen3.5:9b      # optional, Standard = Generatormodell

Eigenschaften:
  1. beantworte_frage ruft den Wächter nach hinweis_pruefen auf.
  2. Folgehinweise (Versuch 2/3): der Neuschreib-Prompt verlangt, ein Wort oder eine Zahl der letzten Antwort aufzugreifen.
  3. Folgehinweise: der Ersatztext greift die letzte Antwort auf.
  4. Der Hinweis vor dem Wächter wird mitgespeichert (hinweis_vor_waechter), damit "ohne" und "mit" Wächter gepaart
     verglichen werden können.
Grenzen: Die Übereinstimmung des Prüfers mit Referenzurteilen ist gering (kappa ca. 0,3). Ob Hinweise dadurch besser werden,
entscheidet nur die menschliche Bewertung.
"""
import os
import re

VERSION = "HG-v1"
MAX_NEU = 2
PRUEFER_OPTIONEN = {"temperature": 0, "seed": 42, "num_predict": 160}
ERSATZ_ERSTER = ("Überlege zuerst, welche Größe oder welcher Begriff in der Frage gesucht ist und wovon er abhängen "
                 "könnte. Was weißt du darüber schon?")
ERSATZ_FOLGE = ("Schau dir deine letzte Antwort noch einmal an: Welche Angabe aus der Frage hast du darin noch nicht "
                "berücksichtigt, und was weißt du darüber?")


def aktiv():
    return os.environ.get("LERNASSISTENT_HG", "aus").strip().lower() not in ("", "aus", "0", "nein")


def pruefer_modell(rp):
    return os.environ.get("LERNASSISTENT_HG_MODELL") or rp.MODEL_NAME


def pruefer_prompt(frage, loesung, verlauf, hinweis, nr):
    """Prompt C2 (direkte Frage nach dem Leck), identisch zu optimiere_hinweise.pruefer_prompt('C2')."""
    verlauf = verlauf or "(noch kein Versuch)"
    return f"""Du prüfst streng, ob ein Hinweis für Lernende die Lösung verrät.

### Frage
{frage}

### Richtige Lösung (Referenz; die lernende Person kennt sie nicht)
{loesung}

### Bisheriger Verlauf (Hinweise, Antworten der Person, Rückmeldungen)
{verlauf}

### Zu prüfender Hinweis (Hinweis Nr. {nr})
{hinweis}

Frage dich: Kann eine Person, die nur die Frage, den Verlauf und diesen Hinweis kennt, daraus schon einen zentralen Teil der
Lösung ablesen oder durch bloßes Zustimmen übernehmen (genannter Begriff, genannte Bedingung, Richtung des Ergebnisses,
richtige Option einer Entweder-oder-Frage, Formelaufbau, Name der gesuchten Sache)? Dann ist es ein Leck.
leck = ja, ein zentraler Teil ist ablesbar; teilweise = nur ein Randbegriff oder ein kleiner Teil; kein_leck = der Hinweis
lenkt nur auf eine Größe oder einen Zusammenhang, ohne etwas von der Lösung zu nennen. Wiederholungen aus der Frage zählen nicht.

Antworte genau in diesem Format:
GENANNT: <was ablesbar ist, in höchstens 15 Wörtern, oder keine>
URTEIL: <leck oder teilweise oder kein_leck>"""


def parse_pruefer(roh):
    u = re.findall(r"(?i)URTEIL\W*[:=]\W*(kein[_ ]leck|teilweise|leck)", roh or "")
    g = re.findall(r"(?im)^\W*GENANNT\W*[:=]\s*(.+)$", roh or "")
    return {"urteil": (u[-1].lower().replace(" ", "_") if u else ""), "genannt": (g[-1].strip() if g else "")[:300]}


def pruefe(rp, frage, loesung, verlauf, hinweis, nr):
    try:
        roh = rp.frage_llm(pruefer_prompt(frage, loesung, verlauf, hinweis, nr), model=pruefer_modell(rp),
                           options=dict(PRUEFER_OPTIONEN))
    except Exception as e:  # Der Wächter darf die Antwort nie verhindern
        print(f"WARNUNG Hinweis-Wächter: {e}")
        return {"urteil": "", "genannt": ""}
    return parse_pruefer(roh)


def neu_zusatz(hinweis, genannt, folge):
    z = (f"\n\nACHTUNG: Dein letzter Entwurf war:\n\"{hinweis}\"\nEr verrät laut Prüfung: "
         f"{genannt or 'einen Baustein der Lösung'}. Schreibe einen neuen Hinweis als engere Frage, die das weder nennt noch "
         f"umschreibt noch als Auswahl anbietet.")
    if folge:
        z += " Greife ein Wort oder eine Zahl aus der letzten Antwort der Person auf."
    return z


def waechter(rp, frage, loesung, hinweis, verlauf, nr, neu_erzeugen):
    """Kern. neu_erzeugen(zusatz_text) -> neuer Hinweis (bereits durch hinweis_pruefen gelaufen) oder "".
    Rückgabe: dict(hinweis, urteil_start, urteil_ende, neu, ersatz, genannt)."""
    folge = nr > 1
    urt = pruefe(rp, frage, loesung, verlauf, hinweis, nr)
    start = urt["urteil"]
    neu = 0
    while urt["urteil"] == "leck" and neu < MAX_NEU:
        neu += 1
        h2 = neu_erzeugen(neu_zusatz(hinweis, urt["genannt"], folge))
        if not h2:
            break
        hinweis = h2
        urt = pruefe(rp, frage, loesung, verlauf, hinweis, nr)
    ersatz = urt["urteil"] == "leck"
    if ersatz:
        hinweis = ERSATZ_FOLGE if folge else ERSATZ_ERSTER
    return {"hinweis": hinweis, "urteil_start": start, "urteil_ende": urt["urteil"], "neu": neu, "ersatz": ersatz,
            "genannt": urt["genannt"]}


def anwenden(rp, frage, top_chunks, stufen):
    """Hook für beantworte_frage (erster Hinweis): ändert stufen in place. rp = Modul rag_pipeline."""
    hinweis = (stufen.get("hinweis") or "").strip()
    if not hinweis or not stufen.get("vollstaendig_geparst") or stufen.get("status") not in ("BEANTWORTET", "TEILWEISE"):
        return stufen
    from ragas_auswertung import ist_modell_verweigerung
    loesung = stufen.get("loesung", "")
    if ist_modell_verweigerung(loesung):
        return stufen

    def neu_erzeugen(zusatz):
        roh = rp.frage_llm(rp.baue_hinweis_prompt(frage, top_chunks, loesung) + zusatz, options=rp.GENERIERUNGS_OPTIONEN)
        h, _ = rp.parse_hinweis(roh)
        if not h:
            return ""
        st = {"hinweis": h, "loesung": loesung, "status": stufen.get("status", "")}
        rp.hinweis_pruefen(frage, st)
        return st["hinweis"]

    r = waechter(rp, frage, loesung, hinweis, "", 1, neu_erzeugen)
    stufen["hinweis_vor_waechter"] = hinweis
    stufen["hinweis"] = r["hinweis"]
    stufen["hinweis_waechter"] = (f"{VERSION} {r['urteil_start'] or '?'}->{r['urteil_ende'] or '?'} "
                                  f"neu={r['neu']} ersatz={'ja' if r['ersatz'] else 'nein'}")
    return stufen
