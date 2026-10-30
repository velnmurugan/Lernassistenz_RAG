#!/usr/bin/env python3
"""
teste_hinweis_dialog.py  –  Hinweis-Dialogtest auf N100 (simulierte Lernende, Rubrik-Bewertung)
------------------------------------------------------------------------------------------------
Ziel: Die Hinweis- und Rückmelde-Funktionen des Systems in einem mehrstufigen Dialog prüfen, ohne
Probanden. Ablauf je N100-Frage (V11B-Konfiguration eingefroren, nichts am System geändert):

  Phase 1  System (qwen3.5:9b): Antwort mit Hinweis (H-v3 + HP-v4) wie in der App.
  Phase 2  Dialog, bis zu 3 Versuche (MAX_VERSUCHE):
             a) Lernenden-Simulator (anderes Modell): schreibt eine Antwort auf den aktuellen Hinweis.
                Soll-Typ je Versuch gesetzt: ca. 30 % richtig, 70 % nicht richtig
                (davon 40 % teilweise, 40 % falsch mit typischem Denkfehler, 20 % keine Idee).
             b) System: Rückmeldung (IF-v5 + FP-v3) mit Urteil.
             c) Bei Urteil != richtig und Versuch < 3: System schreibt den nächsten Hinweis
                (neuer Prompt HD-v1: Regeln H1-H5 aus H-v3 + Bezug auf die letzte Antwort + eine Stufe
                konkreter; gleiche Leck-Prüfung HP-v4). Bei "richtig" endet der Dialog.
  Phase 3  Rubrik-Bewertung (Richter mistral-nemo, nie ein Generator): jeder gezeigte Hinweis
             (P1-P6) und jede Rückmeldung (R1-R4) mit ja / teilweise / nein; dazu eine Prüfung, ob die
             simulierte Antwort zum Soll-Typ passt (S1). Automatisch zusätzlich: Urteil-Treffer,
             Zahlen-Leck, Wortanteil der Lösung im Hinweis.
  Phase 4  Ausgabe: Dialog-CSV, Bewertungsbogen für zwei Menschen (verblindet, 40 Objekte, ohne
             Richterwerte), Zusammenfassung.

Modelle (drei Familien, damit kein Modell sein eigenes Erzeugnis bewertet):
  Generator/System  qwen3.5:9b   (wie V11B)
  Lernenden-Simulator granite4.1:8b (--lerner)
  Richter           mistral-nemo   (--richter)

Wichtige Grenzen (stehen auch in der Zusammenfassung): Simulierte Lernende sind kein Ersatz für echte;
der Test prüft die Mechanik (Urteil, Leck, Eskalation) und liefert Rubrikwerte für die Kalibrierung des
Richters gegen die Menschen. Die Referenz für den Simulator ist die Lösung des Systems (bei falscher
Systemlösung folgt der "richtige" Lernende dieser). Der Richter ist ohne Abgleich mit den Menschen
(Bewertungsbogen) kein Beleg.

Start (aus ~/RAG, Umgebung pilot_rag aktiv, Ollama läuft, Vordergrund):
  Pilot (5 Fragen, ca. 15-20 min):
    python skripte/evaluation/teste_hinweis_dialog.py --limit 5
  Voller Lauf (100 Fragen, ca. 4 h; bricht man ab, setzt derselbe Befehl fort):
    python skripte/evaluation/teste_hinweis_dialog.py
Ergebnisse: evaluationsdaten/hinweis_dialog_<LABEL>_*.csv / .txt / _zustand.json
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import os

# V11B festnageln, bevor das System importiert wird
for _k in ("LERNASSISTENT_CTX", "LERNASSISTENT_RW", "LERNASSISTENT_V18", "LERNASSISTENT_V19", "LERNASSISTENT_MODELL",
           "LERNASSISTENT_THINK", "LERNASSISTENT_TIMEOUT", "LERNASSISTENT_RB"):
    os.environ.pop(_k, None)
os.environ.update(LERNASSISTENT_G="G-v4", LERNASSISTENT_RP="RP-v5", LERNASSISTENT_FS="aus",
                  HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONUNBUFFERED="1")

import argparse  # noqa: E402
import csv  # noqa: E402
import datetime  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402
from pathlib import Path  # noqa: E402

import requests  # noqa: E402

import rag_pipeline  # noqa: E402
from rag_pipeline import (lade_wissensbasis, berechne_kb_hash, beantworte_frage, frage_llm, parse_hinweis,  # noqa: E402
                          hinweis_pruefen, hinweis_verraet_zahl, GENERIERUNGS_OPTIONEN, OLLAMA_URL, _kontext_text)
from ideen_feedback import gib_feedback, idee_moeglich, MAX_VERSUCHE, FEEDBACK_PROMPT_VERSION  # noqa: E402

KB = "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json"
FRAGEN = (("fischer", "daten/testfragen/testfragen_fischer_v2_chunks_beide_v7r.csv"),
          ("boege", "daten/testfragen/testfragen_boege_v2_v7r.csv"))
RETRIEVAL = "hybrid_kg_rr"
FOLGEHINWEIS_VERSION = "HD-v1"
TYPEN = ("richtig", "teilweise", "falsch", "keine_idee")
KEINE_IDEE_SAETZE = ("Ich weiß nicht weiter.", "Dazu fällt mir gerade nichts ein.",
                     "Keine Ahnung, ich sehe nicht, wie ich anfangen soll.", "Ich komme da nicht drauf.",
                     "Damit kann ich gerade nichts anfangen.")

# ----------------------------------------------------------------------------------------------- Rubrik
HINWEIS_ITEMS = {
    "P1": "Zurückhalten: Der Hinweis verrät weder Ergebnis, Zahlenwert, Kernaussage noch die gesuchte Benennung oder "
          "Aufzählung, auch nicht umschrieben. ja = nichts davon verraten.",
    "P2": "Richtung: Der Hinweis nennt den Begriff, die Größe oder den nächsten Denkschritt, der zur Lösung führt. "
          "ja = klare, richtige Richtung.",
    "P3": "Eigenes Denken: Der Hinweis regt zum Herleiten oder Nachdenken an (Zusammenhang, Frage) und liefert nicht "
          "nur ein Stichwort.",
    "P4": "Anpassung: Versuch 1: Umfang und Schwierigkeit angemessen, nicht überfordernd. Ab Versuch 2: greift die "
          "bisherige Antwort auf, lenkt auf die Stelle, ist konkreter als die früheren Hinweise und wiederholt sie nicht.",
    "P5": "Fachlich stimmig: Keine Aussage widerspricht der Lösung, keine erfundenen Fakten oder Zahlen.",
    "P6": "Zugänglich: Kein Verweis auf Material, Text oder Tabelle, die die Person nicht hat; höchstens drei kurze "
          "Sätze; Anrede mit „du“; verständlich.",
}
FEEDBACK_ITEMS = {
    "R1": "Beurteilung: Die Rückmeldung benennt, was an der Antwort stimmt und wo die Abweichung liegt (bei richtiger "
          "Antwort: bestätigt sie; bei „keine Idee“: widerspricht nicht).",
    "R2": "Nächster Schritt: Sie gibt einen nächsten Denkschritt oder fragt nach der Stelle, ohne den fehlenden Teil "
          "oder die Lösung zu nennen (bei richtiger Antwort: nennt, dass die Lösung angezeigt werden kann).",
    "R3": "Fachlich stimmig: Sie widerspricht der Lösung nicht und enthält keine erfundenen Zahlen, Fakten oder Ursachen.",
    "R4": "Form: Zwei bis drei kurze Sätze, freundlich und sachlich, Anrede mit „du“, kein Verweis auf fehlendes Material.",
}
SIM_ITEMS = {"S1": "Die simulierte Antwort passt zum vorgesehenen Typ (richtig = inhaltlich vollständig und richtig; "
                   "teilweise = richtiger Teil, zentrales Element fehlt; falsch = inhaltlich falsch; "
                   "keine_idee = keine fachliche Idee)."}
STOP = set("dieser diese dieses einer eines einem einen wird werden sowie auch nicht dass oder aber kann können "
           "durch über unter wenn dann sind ist".split())


# ------------------------------------------------------------------------------------------------ Hilfen
def stunde(t0, text):
    print(f"[{datetime.datetime.now():%H:%M}] {text} (seit Start {(time.time() - t0) / 60:.0f} min)", flush=True)


def llm(modell, prompt, optionen, timeout=600):
    """Ollama-Aufruf für Simulator und Richter (zweiter Versuch bei Verbindungs-/Zeitfehlern)."""
    nutzlast = {"model": modell, "prompt": prompt, "stream": False, "think": False, "options": optionen}
    letzter = None
    for versuch in range(2):
        try:
            r = requests.post(OLLAMA_URL, json=nutzlast, timeout=timeout)
            if r.status_code == 400 and "think" in r.text.lower():
                nutzlast.pop("think", None)
                r = requests.post(OLLAMA_URL, json=nutzlast, timeout=timeout)
            r.raise_for_status()
            return r.json()["response"].strip()
        except (requests.RequestException, KeyError, ValueError) as e:
            letzter = e
            time.sleep(5)
    raise RuntimeError(f"Ollama-Aufruf ({modell}) fehlgeschlagen: {letzter}")


def pruefe_modelle(*namen):
    try:
        r = requests.get(OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=20)
        vorhanden = [m["name"] for m in r.json().get("models", [])]
    except Exception as e:
        raise SystemExit(f"ABBRUCH: Ollama nicht erreichbar ({e}).")
    fehlt = [n for n in namen if not any(v == n or v.split(":")[0] == n or v.startswith(n + ":") for v in vorhanden)]
    if fehlt:
        raise SystemExit(f"ABBRUCH: Modell(e) fehlen in Ollama: {', '.join(fehlt)}\nVorhanden: {', '.join(vorhanden)}\n"
                         f"Mit --lerner / --richter andere installierte Modelle wählen (nicht qwen).")


def speichere(zustand, pfad):
    tmp = Path(str(pfad) + ".tmp")
    tmp.write_text(json.dumps(zustand, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(pfad)


def verlauf_text(s, bis):
    """Bisheriger Dialog (alle Versuche vor 'bis') als Text."""
    teile = []
    for t in s["turns"][:bis]:
        teile.append(f"Versuch {t['n']} – Hinweis: {t['hinweis']}\nAntwort der Person: {t['antwort']}\n"
                     f"Rückmeldung: {t.get('rueckmeldung', '')}")
    return "\n".join(teile)


def inhaltswoerter(text, ausser=""):
    aus = set(re.findall(r"[a-zäöüß]{6,}", (ausser or "").lower()))
    return {w for w in re.findall(r"[a-zäöüß]{6,}", (text or "").lower()) if w not in STOP and w not in aus}


def loesungswort_anteil(hinweis, loesung, frage):
    ref = inhaltswoerter(loesung, frage)
    return round(len(ref & inhaltswoerter(hinweis)) / len(ref), 2) if ref else 0.0


# ------------------------------------------------------------------------------------- Simulator
def typ_plan(ids, runde, p_richtig, seed):
    """Genau round(p*n) richtig, Rest 40 % teilweise / 40 % falsch / 20 % keine_idee; gemischt, reproduzierbar."""
    ids = sorted(ids)
    n = len(ids)
    n_r = round(p_richtig * n)
    rest = n - n_r
    n_t, n_k = round(0.4 * rest), round(0.2 * rest)
    typen = ["richtig"] * n_r + ["teilweise"] * n_t + ["keine_idee"] * n_k
    typen += ["falsch"] * (n - len(typen))
    random.Random(seed * 100 + runde).shuffle(typen)
    return dict(zip(ids, typen))


ANWEISUNG = {
    "richtig": "Deine Antwort ist inhaltlich richtig und vollständig (bei einer Rechnung mit Rechenweg und Ergebnis). "
               "Formuliere in eigenen Worten und schreibe die Referenzlösung nicht Wort für Wort ab.",
    "teilweise": "Deine Antwort ist nur teilweise richtig: Das, was du schreibst, stimmt, aber ein zentrales Element "
                 "fehlt (zum Beispiel der letzte Rechenschritt, eine von mehreren Angaben oder der Grund). "
                 "Du merkst nicht, dass etwas fehlt.",
    "falsch": "Deine Antwort ist inhaltlich falsch, und zwar so, wie Lernende in diesem Stoff typischerweise falsch "
              "liegen (zwei verwandte Begriffe oder Größen verwechselt, falsche Formel, Werte vertauscht). Du klingst "
              "überzeugt. Die richtige Lösung darf nicht in deiner Antwort stehen.",
}


def lerner_antwort(args, s, typ, hinweis, runde):
    if typ == "keine_idee":
        return KEINE_IDEE_SAETZE[(sum(map(ord, s["id"])) + runde) % len(KEINE_IDEE_SAETZE)]
    verlauf = verlauf_text(s, runde - 1)
    extra = ""
    if runde > 1:
        extra = ("\nDu hast schon einen Versuch gemacht. Gehe auf den neuen Hinweis ein, aber setze ihn nur so um, "
                 "wie es zum vorgesehenen Typ passt.")
    prompt = f"""Du spielst eine Auszubildende oder einen Auszubildenden in einem technischen Beruf, die/der eine Lernfrage bearbeitet.
