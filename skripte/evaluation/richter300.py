"""
richter300.py  (Studie 1, Schritt 3: lokaler LLM-Richter ja / teilweise / nein, Prompt R300-J1)
Richter = anderes Modell als der Generator (Standard gemma4:12b), T = 0, Seed 42. Der Prompt enthält die Bewertungskriterien
wörtlich aus dem Bewertungsbogen (daten/testfragen/kriterien300.json) und 10 von Hand bewertete Beispiele, die nicht zu den
300 Testfragen gehören (daten/testfragen/richter_beispiele.json). Ausgabe: BEGRÜNDUNG, dann URTEIL.
Bewertet werden beide Antworten jeder Frage (ohne RAG, mit RAG), jede einzeln und ohne Hinweis auf die Bedingung.
Fortsetzbar.
  python skripte/evaluation/richter300.py F300-V20 --richter gemma4:12b [--limit 4]
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import argparse
import csv
import json
import re
import time
from pathlib import Path

import rag_pipeline as rp

PROMPT_VERSION = "R300-J1"
OPTIONEN = {"temperature": 0, "seed": 42}
MAX_ANTWORT = 3500
FELDER = ["id", "buch", "typ", "seite", "urteil", "begruendung", "roh", "sek", "richter", "prompt_version"]


def kriterien_text(k):
    teile = ["Buchfragen:",
             f"- ja: {k['Buchfragen: ja']}",
             f"- teilweise: {k['Buchfragen: teilweise']}",
             f"- nein: {k['Buchfragen: nein']}",
             f"- Grenzfälle: {k['Grenzfälle']}",
             "Fragen außerhalb der Lehrbücher (Referenz beginnt mit „Außerhalb der beiden Lehrbücher“):",
             f"- ja: {k['Außerhalb: ja']}",
             f"- nein: {k['Außerhalb: nein']}"]
    return "\n".join(teile)


def fall(frage, referenz, antwort, buchstelle=""):
    t = f"Frage: {frage}\nReferenz: {referenz}\n"
    if buchstelle:
        t += f"Buchstelle: {buchstelle[:1500]}\n"
    a = (antwort or "").strip()
    if len(a) > MAX_ANTWORT:
        a = a[:MAX_ANTWORT] + " […]"
    return t + f"Antwort:\n{a}\n"


def baue_prompt(k, beispiele, frage, referenz, antwort, buchstelle):
    bsp = "\n".join(
        f"### Beispiel {i}\n{fall(b['frage'], b['referenz'], b['antwort'])}"
        f"BEGRÜNDUNG: {b['begruendung']}\nURTEIL: {b['urteil']}\n"
        for i, b in enumerate(beispiele, 1))
    return f"""Du bewertest Antworten auf Fachfragen aus der technischen Ausbildung (Elektrotechnik, Maschinenbau).
Vergleiche die Antwort mit der Referenz (maßgeblich) und, falls vorhanden, mit der Buchstelle. Bewerte streng nach
diesen Kriterien:

{kriterien_text(k)}

Wichtig: Eine einzige falsche Aussage, ein falscher Wert oder eine falsche Einheit ergibt „nein“, auch wenn der Rest stimmt.
„teilweise“ nur, wenn alles Gesagte richtig ist, aber eine Kernaussage fehlt. Zusätzliche richtige Informationen sind erlaubt.
Bei Rechnungen: Rundungsabweichungen bis etwa 2 % sind zulässig. Automatische Warnhinweise gehören zur Antwort.

{bsp}
### Zu bewerten
{fall(frage, referenz, antwort, buchstelle)}
Antworte genau in diesem Format:
BEGRÜNDUNG: <ein bis zwei Sätze>
URTEIL: ja, teilweise oder nein"""


def parse(roh, ausserhalb):
    u = re.findall(r"URTEIL:\s*\**\s*(ja|teilweise|nein)\b", roh, re.IGNORECASE)
    b = re.search(r"BEGRÜNDUNG:\s*(.+?)(?:\n\s*URTEIL:|$)", roh, re.S)
    urteil = u[-1].lower() if u else ""
    if ausserhalb and urteil == "teilweise":
        urteil = "nein"  # für Außerhalb-Fragen gibt es kein „teilweise“: Sachantwort gegeben = nein
    return urteil, (b.group(1).strip() if b else "")


def lies(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--richter", default="gemma4:12b")
    ap.add_argument("--fragen", default="daten/testfragen/fragen300.csv")
    ap.add_argument("--kriterien", default="daten/testfragen/kriterien300.json")
    ap.add_argument("--beispiele", default="daten/testfragen/richter_beispiele.json")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    k = json.load(open(a.kriterien, encoding="utf-8"))
    bsp = json.load(open(a.beispiele, encoding="utf-8"))
    fragen = {q["id"]: q for q in lies(a.fragen)}
    ant = lies(Path("evaluationsdaten") / f"antworten300_{a.label}.csv")[: a.limit]
    out = Path("evaluationsdaten") / f"richter300_{a.label}.csv"
    fertig = {(z["id"], z["seite"]): z for z in lies(out)} if out.exists() else {}
    zeilen = list(fertig.values())
    for z in ant:
        q = fragen[z["id"]]
        aussen = q["buch"] == "Außerhalb"
        for seite in ("ohne", "mit"):
            if (z["id"], seite) in fertig and fertig[(z["id"], seite)]["urteil"]:
                continue
            antwort = z.get(f"antwort_{seite}", "")
            if not antwort or antwort.startswith("FEHLER"):
                continue
            prompt = baue_prompt(k, bsp, q["frage"], q["referenz"], antwort, q.get("referenz_passage", ""))
            t0 = time.time()
            try:
                roh = rp.frage_llm(prompt, model=a.richter, options=OPTIONEN)
            except Exception as e:
                roh = f"FEHLER {type(e).__name__}"
            urteil, begr = parse(roh, aussen)
            neu = {"id": z["id"], "buch": q["buch"], "typ": q["typ"], "seite": seite, "urteil": urteil, "begruendung": begr,
                   "roh": roh[:1500], "sek": round(time.time() - t0, 1), "richter": a.richter, "prompt_version": PROMPT_VERSION}
            zeilen = [x for x in zeilen if (x["id"], x["seite"]) != (z["id"], seite)] + [neu]
            print(f"[{z['id']:>4}] {seite:<4} {urteil or '??':<9} {neu['sek']:>5} s  {begr[:90]}", flush=True)
            with open(out, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FELDER)
                w.writeheader()
                w.writerows(zeilen)
    leer = [x["id"] + "/" + x["seite"] for x in zeilen if not x["urteil"]]
    print(f"Fertig: {out}  ({len(zeilen)} Urteile, unlesbar: {len(leer)} {leer[:10]})")


if __name__ == "__main__":
    main()
