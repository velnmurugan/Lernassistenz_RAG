"""
antworten300.py  (Fragen300, Schritt 1: Antworten ohne und mit RAG, Stand V20)
Wie eval300_antworten.py (Prompt O-v1 ohne RAG, volle Pipeline mit RAG, bewertet wird die LÖSUNG), zusätzlich je Antwort
die Zeiten von Ollama selbst (Modell laden, Prompt lesen, Antwort erzeugen; Summe über alle Aufrufe der Antwort).
Fortsetzbar: fertige Antworten werden übersprungen.
  python skripte/evaluation/antworten300.py F300-V20 --fragen daten/testfragen/fragen300.csv [--limit 4]
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))

import argparse
import csv
import time
from pathlib import Path

import rag_pipeline as rp
from eval300_antworten import prompt_ohne_rag, wiederhole, OHNE_RAG_PROMPT_VERSION

FELDER = ["id", "buch", "typ", "frage",
          "antwort_ohne", "sek_ohne", "ollama_aufrufe_ohne", "laden_s_ohne", "prompt_s_ohne", "erzeugen_s_ohne",
          "status_mit", "antwort_mit", "sek_mit", "ollama_aufrufe_mit", "laden_s_mit", "prompt_s_mit", "erzeugen_s_mit",
          "quellen_mit", "rechen_pruefung_mit", "rechen_befund_mit", "hinweis_mit", "ueberlegung_mit"]

# --- Ollama-Zeiten mitschreiben (ändert nichts am Ablauf) ---
_ZEIT = {"n": 0, "laden": 0.0, "prompt": 0.0, "erzeugen": 0.0}
_post_original = rp.requests.post


def _post_mit_zeiten(*a, **k):
    r = _post_original(*a, **k)
    try:
        j = r.json()
        _ZEIT["n"] += 1
        _ZEIT["laden"] += j.get("load_duration", 0) / 1e9
        _ZEIT["prompt"] += j.get("prompt_eval_duration", 0) / 1e9
        _ZEIT["erzeugen"] += j.get("eval_duration", 0) / 1e9
    except Exception:
        pass
    return r


rp.requests.post = _post_mit_zeiten


def zeiten_start():
    _ZEIT.update(n=0, laden=0.0, prompt=0.0, erzeugen=0.0)


def zeiten_in(z, seite):
    z[f"ollama_aufrufe_{seite}"] = _ZEIT["n"]
    for k in ("laden", "prompt", "erzeugen"):
        z[f"{k}_s_{seite}"] = round(_ZEIT[k], 2)


def lies(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def schreibe(p, zeilen):
    tmp = Path(str(p) + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, extrasaction="ignore")
        w.writeheader()
        w.writerows(zeilen)
    tmp.replace(p)


def fertig(z, s):
    a = z.get(f"antwort_{s}", "")
    return bool(a) and not a.startswith("FEHLER")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--fragen", default="daten/testfragen/fragen300.csv")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--retrieval", default="hybrid_kg_rr")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    fragen = lies(a.fragen)[: a.limit]
    out = Path("evaluationsdaten") / f"antworten300_{a.label}.csv"
    alt = {z["id"]: z for z in lies(out)} if out.exists() else {}
    chunks = rp.lade_wissensbasis(a.kb)
    konfig = (f"Generator {rp.MODEL_NAME} {rp.GENERIERUNGS_OPTIONEN}; ohne RAG {OHNE_RAG_PROMPT_VERSION}; mit RAG "
              f"G={rp.SCAFFOLDING_VERSION} RP={'RP-v13' if getattr(rp, 'RP_V13', False) else rp.RECHEN_PRUEFUNG_VERSION} "
              f"RB={rp.NACHRECHNUNG_VERSION} CTX={rp.KONTEXT_TOKENS}; Retrieval {a.retrieval}; KB {a.kb} "
              f"({rp.berechne_kb_hash(a.kb)}); Fragen {a.fragen} ({len(fragen)})")
    out.with_name(out.stem + "_konfig.txt").write_text(konfig + "\n", encoding="utf-8")
    print(konfig, flush=True)
    zeilen = []
    for q in fragen:
        z = {"id": q["id"], "buch": q["buch"], "typ": q["typ"], "frage": q["frage"], **{k: v for k, v in alt.get(q["id"], {}).items() if v}}
        if not fertig(z, "ohne"):
            zeiten_start()
            t0 = time.time()
            z["antwort_ohne"] = wiederhole(lambda: rp.frage_llm(prompt_ohne_rag(q["frage"]), options=rp.GENERIERUNGS_OPTIONEN),
                                           "FEHLER (Zeitüberschreitung)")
            z["sek_ohne"] = round(time.time() - t0, 1)
            zeiten_in(z, "ohne")
        if not fertig(z, "mit"):
            zeiten_start()
            t0 = time.time()
            erg = wiederhole(lambda: rp.beantworte_frage(q["frage"], chunks, methode=a.retrieval),
                             {"status": "FEHLER", "loesung": "FEHLER (Zeitüberschreitung)", "quellen": []})
            z["sek_mit"] = round(time.time() - t0, 1)
            zeiten_in(z, "mit")
            z["status_mit"] = erg.get("status", "")
            z["antwort_mit"] = erg.get("loesung", "")
            z["quellen_mit"] = "; ".join(c["id"] for c in erg.get("quellen", []))
            z["rechen_pruefung_mit"] = erg.get("rechen_pruefung", "")
            z["rechen_befund_mit"] = erg.get("rechen_befund", "")
            z["hinweis_mit"] = erg.get("hinweis", "")  # V20-Hinweis (für die Hinweisbewertung; nicht im Bewertungsbogen)
            z["ueberlegung_mit"] = erg.get("hinweis_ueberlegung", "")
        print(f"[{q['id']:>4}] {q['buch'][:8]:<8} {q['typ']:<11} ohne {z.get('sek_ohne', '')!s:>6} s | "
              f"mit {z.get('sek_mit', '')!s:>6} s {z.get('status_mit', '')}", flush=True)
        zeilen.append(z)
        schreibe(out, zeilen + [alt[i] for i in alt if i not in {x["id"] for x in zeilen}])
    schreibe(out, zeilen + [alt[i] for i in alt if i not in {x["id"] for x in zeilen}])
    offen = [z["id"] for z in zeilen if not (fertig(z, "ohne") and fertig(z, "mit"))]
    print(f"Fertig: {out} ({len(zeilen)} Fragen, unvollständig: {len(offen)} {offen[:10]})")


if __name__ == "__main__":
    main()
