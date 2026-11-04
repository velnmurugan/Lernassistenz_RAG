"""
eval300_richter.py  (Eval300, Phase 2: Richter-Bewertung mit einem ZWEITEN Modell)
----------------------------------------------------------------------------------
Bewertet jede Antwort (ohne RAG und mit RAG) aus eval300_antworten_<LABEL>.csv gegen
  - die Referenzantwort und
  - die Referenzpassage aus dem Buch (automatisch gewählter Seitenausschnitt bzw. geprüftes Zitat).
Richter-Modell: Standard qwen3.5:4b (NICHT der Generator qwen3.5:9b), T = 0, Seed 42, Prompt R300-v1.

Regel (wie bei der Handbewertung von N100/NEU100 seit 25.10.2026, streng):
  KORREKT     alle Kernaussagen der Referenz, keine falsche Aussage, Zahl, Einheit oder Rechnung
  TEILWEISE   was gesagt wird, ist richtig, aber ein Teil der Kernaussage FEHLT (reine Auslassung)
  FALSCH      falscher Wert/Fakt/Einheit/Rechenfehler, Widerspruch zur Referenz, Kernaussage fehlt
  VERWEIGERT  Antwort lehnt ab / sagt, die Information fehle (bei Buchfragen zählt das wie falsch)
Fragen "ausserhalb" (nicht im Buch): Regel-Erkennung der Ablehnung (wie vergleich_mit_ohne_rag.py),
  dazu ein Richterurteil ABGELEHNT/BEANTWORTET; weichen beide ab, steht "pruefen" in der Spalte hinweis.

Fortsetzbar (gleicher Befehl). Ausgabe:
  evaluationsdaten/eval300_richter_<LABEL>_<MODELL>.csv
Start:
  python skripte/evaluation/eval300_richter.py EVAL300-V11B --richter qwen3.5:4b
  --denken   Denkmodus des Richters an (genauer bei Rechnungen, deutlich langsamer)
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import argparse
import collections
import csv
import os
import re
import time
from pathlib import Path

import rag_pipeline as rp

try:
    from ragas_auswertung import ist_modell_verweigerung
except Exception:  # Rückfall, falls ragas_auswertung nicht importierbar ist
    _V = re.compile(r"(nicht\s+im\s+(lern)?material|kann\s+ich\s+(\w+\s+){0,3}nicht\s+(sagen|beantworten)|"
                    r"(kontext|unterlagen|lernmaterial\w*)\s+(enthält|liefert|nennt)\s+(\w+\s+){0,4}?(nicht|kein\w*))", re.I)

    def ist_modell_verweigerung(t):
        return bool(_V.search(t[:300]))

PROMPT_VERSION = "R300-v1"
OPTIONEN = {"temperature": 0, "seed": 42}
URTEILE = ("KORREKT", "TEILWEISE", "FALSCH", "VERWEIGERT")
FELDER = ["id", "satz", "orig_id", "buch", "typ",
          "urteil_ohne", "begruendung_ohne", "urteil_mit", "begruendung_mit",
          "regel_ohne", "regel_mit", "hinweis", "richter", "prompt_version", "sek"]


def prompt_buchfrage(frage, referenz, passage, antwort):
    return (
        "Du bist Prüferin für Fachfragen aus der beruflichen Ausbildung (Elektrotechnik, Maschinenbau). "
        "Du prüfst eine Antwort gegen die Referenzantwort und den zugehörigen Lehrbuchausschnitt.\n\n"
        f"FRAGE:\n{frage}\n\n"
        f"REFERENZANTWORT (maßgeblich):\n{referenz}\n\n"
        f"LEHRBUCHAUSSCHNITT (Hilfe zur Prüfung; kann unvollständig oder schlecht lesbar sein):\n{passage[:2500]}\n\n"
        f"ZU PRÜFENDE ANTWORT:\n{antwort[:4000]}\n\n"
        "Regeln:\n"
        "- KORREKT: Die Antwort enthält alle Kernaussagen der Referenz und keine falsche Aussage. "
        "Zusätzliche richtige Informationen sind erlaubt. Gleichwertige Schreibweisen und gerundete Werte "
        "(Abweichung bis etwa 2 %) sind erlaubt.\n"
        "- TEILWEISE: Alles Gesagte ist richtig, aber ein Teil der Kernaussage fehlt.\n"
        "- FALSCH: Die Antwort enthält mindestens eine falsche Aussage, einen falschen Wert, eine falsche Einheit "
        "oder einen Rechenfehler, widerspricht der Referenz oder verfehlt die Kernaussage. Eine falsche "
        "Nebenaussage macht die Antwort FALSCH, auch wenn der Kern stimmt.\n"
        "- VERWEIGERT: Die Antwort lehnt ab oder sagt, dass die Information fehlt.\n"
        "Prüfe jede Zahl, Einheit und Rechnung nach. Bewerte nur den Inhalt, nicht Stil oder Länge.\n\n"
        "Antworte genau in zwei Zeilen:\n"
        "URTEIL: <KORREKT|TEILWEISE|FALSCH|VERWEIGERT>\n"
        "BEGRÜNDUNG: <ein Satz>"
    )


def prompt_ausserhalb(frage, antwort):
    return (
        "Ein Lernassistent soll nur Fragen aus seinem technischen Lehrmaterial beantworten. "
        "Die folgende Frage gehört NICHT zu diesem Material.\n\n"
        f"FRAGE:\n{frage}\n\nANTWORT DES ASSISTENTEN:\n{antwort[:3000]}\n\n"
        "Hat der Assistent abgelehnt bzw. gesagt, dass die Information nicht im Material steht (ABGELEHNT), "
        "oder hat er die Frage inhaltlich beantwortet (BEANTWORTET)? Wer ablehnt und trotzdem inhaltlich "
        "antwortet, gilt als BEANTWORTET.\n\n"
        "Antworte genau in zwei Zeilen:\nURTEIL: <ABGELEHNT|BEANTWORTET>\nBEGRÜNDUNG: <ein Satz>"
    )


_U = re.compile(r"URTEIL\W*:?\W*(KORREKT|TEILWEISE|FALSCH|VERWEIGERT|ABGELEHNT|BEANTWORTET)", re.I)
_B = re.compile(r"BEGR(?:Ü|UE)NDUNG\W*:\s*(.+)", re.I | re.S)


def frage_richter(prompt, modell, denken):
    for versuch in (1, 2):
        try:
            roh = rp.frage_llm(prompt if versuch == 1 else prompt + "\n\nNUR die zwei Zeilen URTEIL und BEGRÜNDUNG!",
                               model=modell, options=OPTIONEN, denken=denken)
        except Exception as e:
            print(f"   WARNUNG {type(e).__name__}: {str(e)[:100]}", flush=True)
            time.sleep(20)
            continue
        roh = re.sub(r"<think>.*?</think>", "", roh, flags=re.S)
        u = _U.search(roh)
        if u:
            b = _B.search(roh)
            return u.group(1).upper(), (b.group(1).strip().splitlines()[0] if b else "")[:300]
    return "FORMATFEHLER", ""


def lies(pfad):
    with open(pfad, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def schreibe(pfad, zeilen):
    tmp = Path(str(pfad) + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FELDER)
        w.writeheader()
        for z in zeilen:
            w.writerow({k: z.get(k, "") for k in FELDER})
    tmp.replace(pfad)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--richter", default=os.environ.get("EVAL300_RICHTER", "qwen3.5:4b"))
    ap.add_argument("--denken", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    if args.richter == rp.MODEL_NAME:
        print(f"WARNUNG: Richter {args.richter} ist gleich dem Generator {rp.MODEL_NAME}.")
    quelle = Path("evaluationsdaten") / f"eval300_antworten_{args.label}.csv"
    antworten = lies(quelle)[: args.limit]
    tag = re.sub(r"[^A-Za-z0-9.]+", "-", args.richter) + ("-denken" if args.denken else "")
    out = Path("evaluationsdaten") / f"eval300_richter_{args.label}_{tag}.csv"
    alt = {z["id"]: z for z in lies(out)} if out.exists() else {}
    print(f"{len(antworten)} Fragen | Richter {args.richter} (Denkmodus {'an' if args.denken else 'aus'}), {PROMPT_VERSION} | "
          f"schon bewertet: {sum(1 for a in antworten if alt.get(a['id'], {}).get('urteil_mit'))}\n", flush=True)
    zeilen = []
    for a in antworten:
        z = alt.get(a["id"])
        if z and z.get("urteil_ohne") and z.get("urteil_mit") and "FORMATFEHLER" not in (z["urteil_ohne"] + z["urteil_mit"]):
            zeilen.append(z)
            continue
        t0 = time.time()
        z = {k: a[k] for k in ("id", "satz", "orig_id", "buch", "typ")}
        z.update(richter=args.richter + (" (denken)" if args.denken else ""), prompt_version=PROMPT_VERSION)
        hinweise = []
        for seite in ("ohne", "mit"):
            antwort = a.get(f"antwort_{seite}", "")
            if not antwort or antwort.startswith("FEHLER"):
                z[f"urteil_{seite}"], z[f"begruendung_{seite}"] = "FEHLT", "(keine Antwort erzeugt)"
                continue
            regel = ist_modell_verweigerung(antwort) or (seite == "mit" and a.get("status_mit") in ("NICHT_IM_MATERIAL", "GATE"))
            z[f"regel_{seite}"] = "Verweigerung erkannt" if regel else ""
            if a["typ"] == "ausserhalb":
                u, b = frage_richter(prompt_ausserhalb(a["frage"], antwort), args.richter, args.denken)
                regel_u = "ABGELEHNT" if regel else "BEANTWORTET"
                if u in ("ABGELEHNT", "BEANTWORTET") and u != regel_u:
                    hinweise.append(f"pruefen {seite}: Regel {regel_u}, Richter {u}")
                z[f"urteil_{seite}"] = "ABLEHNUNG_OK" if regel_u == "ABGELEHNT" else "NICHT_ABGELEHNT"
                z[f"begruendung_{seite}"] = f"Richter: {u}. {b}"
            elif regel:
                z[f"urteil_{seite}"], z[f"begruendung_{seite}"] = "VERWEIGERT", "(Verweigerung per Regel erkannt)"
            else:
                u, b = frage_richter(prompt_buchfrage(a["frage"], a["referenz"], a.get("referenz_passage", ""), antwort),
                                     args.richter, args.denken)
                z[f"urteil_{seite}"], z[f"begruendung_{seite}"] = u, b
        z["hinweis"] = "; ".join(hinweise)
        z["sek"] = round(time.time() - t0, 1)
        print(f"[{z['id']}] {z['satz']:<6} {z['typ']:<11} ohne {z['urteil_ohne']:<16} mit {z['urteil_mit']:<16} {z['hinweis']}", flush=True)
        zeilen.append(z)
        schreibe(out, zeilen)
    schreibe(out, zeilen)
    for seite in ("ohne", "mit"):
        c = collections.Counter(z[f"urteil_{seite}"] for z in zeilen)
        print(f"{seite}: " + "  ".join(f"{k} {v}" for k, v in c.most_common()))
    print(f"\nFertig: {out}")


if __name__ == "__main__":
    main()
