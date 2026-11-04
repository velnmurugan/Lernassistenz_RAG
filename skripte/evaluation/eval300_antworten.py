"""
eval300_antworten.py  (Eval300, Phase 1: Antworten erzeugen)
-------------------------------------------------------------
Beantwortet die 300 gemischten Fragen (N100 + NEU100 + Fragenset v4) zweimal mit dem Generator
(Standard qwen3.5:9b, T = 0, Seed 42):
  OHNE RAG  nur die Frage, Prompt O-v1 (wie in vergleich_mit_ohne_rag.py; vergleichbar mit N100/NEU100)
  MIT RAG   volle Pipeline (Retrieval hybrid_kg_rr + aktuelle Prompt-Versionen aus den Umgebungsvariablen,
            V11B: LERNASSISTENT_G=G-v4, LERNASSISTENT_RP=RP-v5, LERNASSISTENT_FS=aus); bewertet wird die LÖSUNG.
Es wird NICHT bewertet (das macht eval300_richter.py mit einem anderen Modell).

Fortsetzbar: bereits beantwortete Fragen werden übersprungen (gleicher Befehl nach Abbruch).
Ausgabe (enthält Buchinhalte -> nicht ins Git):
  evaluationsdaten/eval300_antworten_<LABEL>.csv   und   ..._konfig.txt

Start (aus ~/RAG, Umgebung pilot_rag, Ollama läuft):
  python skripte/evaluation/eval300_antworten.py EVAL300-V11B --kb daten/wissensbasen/knowledge_base_fischer_boege_v7r.json
  --limit 6        nur die ersten 6 Fragen (Probelauf)
  --nur ohne|mit   nur eine Seite erzeugen
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import argparse
import csv
import time
from pathlib import Path

import rag_pipeline as rp

OHNE_RAG_PROMPT_VERSION = "O-v1"
FRAGEN_STANDARD = "daten/testfragen/fragen_eval300.csv"
FELDER = ["id", "satz", "orig_id", "buch", "typ", "frage", "referenz", "referenz_passage", "seite_pdf",
          "antwort_ohne", "sek_ohne",
          "status_mit", "antwort_mit", "sek_mit", "quellen_mit", "kontext_mit",
          "rechen_pruefung_mit", "rechen_befund_mit"]


def prompt_ohne_rag(frage):
    # identisch mit O-v1 in vergleich_mit_ohne_rag.py (Vergleichbarkeit mit N100/NEU100)
    return (
        "Du bist Fachlehrkraft für Elektrotechnik in der beruflichen Ausbildung. "
        "Beantworte die Frage einer oder eines Auszubildenden fachlich korrekt und knapp "
        "(höchstens 6 Sätze). Bei Rechenaufgaben: Formel, eingesetzte Werte, Ergebnis mit Einheit. "
        "Wenn du etwas nicht sicher weißt, sage das ausdrücklich, statt zu raten.\n\n"
        f"Frage: {frage}\n\nAntwort:"
    )


def wiederhole(fn, ersatz, versuche=3, pause=20):
    for i in range(1, versuche + 1):
        try:
            return fn()
        except Exception as e:  # Ollama-Zeitüberschreitung u. ä.: Lauf geht weiter
            print(f"   WARNUNG Versuch {i}/{versuche}: {type(e).__name__}: {str(e)[:120]}", flush=True)
            time.sleep(pause)
    return ersatz


def lies_csv(pfad):
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


def fertig(z, seite):
    a = z.get(f"antwort_{seite}", "")
    return bool(a) and not a.startswith("FEHLER")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("label")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--fragen", default=FRAGEN_STANDARD)
    ap.add_argument("--retrieval", default="hybrid_kg_rr")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--nur", choices=["ohne", "mit", "beide"], default="beide")
    ap.add_argument("--logge", action="store_true", help="RAG-Antworten auch in interaktionen.csv protokollieren (RAGAS)")
    args = ap.parse_args()

    fragen = lies_csv(args.fragen)[: args.limit]
    out = Path("evaluationsdaten") / f"eval300_antworten_{args.label}.csv"
    alt = {z["id"]: z for z in lies_csv(out)} if out.exists() else {}
    chunks = rp.lade_wissensbasis(args.kb)
    text_von = {c.get("id"): c.get("text", "") for c in chunks}
    kb_hash = rp.berechne_kb_hash(args.kb)
    konfig = (f"Generator {rp.MODEL_NAME} {rp.GENERIERUNGS_OPTIONEN}; ohne RAG: {OHNE_RAG_PROMPT_VERSION}; "
              f"mit RAG: {rp.SCAFFOLDING_VERSION}/{rp.RECHEN_PRUEFUNG_VERSION}/{rp.HINWEIS_PRUEFUNG_VERSION}, "
              f"Retrieval {args.retrieval}, KB {args.kb} ({kb_hash}); Fragen {args.fragen} ({len(fragen)})")
    out.with_name(out.stem + "_konfig.txt").write_text(konfig + "\n", encoding="utf-8")
    print(f"{len(fragen)} Fragen, davon {sum(1 for q in fragen if q['id'] in alt)} schon begonnen | {konfig}\n", flush=True)

    zeilen = []
    for q in fragen:
        z = {**q, **{k: v for k, v in alt.get(q["id"], {}).items() if k not in q}}
        if args.nur in ("ohne", "beide") and not fertig(z, "ohne"):
            t0 = time.time()
            z["antwort_ohne"] = wiederhole(lambda: rp.frage_llm(prompt_ohne_rag(q["frage"]), options=rp.GENERIERUNGS_OPTIONEN),
                                           "FEHLER (Zeitüberschreitung)")
            z["sek_ohne"] = round(time.time() - t0, 1)
        if args.nur in ("mit", "beide") and not fertig(z, "mit"):
            t0 = time.time()
            erg = wiederhole(lambda: rp.beantworte_frage(q["frage"], chunks, methode=args.retrieval),
                             {"status": "FEHLER", "loesung": "FEHLER (Zeitüberschreitung)", "quellen": []})
            z["sek_mit"] = round(time.time() - t0, 1)
            if args.logge and erg.get("status") != "FEHLER":
                erg["kb_hash"] = kb_hash
                rp.protokolliere_interaktion(args.label, erg, scaffolding_stufe_erreicht=len(rp.scaffolding_marker()))
            z["status_mit"] = erg.get("status", "")
            z["antwort_mit"] = erg.get("loesung", "")
            ids = [c["id"] for c in erg.get("quellen", [])]
            z["quellen_mit"] = "; ".join(ids)
            z["kontext_mit"] = " ||| ".join(f"[{i}] {text_von.get(i, '')}" for i in ids)[:8000]
            z["rechen_pruefung_mit"] = erg.get("rechen_pruefung", "")
            z["rechen_befund_mit"] = erg.get("rechen_befund", "")
        print(f"[{q['id']}] {q['satz']:<6} {q['typ']:<11} ohne {z.get('sek_ohne', '')!s:>6} s | "
              f"mit {z.get('sek_mit', '')!s:>6} s {z.get('status_mit', '')}", flush=True)
        zeilen.append(z)
        schreibe(out, zeilen + [alt[i] for i in alt if i not in {x['id'] for x in zeilen}])
    schreibe(out, zeilen)
    offen = [z["id"] for z in zeilen if (args.nur != "mit" and not fertig(z, "ohne")) or (args.nur != "ohne" and not fertig(z, "mit"))]
    print(f"\nFertig: {out}  ({len(zeilen)} Fragen, unvollständig: {len(offen)} {offen[:10]})")


if __name__ == "__main__":
    main()