Du schreibst NUR deine eigene Antwort: ein bis drei Sätze, einfache Sprache, keine Anrede, keine Erklärung, dass du etwas absichtlich tust.

### Frage
{s['frage']}

### Referenzlösung (nur damit du deine Rolle richtig spielen kannst; die Person kennt sie nicht)
{s['loesung']}
{('### Bisheriger Verlauf' + chr(10) + verlauf) if verlauf else ''}

### Aktueller Hinweis, den du gesehen hast
{hinweis}

### Vorgesehene Art deiner Antwort
{ANWEISUNG[typ]}{extra}

Antworte nur mit dem Text deiner Antwort."""
    roh = llm(args.lerner, prompt, {"temperature": 0.3, "seed": 42 + runde, "num_predict": 250})
    roh = re.sub(r"(?is)^\s*(antwort|meine antwort)\s*:\s*", "", roh).strip().strip('"„“').strip()
    return roh[:700] or KEINE_IDEE_SAETZE[0]


# --------------------------------------------------------------------------------- Folgehinweis
def baue_folgehinweis_prompt(s, t, stufe):
    """HD-v1: H1-H5 wie H-v3; zusätzlich Bezug auf die letzte Antwort (H6) und eine Stufe konkreter (H7)."""
    return f"""Du schreibst den NÄCHSTEN Hinweis (Denkanstoß) für Auszubildende in technischen Berufen.
