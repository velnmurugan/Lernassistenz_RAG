#!/usr/bin/env python3
"""
teste_hinweis_waechter.py  (HG-R)  –  Wächter HG-v1 auf den 143 gespeicherten Hinweis-Situationen aus HD-V2, mit Rubrik P1-P6
---------------------------------------------------------------------------------------------------------------------------
Für jede der 143 Situationen (Versuch 1: 92, 2: 39, 3: 12) gilt der in HD-V2 gespeicherte Hinweis als Basis (= der von V11B
ausgelieferte Hinweis). Der Wächter HG-v1 wird auf genau diesen Hinweis angewandt (Entwurf = gespeicherter Hinweis, Neuschreiben mit
dem Prompt der Pipeline). So sind Basis und Wächter-Hinweis PAARWEISE vergleichbar (gleiche Frage, gleiche Vorgeschichte).
Rubrik P1-P6 (Richter mistral-nemo, T=0, Seed 42, wie im Dialogtest): Basis-Urteile aus HD-V2 werden wiederverwendet; geänderte
Hinweise werden neu beurteilt. Hinweise ohne Änderung erhalten das Urteil der Basis.

Ausgabe (evaluationsdaten/hinweis_waechter_<LABEL>_*):
  _paare.csv             alle 143 Situationen: Basis, Wächter-Hinweis, Protokoll, Rubrik beider Hinweise
  _zusammenfassung.txt   Anteile ja je Kriterium, gepaart besser/schlechter, Vorzeichentest, je Versuch, Ersatz-/Neuschreibrate
  _bogen.csv             BLIND, nur die geänderten Hinweise: Hinweis 1 / 2 in zufälliger Reihenfolge, Spalten zum Ausfüllen (English)
  _bogen_schluessel.csv  Schlüssel (welcher Text ist Basis) – erst nach der Handbewertung öffnen
  _zustand.json          Zwischenstand (Fortsetzung mit demselben Befehl)
Start (aus ~/RAG): python skripte/evaluation/teste_hinweis_waechter.py [--limit 5] [--richter mistral-nemo]
Dauer grob 30-60 min. Grenzen: Entwicklungsdaten; Prüfer des Wächters kappa <= 0.34; Richter ungeprüft -> Handbewertung entscheidet.
"""
import sys as _sys
import pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import argparse  # noqa: E402
import csv  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

import optimiere_hinweise as oh  # noqa: E402
import teste_hinweis_dialog as hd  # noqa: E402
import teste_hinweis_stabilitaet as hs  # noqa: E402
import hinweiswaechter as hw  # noqa: E402

rp = hd.rag_pipeline
LABEL = "HG-R"
ITEMS = ("P1", "P2", "P3", "P4", "P5", "P6")
WERT = {"ja": 2, "teilweise": 1, "nein": 0}


def rubrik(args, sz, hinweis):
    s = sz["s"]
    t = {"n": sz["n"]}
    roh = hd.llm(args.richter, hd.judge_prompt("hinweis", s, t, hinweis), {"temperature": 0, "seed": 42, "num_predict": 400})
    return hd.parse_judge(roh, hd.HINWEIS_ITEMS)


def phase_waechter(args, z, szl, pfad, t0):
    hd.stunde(t0, f"Phase 1/2: Wächter HG-v1 auf {len(szl)} Situationen (Prüfer {hw.pruefer_modell(rp)})")
    opt = dict(rp.GENERIERUNGS_OPTIONEN)
    for k, sz in enumerate(szl, 1):
        if sz["key"] in z["w"]:
            continue
        s, n = sz["s"], sz["n"]
        basis = sz["hinweis_b"].strip()
        verlauf = hd.verlauf_text(s, n - 1) if n > 1 else ""

        def neu(zusatz, sz=sz):
            return hs.erzeuge2(oh.prompt_basis(sz) + zusatz, sz["s"], opt)[0]

        z0 = time.time()
        r = hw.waechter(rp, s["frage"], s["loesung"], basis, verlauf, n, neu)
        z["w"][sz["key"]] = {"basis": basis, "waechter": r["hinweis"].strip(), "start": r["urteil_start"], "ende": r["urteil_ende"],
                             "neu": r["neu"], "ersatz": r["ersatz"], "genannt": r["genannt"]}
        hd.speichere(z, pfad)
        print(f"  [{k}/{len(szl)}] {sz['key']:<7} V{n} {r['urteil_start'] or '?':<9} -> {r['urteil_ende'] or '?':<9} neu={r['neu']} "
              f"ersatz={'ja' if r['ersatz'] else 'nein'} {'GEÄNDERT' if r['hinweis'].strip() != basis else ''} {time.time() - z0:.0f}s", flush=True)


