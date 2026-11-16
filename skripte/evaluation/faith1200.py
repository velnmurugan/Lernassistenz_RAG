"""
faith1200.py  (Study 1: faithfulness for all four conditions = 1080 answers to the 270 book questions)

Same method as faith300.py (prompts J-v1 from ragas_auswertung.py, judge gemma4:12b by default):
the answer is split into statements, each statement is checked against the retrieved passages,
Faithfulness = supported statements / checkable statements.

Context per condition (each pair "without / with RAG" is checked against the SAME passages):
  qw_o, qw_m   -> passages qwen V20 received   (antworten300_F300-V20.csv, column quellen_mit)
  gpt_o, gpt_m -> passages GPT with RAG received (gptrag300_F300-GPT61SOL-RAG.csv, column quellen)
They differ where the formula search of V20 added passages.

Existing values from faith300.py (faith300_F300-V20.csv) are taken over, not recomputed (same judge, same prompts,
same context). Results: evaluationsdaten/faith1200.csv (+ _details.jsonl).
Resumable: start the same command again after an interruption.

  python -u skripte/evaluation/faith1200.py --limit 2          # test: 2 questions
  python -u skripte/evaluation/faith1200.py | tee -a protokolle/faith1200.txt
  python skripte/evaluation/faith1200.py --summary              # means only
Options: --nur gpt_o,gpt_m   (only some conditions)   --richter <ollama model>
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))

import argparse
import csv
import json
import time
from pathlib import Path

import rag_pipeline as rp
import ragas_auswertung as ra

csv.field_size_limit(10**9)
EV = Path("evaluationsdaten")
COND = ["gpt_o", "gpt_m", "qw_o", "qw_m"]
FELDER = ["id", "buch", "typ", "bedingung", "kontext", "faithfulness", "aussagen", "gestuetzt", "unlesbar",
          "meta_verworfen", "sek", "richter", "quelle"]


def lies(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ids_aus(s):
    return [i.strip() for i in (s or "").split(";") if i.strip()]


def schreibe(out, zeilen):
    tmp = out.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FELDER)
        w.writeheader()
        w.writerows(zeilen)
    tmp.replace(out)


def zusammenfassung(zeilen):
    print("\nFaithfulness (mean over book questions with a value)")
    for c in COND:
        v = [float(z["faithfulness"]) for z in zeilen if z["bedingung"] == c and z["faithfulness"] not in ("", None)]
        vr = [float(z["faithfulness"]) for z in zeilen if z["bedingung"] == c and z["faithfulness"] not in ("", None)
              and z["typ"].lower() not in ("rechnung",)]
        if v:
            print(f"  {c:6s} n={len(v):3d}  mean={sum(v)/len(v):.3f}   without calculation: n={len(vr)} mean={sum(vr)/max(1,len(vr)):.3f}")
        else:
            print(f"  {c:6s} no values yet")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--richter", default="gemma4:12b")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--qwen", default=str(EV / "antworten300_F300-V20.csv"))
    ap.add_argument("--gpt", default=str(EV / "gpt300_F300-GPT61SOL.csv"))
    ap.add_argument("--gptrag", default=str(EV / "gptrag300_F300-GPT61SOL-RAG.csv"))
    ap.add_argument("--alt", default=str(EV / "faith300_F300-V20.csv"), help="existing V20 values to take over")
    ap.add_argument("--nur", default=",".join(COND), help="conditions, e.g. gpt_o,gpt_m")
    ap.add_argument("--limit", type=int, help="only the first N book questions (test)")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()

    out = EV / "faith1200.csv"
    det = EV / "faith1200_details.jsonl"
    zeilen = lies(out) if out.exists() else []
    if a.summary:
        return zusammenfassung(zeilen)

    for p in (a.qwen, a.gpt, a.gptrag):
        if not Path(p).exists():
            _sys.exit(f"missing file: {p}  (pass the right path with --qwen / --gpt / --gptrag)")
    ra.PROMPT_VERSION = "J-v1"
    nur = [c.strip() for c in a.nur.split(",") if c.strip() in COND]

    qw = {z["id"]: z for z in lies(a.qwen)}
    gp = {z["id"]: z for z in lies(a.gpt)}
    gr = {z["id"]: z for z in lies(a.gptrag)}
    fragen = [z for z in lies(a.qwen) if z["buch"] != "Außerhalb"][: a.limit]

    fertig = {(z["id"], z["bedingung"]) for z in zeilen}
    # take over existing values from faith300.py
    if Path(a.alt).exists():
        n = 0
        for z in lies(a.alt):
            c = {"ohne": "qw_o", "mit": "qw_m"}.get(z["seite"])
            if c and (z["id"], c) not in fertig and z.get("richter", a.richter) == a.richter:
                zeilen.append({"id": z["id"], "buch": z["buch"], "typ": z["typ"], "bedingung": c, "kontext": "qwen",
                               "faithfulness": z["faithfulness"], "aussagen": z["aussagen"], "gestuetzt": z["gestuetzt"],
                               "unlesbar": z["unlesbar"], "meta_verworfen": z["meta_verworfen"], "sek": z["sek"],
                               "richter": z.get("richter", a.richter), "quelle": Path(a.alt).name})
                fertig.add((z["id"], c)); n += 1
        if n:
            print(f"taken over from {Path(a.alt).name}: {n} values")
            schreibe(out, zeilen)

    lookup = {c["id"]: c for c in rp.lade_wissensbasis(a.kb)}
    todo = [(f, c) for f in fragen for c in nur if (f["id"], c) not in fertig]
    print(f"judge {a.richter}: {len(fertig)} done, {len(todo)} to go -> {out}")

    for i, (f, c) in enumerate(todo, 1):
        qid = f["id"]
        if c.startswith("qw"):
            kontext_ids, kname = ids_aus(qw[qid].get("quellen_mit")), "qwen"
            antwort = qw[qid].get("antwort_ohne" if c == "qw_o" else "antwort_mit", "")
        else:
            kontext_ids, kname = ids_aus((gr.get(qid) or {}).get("quellen")), "gpt"
            antwort = (gp.get(qid) or {}).get("antwort_gpt", "") if c == "gpt_o" else (gr.get(qid) or {}).get("antwort_gpt_rag", "")
        kontext = rp._material_text([lookup[x] for x in kontext_ids if x in lookup])
        if not kontext or not antwort or antwort.startswith("FEHLER"):
            print(f"[{i}/{len(todo)}] {qid} {c}: skipped (no context or no answer)")
            continue
        t0 = time.time()
        for versuch in range(3):
            try:
                aussagen, verworfen = ra.extrahiere_statements(f["frage"], antwort, a.richter)
                details = []
                for s in aussagen:
                    u, b = ra.pruefe_statement_gestuetzt(s, kontext, a.richter)
                    details.append({"aussage": s, "urteil": u, "begruendung": b})
                break
            except Exception as e:
                msg = str(e)
                if "404" in msg:
                    _sys.exit(f"Ollama answered 404: model '{a.richter}' not found. Check `ollama list`, then `ollama pull {a.richter}`.")
                print(f"  {qid} {c} attempt {versuch+1} failed: {msg[:160]} -> retry in 20 s")
                time.sleep(20)
        else:
            print(f"  {qid} {c} SKIPPED after 3 attempts (run again later)")
            continue
        gueltig = [d for d in details if d["urteil"] is not None]
        score = round(sum(d["urteil"] for d in gueltig) / len(gueltig), 4) if gueltig else ""
        zeilen.append({"id": qid, "buch": f["buch"], "typ": f["typ"], "bedingung": c, "kontext": kname,
                       "faithfulness": score, "aussagen": len(details), "gestuetzt": sum(1 for d in gueltig if d["urteil"]),
                       "unlesbar": len(details) - len(gueltig), "meta_verworfen": verworfen,
                       "sek": round(time.time() - t0, 1), "richter": a.richter, "quelle": "faith1200"})
        with open(det, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"id": qid, "bedingung": c, "kontext": kname, "kontext_ids": kontext_ids,
                                 "details": details}, ensure_ascii=False) + "\n")
        schreibe(out, zeilen)
        print(f"[{i}/{len(todo)}] {qid:>4} {c:5s} F={score!s:<6} ({sum(1 for d in gueltig if d['urteil'])}/{len(gueltig)} statements) {round(time.time()-t0,1)} s", flush=True)
    zusammenfassung(zeilen)


if __name__ == "__main__":
    main()