Die/der Auszubildende hat die Frage schon einmal versucht, die Antwort war nicht richtig. Du kennst die Frage,
die Lernmaterialien, die richtige Lösung und den bisherigen Verlauf. Die/der Auszubildende sieht NUR die Frage und
den Verlauf, nicht die Lernmaterialien und nicht die Lösung.

Regeln für den Hinweis:
H1 Verrate die Lösung nicht: kein Ergebnis, kein Zahlenwert aus der Lösung, keine Formel
   mit eingesetzten Werten, nicht die gesuchte Kernaussage, Aufzählung oder Benennung.
H2 Zeige die Richtung: nenne den Begriff, die Größe oder den nächsten Denkschritt, der zur Lösung führt.
H3 Nutze nur, was die/der Auszubildende kennt: die Frage, den Verlauf und Grundwissen. Schreibe nie
   „im Kontext", „im Text", „in der Tabelle", „in der Quelle" oder „in den Materialien".
H4 Fördere Verständnis: lenke auf den Zusammenhang (wie hängt was zusammen, warum), aber überfordere nicht.
H5 Klar und kurz: 1-2 Sätze, sprich die/den Auszubildende:n mit „du" an, du darfst mit einer Frage enden.
H6 Knüpfe an die letzte Antwort an: lenke auf die Stelle, an der sie vom Richtigen abweicht oder etwas fehlt,
   aber nenne den fehlenden oder falschen Teil nicht selbst. Wiederhole die Rückmeldung nicht.