def phase_rubrik(args, z, szl, pfad, t0):
    todo = []
    for sz in szl:
        w = z["w"].get(sz["key"])
        if not w:
            continue
        if sz["key"] not in z["rb"]:
            todo.append(sz)
    hd.stunde(t0, f"Phase 2/2: Rubrik P1-P6 durch {args.richter} ({len(todo)} Situationen)")
    for k, sz in enumerate(todo, 1):
        w = z["w"][sz["key"]]
        basis_urteil = {p: sz["urteile_b"].get(p, "") for p in ITEMS}
        if not any(basis_urteil.values()):  # Basis in HD-V2 nicht beurteilt -> jetzt beurteilen
            basis_urteil = {p: rubrik(args, sz, w["basis"]).get(p, "") for p in ITEMS}
        if w["waechter"] == w["basis"]:
            wae_urteil = dict(basis_urteil)
        else:
            u = rubrik(args, sz, w["waechter"])
            wae_urteil = {p: u.get(p, "") for p in ITEMS}
        z["rb"][sz["key"]] = {"basis": basis_urteil, "waechter": wae_urteil}
        if k % 10 == 0 or k == len(todo):
            hd.speichere(z, pfad)
            print(f"  [{k}/{len(todo)}] beurteilt", flush=True)
    hd.speichere(z, pfad)


def ausgabe(args, z, szl, t0):
    ED = Path("evaluationsdaten")
    base = ED / f"hinweis_waechter_{LABEL}{'-PILOT' if args.limit else ''}"
    zeilen = []
    for sz in szl:
        w, r = z["w"].get(sz["key"]), z["rb"].get(sz["key"])
        if not w or not r:
            continue
        zeile = {"key": sz["key"], "versuch": sz["n"], "frage": sz["s"]["frage"], "basis": w["basis"], "waechter": w["waechter"],
                 "geaendert": w["basis"] != w["waechter"], "pruefer_start": w["start"], "pruefer_ende": w["ende"],
                 "neu": w["neu"], "ersatz": w["ersatz"], "genannt": w["genannt"]}
        for p in ITEMS:
            zeile[f"B_{p}"], zeile[f"W_{p}"] = r["basis"].get(p, ""), r["waechter"].get(p, "")
        zeilen.append(zeile)
    if not zeilen:
        print("Keine Daten.")
        return
    with open(str(base) + "_paare.csv", "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()))
        wr.writeheader()
        wr.writerows(zeilen)

    n = len(zeilen)
    ch = [x for x in zeilen if x["geaendert"]]
    L = [f"Wächter HG-v1 auf den gespeicherten Hinweisen aus HD-V2 ({LABEL})  {time.strftime('%d.%m.%Y %H:%M')}",
         f"Situationen: {n} (Versuch 1: {sum(x['versuch'] == 1 for x in zeilen)}, 2: {sum(x['versuch'] == 2 for x in zeilen)}, 3: {sum(x['versuch'] == 3 for x in zeilen)}); "
         f"Prüfer {hw.pruefer_modell(rp)}/C2, Richter {args.richter}",
         "",
         f"Hinweis geändert: {len(ch)} von {n} ({len(ch) / n:.0%}); davon Ersatztext: {sum(x['ersatz'] for x in ch)}; "
         f"Prüfer-Urteil vor Eingriff: {dict(Counter(x['pruefer_start'] or '?' for x in zeilen))}",
         "Geändert je Versuch: " + ", ".join(f"V{v}: {sum(1 for x in ch if x['versuch'] == v)}/{sum(1 for x in zeilen if x['versuch'] == v)}" for v in (1, 2, 3)),
         "",
         "Rubrik (Richter): Anteil 'ja' / gepaart besser-schlechter (nur geänderte Hinweise zählen als Unterschied; Vorzeichentest zweiseitig)"]
    for p in ITEMS:
        ba = [x[f"B_{p}"] for x in zeilen if x[f"B_{p}"]]
        wa = [x[f"W_{p}"] for x in zeilen if x[f"W_{p}"]]
        bess = sum(1 for x in zeilen if x[f"B_{p}"] and x[f"W_{p}"] and WERT[x[f"W_{p}"]] > WERT[x[f"B_{p}"]])
        schl = sum(1 for x in zeilen if x[f"B_{p}"] and x[f"W_{p}"] and WERT[x[f"W_{p}"]] < WERT[x[f"B_{p}"]])
        L.append(f"  {p} {hd.HINWEIS_ITEMS[p].split(':')[0]:<14} Basis {sum(v == 'ja' for v in ba) / max(1, len(ba)):.0%}  Wächter {sum(v == 'ja' for v in wa) / max(1, len(wa)):.0%}"
                 f"   besser {bess} / schlechter {schl}  p={oh.vorzeichentest(bess, schl):.2f}")
    L += ["", "Hinweis zur Lesart: Der Richter (mistral-nemo) ist ungeprüft; der Wächter-Prüfer hatte in HO-V1 kappa 0.28-0.34. Das ist Orientierung.",
          f"Verbindlich ist die Handbewertung des blinden Bogens ({len(ch)} geänderte Hinweise)."]
    Path(str(base) + "_zusammenfassung.txt").write_text("\n".join(L), encoding="utf-8")

    # Blinder Bogen (English)
    rnd = random.Random(args.seed)
    bogen, schl_ = [], []
    for k, x in enumerate(ch, 1):
        tausch = rnd.random() < 0.5
        h1, h2 = (x["waechter"], x["basis"]) if tausch else (x["basis"], x["waechter"])
        sz = next(s for s in szl if s["key"] == x["key"])
        bogen.append({"row": k, "attempt": x["versuch"], "question": x["frage"], "reference_solution": sz["s"]["loesung"],
                      "history_before_this_hint": hd.verlauf_text(sz["s"], sz["n"] - 1) if sz["n"] > 1 else "(first hint)",
                      "hint_1": h1, "hint_2": h2,
                      "P1_hint_1 (yes/partly/no = does NOT leak)": "", "P1_hint_2 (yes/partly/no = does NOT leak)": "",
                      "leaks_less (1/2/same)": "", "better_help (1/2/same)": "", "remark": ""})
        schl_.append({"row": k, "key": x["key"], "hint_1": "guard" if tausch else "baseline", "hint_2": "baseline" if tausch else "guard"})
    for name, felder, rows in (("_bogen.csv", list(bogen[0].keys()) if bogen else ["row"], bogen),
                               ("_bogen_schluessel.csv", ["row", "key", "hint_1", "hint_2"], schl_)):
        with open(str(base) + name, "w", encoding="utf-8-sig", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=felder)
            wr.writeheader()
            wr.writerows(rows)
    print("\n".join(L))
    print(f"\nDateien: {base}_paare.csv, _zusammenfassung.txt, _bogen.csv ({len(ch)} Zeilen, blind), _bogen_schluessel.csv")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--richter", default="mistral-nemo")
    ap.add_argument("--limit", type=int, default=0, help="Pilot: nur so viele Situationen")
    ap.add_argument("--seed", type=int, default=2028)
    args = ap.parse_args()
    t0 = time.time()
    if not hw.aktiv():
        import os
        os.environ["LERNASSISTENT_HG"] = "HG-v1"
    rp.RRF_K = 5
    szl = oh.lade_szenarien("HD-V2")
    if args.limit:
        schritt = max(1, len(szl) // args.limit)
        szl = szl[::schritt][: args.limit]
    hd.pruefe_modelle(rp.MODEL_NAME, args.richter)
    Path("evaluationsdaten").mkdir(exist_ok=True)
    pfad = Path(f"evaluationsdaten/hinweis_waechter_{LABEL}{'-PILOT' if args.limit else ''}_zustand.json")
    z = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {"w": {}, "rb": {}}
    print(f"{len(szl)} Situationen aus HD-V2, Wächter {hw.VERSION}, Richter {args.richter}")
    phase_waechter(args, z, szl, pfad, t0)
    phase_rubrik(args, z, szl, pfad, t0)
    ausgabe(args, z, szl, t0)
    hd.stunde(t0, "Fertig")


if __name__ == "__main__":
    main()