H7 Dies ist Hinweisstufe {stufe}: sei etwas konkreter als die bisherigen Hinweise und wiederhole sie nicht,
   ohne gegen H1 zu verstoßen.

Lernmaterialien:
{s['kontext']}

Frage: {s['frage']}

Lösung (GEHEIM, nicht verraten):
{s['loesung']}

Bisheriger Verlauf:
{verlauf_text(s, t['n'])}

Antworte GENAU in diesem Format:
UEBERLEGUNG: <nur für dich: (a) Welche Wörter und Zahlen aus der Lösung dürfen NICHT im Hinweis stehen? (b) Welche Stelle der letzten Antwort ist der Ansatzpunkt?>
HINWEIS: <der Hinweis>"""


def folgehinweis(s, t, stufe):
    roh = frage_llm(baue_folgehinweis_prompt(s, t, stufe), options=GENERIERUNGS_OPTIONEN)
    h, ueb = parse_hinweis(roh)
    if not h:
        return "", "format_fehler", ueb
    stufen = {"hinweis": h, "loesung": s["loesung"], "status": s["status"]}
    hinweis_pruefen(s["frage"], stufen)
    return stufen["hinweis"], stufen.get("hinweis_pruefung", ""), ueb


# ------------------------------------------------------------------------------------- Richter
def judge_prompt(art, s, t, text):
    if art == "hinweis":
        items, titel, was = HINWEIS_ITEMS, "Hinweis", "den Hinweis"
        sichtbar = f"Versuch {t['n']} von {MAX_VERSUCHE}."
        if t["n"] > 1:
            sichtbar += "\nBisheriger Verlauf:\n" + verlauf_text(s, t["n"] - 1)
    elif art == "rueckmeldung":
        items, titel, was = FEEDBACK_ITEMS, "Rückmeldung", "die Rückmeldung"
        sichtbar = (f"Versuch {t['n']} von {MAX_VERSUCHE}.\nHinweis, den die Person gesehen hat: {t['hinweis']}\n"
                    f"Antwort der Person: {t['antwort']}\nUrteil des Systems: {t.get('urteil', '')}")
    else:
        items, titel, was = SIM_ITEMS, "simulierte Antwort", "die simulierte Antwort"
        sichtbar = f"Vorgesehener Typ: {t['typ_soll']}"
    kriterien = "\n".join(f"{k} {v}" for k, v in items.items())
    zeilen = "\n".join(f"{k}: <ja oder teilweise oder nein> | <Begründung in höchstens 12 Wörtern>" for k in items)
    return f"""Du bewertest {was} in einem Lerndialog für Auszubildende in technischen Berufen streng nach den Kriterien.
Bewerte nur, was dasteht. ja = Kriterium voll erfüllt, teilweise = in Teilen oder mit Mängeln, nein = nicht erfüllt.

### Frage
{s['frage']}

### Richtige Lösung (Referenz; die lernende Person kennt sie nicht)
{s['loesung']}

### Kontext
{sichtbar}

### Zu bewertende {titel}
{text}

### Kriterien
{kriterien}

Antworte genau in diesem Format, eine Zeile je Kriterium, sonst nichts:
{zeilen}"""


def parse_judge(roh, items):
    erg = {}
    for k in items:
        m = re.search(rf"(?im)^\W*{k}\W*[:=]\s*(ja|teilweise|nein)\b\s*\|?\s*(.*)$", roh)
        erg[k] = m.group(1).lower() if m else ""
        erg[k + "_grund"] = m.group(2).strip() if m else ""
    return erg


# ----------------------------------------------------------------------------------------- Phasen
def lade_fragen():
    fragen = []
    for buch, pfad in FRAGEN:
        if not Path(pfad).exists():
            raise SystemExit(f"FEHLT: {pfad} (aus ~/RAG starten)")
        with open(pfad, encoding="utf-8-sig", newline="") as f:
            for i, z in enumerate(csv.DictReader(f), 1):
                if (z.get("typ") or "").strip().lower() == "ausserhalb":
                    continue
                nr = str(z.get("nr") or i)
                fragen.append({"id": f"{buch[0].upper()}{nr}", "buch": buch, "nr": nr, "frage": z["frage"].strip(),
                               "typ": z.get("typ", ""), "kernaussage": z.get("erwartete_kernaussage", "")})
    return fragen


def phase1(args, zustand, fragen, chunks, pfad, t0):
    stunde(t0, f"Phase 1/4: System antwortet ({len(fragen)} Fragen, qwen3.5:9b)")
    for i, q in enumerate(fragen, 1):
        if q["id"] in zustand["q"]:
            continue
        z0 = time.time()
        erg = beantworte_frage(q["frage"], chunks, top_k=4, methode=RETRIEVAL)
        ok = bool(idee_moeglich(erg))
        zustand["q"][q["id"]] = {
            **q, "ok": ok, "status": erg.get("status", ""), "hinweis0": erg.get("hinweis", ""),
            "hinweis0_pruefung": erg.get("hinweis_pruefung", ""), "hinweis0_quelle": erg.get("hinweis_quelle", ""),
            "loesung": erg.get("loesung", ""), "kontext": _kontext_text(erg["top_chunks"]) if ok else "",
            "quellen": [c["id"] for c in erg.get("top_chunks", [])], "turns": [], "ende": "",
            "sek_antwort": round(time.time() - z0, 1)}
        speichere(zustand, pfad)
        print(f"  [{i}/{len(fragen)}] {q['id']:<5} {'Dialog möglich' if ok else 'kein Dialog (' + (erg.get('status') or 'Gate') + ')'}"
              f"  {time.time() - z0:.0f}s", flush=True)


def phase2_runde(args, zustand, runde, pfad, t0):
    qs = [s for s in zustand["q"].values() if s["ok"]]
    aktiv = [s for s in qs if not s["ende"] and len(s["turns"]) == runde - 1]
    if aktiv:
        stunde(t0, f"Phase 2/4, Versuch {runde}: Simulator antwortet ({len(aktiv)} Dialoge, {args.lerner})")
        plan = typ_plan([s["id"] for s in aktiv], runde, args.p_richtig, args.seed)
        for s in aktiv:
            hinweis = s["hinweis0"] if runde == 1 else s["turns"][-1]["folgehinweis"]
            hp = s["hinweis0_pruefung"] if runde == 1 else s["turns"][-1].get("folgehinweis_pruefung", "")
            typ = plan[s["id"]]
            s["turns"].append({"n": runde, "hinweis": hinweis, "hinweis_pruefung": hp, "typ_soll": typ,
                               "antwort": lerner_antwort(args, s, typ, hinweis, runde)})
            speichere(zustand, pfad)
    offen = [s for s in qs if not s["ende"] and s["turns"] and s["turns"][-1]["n"] == runde and "urteil" not in s["turns"][-1]]
    if offen:
        stunde(t0, f"Phase 2/4, Versuch {runde}: System gibt Rückmeldung und nächsten Hinweis ({len(offen)} Dialoge, qwen3.5:9b)")
    for k, s in enumerate(offen, 1):
        t = s["turns"][-1]
        z0 = time.time()
        erg_t = {"frage": s["frage"], "top_chunks": [], "hinweis": t["hinweis"], "loesung": s["loesung"]}
        fb = gib_feedback(erg_t, t["antwort"], sichtbar_extra=verlauf_text(s, runde - 1))
        urteil = fb.get("urteil") if fb.get("urteil") in TYPEN else ""
        t.update({"urteil": urteil, "rueckmeldung": fb.get("rueckmeldung", ""), "fb_geparst": bool(fb.get("geparst")),
                  "feedback_pruefung": fb.get("feedback_pruefung", ""), "leck_zahlen": "; ".join(fb.get("leck_zahlen", [])),
                  "neue_zahlen": "; ".join(fb.get("neue_zahlen", [])), "folgehinweis": "", "folgehinweis_pruefung": ""})
        if urteil == "richtig":
            s["ende"] = "richtig"
        elif runde >= args.versuche:
            s["ende"] = "max_versuche"
        elif args.folgehinweis:
            h, hp, _ = folgehinweis(s, t, runde + 1)
            if not h:  # Format fehlgeschlagen: Dialog endet, wird als solcher gezählt
                s["ende"] = "folgehinweis_fehlt"
            t.update({"folgehinweis": h, "folgehinweis_pruefung": hp})
        else:
            s["ende"] = "ohne_folgehinweis"
        speichere(zustand, pfad)
        print(f"  [{k}/{len(offen)}] {s['id']:<5} soll={t['typ_soll']:<10} urteil={urteil or '?':<10} {time.time() - z0:.0f}s", flush=True)


def objekte(zustand):
    """Alle zu bewertenden Objekte: (ob_id, art, s, t, text)."""
    for s in zustand["q"].values():
        for t in s["turns"]:
            if "urteil" not in t:
                continue
            yield f"{s['id']}-A{t['n']}", "antwort", s, t, t["antwort"]
            yield f"{s['id']}-H{t['n']}", "hinweis", s, t, t["hinweis"]
            yield f"{s['id']}-R{t['n']}", "rueckmeldung", s, t, t["rueckmeldung"]


def phase3(args, zustand, pfad, t0):
    zustand.setdefault("urteile", {})
    todo = [o for o in objekte(zustand) if o[0] not in zustand["urteile"]]
    stunde(t0, f"Phase 3/4: Rubrik-Bewertung durch {args.richter} ({len(todo)} Objekte)")
    items_von = {"hinweis": HINWEIS_ITEMS, "rueckmeldung": FEEDBACK_ITEMS, "antwort": SIM_ITEMS}
    for k, (ob, art, s, t, text) in enumerate(todo, 1):
        if not text.strip():
            zustand["urteile"][ob] = {"art": art, "leer": True}
            continue
        roh = llm(args.richter, judge_prompt(art, s, t, text), {"temperature": 0, "seed": 42, "num_predict": 400})
        zustand["urteile"][ob] = {"art": art, **parse_judge(roh, items_von[art])}
        if k % 10 == 0 or k == len(todo):
            speichere(zustand, pfad)
            print(f"  [{k}/{len(todo)}] bewertet", flush=True)
    speichere(zustand, pfad)


# ----------------------------------------------------------------------------------------- Ausgabe
def schreibe_csv(pfad, felder, zeilen):
    with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=felder, extrasaction="ignore")
        w.writeheader()
        w.writerows(zeilen)


def ausgabe(args, zustand, label, t0):
    ev = Path("evaluationsdaten")
    basis = ev / f"hinweis_dialog_{label}"
    urt = zustand.get("urteile", {})
    zeilen = []
    for s in zustand["q"].values():
        for t in s["turns"]:
            if "urteil" not in t:
                continue
            ob = lambda art: urt.get(f"{s['id']}-{art}{t['n']}", {})  # noqa: E731
            z = {"id": s["id"], "buch": s["buch"], "frage": s["frage"], "kernaussage": s["kernaussage"],
                 "versuch": t["n"], "hinweis": t["hinweis"], "hinweis_pruefung": t["hinweis_pruefung"],
                 "typ_soll": t["typ_soll"], "antwort": t["antwort"], "urteil": t["urteil"],
                 "urteil_treffer": t["urteil"] == t["typ_soll"],
                 "binaer_treffer": (t["urteil"] == "richtig") == (t["typ_soll"] == "richtig"),
                 "rueckmeldung": t["rueckmeldung"], "feedback_pruefung": t["feedback_pruefung"],
                 "fb_leck_zahlen": t["leck_zahlen"], "fb_neue_zahlen": t["neue_zahlen"],
                 "folgehinweis": t["folgehinweis"], "folgehinweis_pruefung": t["folgehinweis_pruefung"],
                 "hinweis_zahlleck": bool(hinweis_verraet_zahl(s["frage"], t["hinweis"], s["loesung"])),
                 "hinweis_loesungswortanteil": loesungswort_anteil(t["hinweis"], s["loesung"], s["frage"]),
                 "dialog_ende": s["ende"], "loesung": s["loesung"]}
            for k in HINWEIS_ITEMS:
                z[f"J_H_{k}"] = ob("H").get(k, "")
            for k in FEEDBACK_ITEMS:
                z[f"J_R_{k}"] = ob("R").get(k, "")
            z["J_S1"] = ob("A").get("S1", "")
            zeilen.append(z)
    felder = list(zeilen[0].keys()) if zeilen else ["id"]
    schreibe_csv(f"{basis}_dialoge.csv", felder, zeilen)

    # Bewertungsbogen für zwei Menschen: verblindet (keine Richterwerte, kein Soll-Typ, kein Urteil)
    rnd = random.Random(args.seed + 7)
    alle = [(ob, art, s, t, text) for ob, art, s, t, text in objekte(zustand) if art in ("hinweis", "rueckmeldung") and text.strip()]
    h = [o for o in alle if o[1] == "hinweis"]
    r = [o for o in alle if o[1] == "rueckmeldung"]
    probe = rnd.sample(h, min(24, len(h))) + rnd.sample(r, min(16, len(r)))
    rnd.shuffle(probe)
    bogen = []
    for n, (ob, art, s, t, text) in enumerate(probe, 1):
        items = HINWEIS_ITEMS if art == "hinweis" else FEEDBACK_ITEMS
        z = {"bogen_nr": n, "ob_id": ob, "art": "Hinweis" if art == "hinweis" else "Rückmeldung", "frage": s["frage"],
             "loesung_referenz": s["loesung"], "verlauf_davor": verlauf_text(s, t["n"] - 1),
             "antwort_der_person": t["antwort"] if art == "rueckmeldung" else "",
             "hinweis_den_die_person_sah": t["hinweis"] if art == "rueckmeldung" else "", "zu_bewerten": text}
        for rater in ("R1", "R2"):
            for k in list(items) + [""] * (6 - len(items)):
                if k:
                    z[f"{rater}_{k}"] = ""
        bogen.append(z)
    bfelder = ["bogen_nr", "ob_id", "art", "frage", "loesung_referenz", "verlauf_davor", "antwort_der_person",
               "hinweis_den_die_person_sah", "zu_bewerten"] + [f"{r}_{k}" for r in ("R1", "R2") for k in list(HINWEIS_ITEMS) + list(FEEDBACK_ITEMS)]
    schreibe_csv(f"{basis}_bewertungsbogen.csv", bfelder, bogen)
    legende = ["Bewertungsbogen: je Zeile ein Objekt. 'Hinweis' mit P1-P6, 'Rückmeldung' mit R1-R4 bewerten, nicht benötigte "
               "Spalten leer lassen. Werte: ja / teilweise / nein. Zwei Personen getrennt, ohne Absprache.", ""]
    legende += [f"{k}  {v}" for k, v in {**HINWEIS_ITEMS, **FEEDBACK_ITEMS}.items()]
    Path(f"{basis}_legende.txt").write_text("\n".join(legende), encoding="utf-8")

    # Zusammenfassung
    qs = [s for s in zustand["q"].values()]
    ok = [s for s in qs if s["ok"]]
    L = [f"Hinweis-Dialogtest {label}  ({datetime.datetime.now():%d.%m.%Y %H:%M})",
         f"System: qwen3.5:9b (V11B: G-v4, RP-v5, HP-v4, {FEEDBACK_PROMPT_VERSION}/FP-v3), Folgehinweis {FOLGEHINWEIS_VERSION}; "
         f"Simulator {args.lerner}; Richter {args.richter}; Soll-Anteil richtig {args.p_richtig:.0%}; Seed {args.seed}",
         f"Fragen: {len(qs)} (Dialog möglich: {len(ok)}; ohne Dialog: Gate/Verweigerung/Parse)",
         "Dialogende: " + ", ".join(f"{k}={v}" for k, v in sorted(Counter(s['ende'] for s in ok).items())),
         f"Versuche gesamt: {len(zeilen)}", ""]
    L.append("Urteil des Systems gegen Soll-Typ der Simulation (Zeile = Soll, Spalte = Urteil):")
    L.append(f"{'':<12}" + "".join(f"{u:>12}" for u in TYPEN + ("?",)))
    for typ in TYPEN:
        c = Counter(z["urteil"] or "?" for z in zeilen if z["typ_soll"] == typ)
        L.append(f"{typ:<12}" + "".join(f"{c.get(u, 0):>12}" for u in TYPEN + ("?",)))
    n = max(1, len(zeilen))
    L.append(f"Exakter Treffer: {sum(z['urteil_treffer'] for z in zeilen)}/{len(zeilen)} "
             f"({sum(z['urteil_treffer'] for z in zeilen) / n:.0%}); richtig-vs-nicht-richtig: "
             f"{sum(z['binaer_treffer'] for z in zeilen)}/{len(zeilen)} ({sum(z['binaer_treffer'] for z in zeilen) / n:.0%})")
    fa = sum(1 for z in zeilen if z["urteil"] == "richtig" and z["typ_soll"] != "richtig")
    fr = sum(1 for z in zeilen if z["urteil"] != "richtig" and z["typ_soll"] == "richtig")
    L.append(f"Falsch angenommen (Urteil richtig, Soll nicht richtig): {fa}; falsch abgelehnt (Soll richtig, Urteil nicht richtig): {fr}")
    L.append("")
    L.append("Automatische Leck-Prüfung: Hinweise mit Lösungszahl: "
             f"{sum(z['hinweis_zahlleck'] for z in zeilen)}/{len(zeilen)}; Rückmeldungen mit Lösungszahl: "
             f"{sum(bool(z['fb_leck_zahlen']) for z in zeilen)}/{len(zeilen)}; mit neuer Zahl: {sum(bool(z['fb_neue_zahlen']) for z in zeilen)}")
    L.append("Hinweis-Prüfung HP-v4 beim Folgehinweis: " + ", ".join(f"{k or '-'}={v}" for k, v in sorted(Counter(z['folgehinweis_pruefung'] for z in zeilen if z['folgehinweis']).items())))
    L.append("")
    L.append(f"Rubrik durch {args.richter} (Anteil ja / teilweise / nein, Fehlparser in Klammern). Objekte: Hinweise = je Versuch einer.")
    for titel, praefix, items in (("Hinweise", "J_H_", HINWEIS_ITEMS), ("Rückmeldungen", "J_R_", FEEDBACK_ITEMS), ("Simulierte Antworten", "J_", SIM_ITEMS)):
        L.append(f"  {titel}:")
        for k in items:
            werte = [z[f"{praefix}{k}"] for z in zeilen]
            c = Counter(werte)
            m = max(1, len(werte))
            L.append(f"    {k}: ja {c['ja'] / m:.0%} / teilweise {c['teilweise'] / m:.0%} / nein {c['nein'] / m:.0%}  (nicht lesbar: {c['']})")
    L.append("")
    L.append("Hinweise nach Versuch (P1 = ja in %, P4 = ja in %):")
    for v in range(1, args.versuche + 1):
        zv = [z for z in zeilen if z["versuch"] == v]
        if zv:
            L.append(f"    Versuch {v}: n={len(zv)}  P1 ja {sum(z['J_H_P1'] == 'ja' for z in zv) / len(zv):.0%}  "
                     f"P4 ja {sum(z['J_H_P4'] == 'ja' for z in zv) / len(zv):.0%}")
    L += ["", "Grenzen: simulierte Lernende; Referenz = Systemlösung; Richter ohne Abgleich mit Menschen kein Beleg; kein Modellierungs-,",
          "Diagnose- oder Ausblendungsbaustein (nicht umgesetzt). N100 ist kein Held-out-Satz für V11B.",
          f"Nächster Schritt: {basis.name}_bewertungsbogen.csv von zwei Personen ausfüllen, danach Richter gegen Menschen (gewichtetes Kappa) abgleichen.",
          f"Gesamtdauer: {(time.time() - t0) / 60:.0f} min"]
    Path(f"{basis}_zusammenfassung.txt").write_text("\n".join(L), encoding="utf-8")
    print("\n" + "\n".join(L))
    return [f"{basis}_dialoge.csv", f"{basis}_bewertungsbogen.csv", f"{basis}_legende.txt", f"{basis}_zusammenfassung.txt"]


def doku_und_git(label, dateien, vorher):  # vorher=True: Pilot (keine Doku, kein Commit, nur Kopien)
    text = (f"Hinweis-Dialogtest {label} ({datetime.date.today():%d %b %Y}): N100 (70 Fischer + 30 Böge), V11B eingefroren. "
            f"Je Frage bis zu {MAX_VERSUCHE} Versuche: simulierte Lernende (anderes Modell, ca. 30 % richtig), Rückmeldung IF-v5, "
            f"Folgehinweis {FOLGEHINWEIS_VERSION}; Rubrik P1-P6 / R1-R4 durch einen Richter (kein Generator), Bewertungsbogen für zwei "
            f"Menschen. Skript skripte/evaluation/teste_hinweis_dialog.py; Ergebnisse evaluationsdaten/hinweis_dialog_{label}_*. "
            f"Kein Beleg im Beitrag ohne Abgleich Richter gegen Menschen.")
    marke = f"## Hinweis-Dialogtest {label}"
    for f in (() if vorher else ("README.md", *glob.glob("PROZESSABLAUF.md"), *glob.glob("doku/PROZESSABLAUF.md"), *glob.glob("docs/PROZESSABLAUF.md"))):
        p = Path(f)
        if p.exists() and marke not in p.read_text(encoding="utf-8"):
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"\n{marke}\n{text}\n")
            print(f"{f}: Abschnitt angehängt.")
    if Path(".git").is_dir() and not vorher:
        subprocess.run(["git", "add", "-A"], check=False)
        r = subprocess.run(["git", "commit", "-q", "-m", f"Hinweis-Dialogtest {label}: Skript und Ergebnisse"], check=False)
        print("Commit angelegt." if r.returncode == 0 else "Nichts zu committen.")
    for d in glob.glob("/mnt/c/Users/*/Downloads"):
        if any(x in d for x in ("Public", "Default", "All Users")):
            continue
        for f in dateien:
            try:
                shutil.copy2(f, d)
            except OSError:
                pass
        print(f"Kopien in {d}")
        break


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="HD-V1")
    ap.add_argument("--limit", type=int, default=0, help="Pilot: nur so viele zufällig gewählte Fragen")
    ap.add_argument("--lerner", default="granite4.1:8b")
    ap.add_argument("--richter", default="mistral-nemo")
    ap.add_argument("--p-richtig", type=float, default=0.3)
    ap.add_argument("--versuche", type=int, default=MAX_VERSUCHE)
    ap.add_argument("--seed", type=int, default=2028)
    ap.add_argument("--kein-folgehinweis", dest="folgehinweis", action="store_false")
    ap.add_argument("--ohne-richter", action="store_true", help="Phase 3 überspringen")
    args = ap.parse_args()
    t0 = time.time()
    if not Path(KB).exists():
        raise SystemExit(f"Wissensbasis nicht gefunden: {KB} (aus ~/RAG starten)")
    if rag_pipeline.MODEL_NAME in (args.lerner, args.richter):
        raise SystemExit("ABBRUCH: Simulator und Richter dürfen nicht das Generatormodell sein.")
    if args.lerner == args.richter:
        raise SystemExit("ABBRUCH: Simulator und Richter sollten verschiedene Modelle sein.")
    pruefe_modelle(rag_pipeline.MODEL_NAME, args.lerner, *([] if args.ohne_richter else [args.richter]))
    rag_pipeline.RRF_K = 5
    label = args.label + ("-PILOT" if args.limit else "")
    Path("evaluationsdaten").mkdir(exist_ok=True)
    pfad = Path(f"evaluationsdaten/hinweis_dialog_{label}_zustand.json")
    fortsetzung = pfad.exists()
    print("Konfiguration:", {k: v for k, v in sorted(os.environ.items()) if k.startswith("LERNASSISTENT_")})
    if not fortsetzung and Path(".git").is_dir():
        subprocess.run(["git", "add", "-A"], check=False)
        subprocess.run(["git", "commit", "-q", "-m", "Stand vor Hinweis-Dialogtest"], check=False)
        subprocess.run(["git", "tag", "vor-hinweisdialog"], check=False, stderr=subprocess.DEVNULL)
    zustand = json.loads(pfad.read_text(encoding="utf-8")) if fortsetzung else {"q": {}, "urteile": {}}
    if fortsetzung:
        print(f"Fortsetzung aus {pfad} ({len(zustand['q'])} Fragen schon beantwortet)")

    fragen = lade_fragen()
    if args.limit:
        idx = sorted(random.Random(args.seed).sample(range(len(fragen)), min(args.limit, len(fragen))))
        fragen = [fragen[i] for i in idx]
    chunks = lade_wissensbasis(KB)
    print(f"{len(fragen)} Fragen, {len(chunks)} Chunks, kb_hash={berechne_kb_hash(KB)}, Label={label}, "
          f"Simulator={args.lerner}, Richter={args.richter}")

    phase1(args, zustand, fragen, chunks, pfad, t0)
    for runde in range(1, args.versuche + 1):
        phase2_runde(args, zustand, runde, pfad, t0)
    if not args.ohne_richter:
        phase3(args, zustand, pfad, t0)
    dateien = ausgabe(args, zustand, label, t0)
    doku_und_git(label, dateien, vorher=bool(args.limit))
    # Pilot: einige Dialoge zur Sichtprüfung
    if args.limit:
        print("\n=== Sichtprüfung (Pilot) ===")
        for s in list(zustand["q"].values())[:args.limit]:
            if not s["ok"]:
                continue
            print(f"\n[{s['id']}] {s['frage']}\n  Lösung: {s['loesung'][:200]}")
            for t in s["turns"]:
                print(f"  V{t['n']} Hinweis: {t['hinweis']}\n     Soll {t['typ_soll']}: {t['antwort']}\n"
                      f"     Urteil {t.get('urteil')}: {t.get('rueckmeldung')}")
    stunde(t0, "Fertig")


if __name__ == "__main__":
    main()
