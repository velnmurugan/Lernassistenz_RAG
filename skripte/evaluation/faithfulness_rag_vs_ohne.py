"""Faithfulness mit und ohne Retrieval (N100, Stand V11B).

Zweck: Wie viel jeder Antwort wird durch das Lernmaterial gestützt? Beide Antwortarten (mit Retrieval = V11B, ohne Retrieval =
Prompt O-v1) werden mit demselben Richter (mistral-nemo, J-v1) und derselben Funktion wie in ragas_auswertung.py gegen
DIESELBEN vier Textabschnitte geprüft, die das System für die Frage abgerufen hat. Quelle der Antworten und Abschnitte:
evaluationsdaten/vergleich_rag_RAGVGL-N100{F,B}-V11B-BEIDE7.csv (antwort_mit, antwort_ohne, quellen_mit).
Bewertet werden die 95 beantwortbaren Fragen (die 5 Ablehnungen entfallen). Ergebnis wird nach jeder Antwort gespeichert; ein
abgebrochener Lauf setzt beim nächsten Start fort. Nur Faithfulness (keine Answer/Context Relevance).

Start (aus ~/RAG, Umgebung pilot_rag):
  python skripte/evaluation/faithfulness_rag_vs_ohne.py            # alle 95 Fragen, beide Arme
  python skripte/evaluation/faithfulness_rag_vs_ohne.py --limit 3  # Probe: 3 Fragen, zeigt Sekunden je Antwort
  python skripte/evaluation/faithfulness_rag_vs_ohne.py --nur-zusammenfassung
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse, csv, math, os, time
from collections import defaultdict

import ragas_auswertung as ra
import rag_pipeline as rp

KB = "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json"
QUELLEN = [("F", "evaluationsdaten/vergleich_rag_RAGVGL-N100F-V11B-BEIDE7.csv"),
           ("B", "evaluationsdaten/vergleich_rag_RAGVGL-N100B-V11B-BEIDE7.csv")]
AUS = "evaluationsdaten/faithfulness_rag_vs_ohne_V11B.csv"
DET = "evaluationsdaten/faithfulness_rag_vs_ohne_V11B_details.csv"
ZUS = "evaluationsdaten/faithfulness_rag_vs_ohne_V11B_zusammenfassung.txt"
ALT = "evaluationsdaten/ragas_ergebnisse_N100_NACHT.csv"  # früherer Lauf (Kontrollwert für den Mit-RAG-Arm)
FELDER = ["id", "typ", "arm", "n_aussagen", "n_gestuetzt", "n_unlesbar", "n_meta_verworfen", "faithfulness"]
DET_FELDER = ["id", "arm", "aussage", "urteil", "begruendung"]


def lade_faelle(chunks):
    lookup = {c["id"]: c for c in chunks}
    faelle, uebersprungen = [], []
    for praefix, datei in QUELLEN:
        for z in csv.DictReader(open(datei, encoding="utf-8")):
            fid = f"{praefix}{z['nr']}"
            ids = [i.strip() for i in z["quellen_mit"].split(";") if i.strip()]
            if z["status_mit"] != "BEANTWORTET" or not ids:
                uebersprungen.append((fid, z["status_mit"] or "ohne Quellen"))
                continue
            fehlend = [i for i in ids if i not in lookup]
            if fehlend:
                raise SystemExit(f"ABBRUCH: Chunks fehlen in der Wissensbasis ({fid}): {fehlend}")
            faelle.append({"id": fid, "typ": z["typ"], "frage": z["frage"], "mit": z["antwort_mit"], "ohne": z["antwort_ohne"],
                           "kontext_chunks": [lookup[i] for i in ids]})
    return faelle, uebersprungen


def vorhanden():
    if not os.path.exists(AUS):
        return set()
    return {(r["id"], r["arm"]) for r in csv.DictReader(open(AUS, encoding="utf-8"))}


def binom_p(k, n):  # zweiseitiger exakter Vorzeichentest, p = 0,5
    if n == 0:
        return 1.0
    s = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * s)


def zusammenfassung():
    if not os.path.exists(AUS):
        print("Keine Ergebnisse vorhanden.")
        return
    zeilen = list(csv.DictReader(open(AUS, encoding="utf-8")))
    d = defaultdict(dict)
    typ = {}
    for r in zeilen:
        typ[r["id"]] = r["typ"]
        if r["faithfulness"] != "":
            d[r["id"]][r["arm"]] = float(r["faithfulness"])
    paare = {i: v for i, v in d.items() if "mit" in v and "ohne" in v}
    m = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    out = []
    out.append(f"Faithfulness (Anteil durch die vier abgerufenen Textabschnitte gestützter Aussagen), Richter {ra.JUDGE_MODELL_STANDARD}, Prompt {ra.PROMPT_VERSION}")
    out.append(f"Bewertete Antworten: mit Retrieval {sum('mit' in v for v in d.values())}, ohne Retrieval {sum('ohne' in v for v in d.values())}; Paare (beide bewertet): {len(paare)}")
    out.append(f"Mittelwert über die Paare:  mit Retrieval {m([v['mit'] for v in paare.values()]):.3f}   ohne Retrieval {m([v['ohne'] for v in paare.values()]):.3f}")
    besser = sum(v["mit"] > v["ohne"] for v in paare.values())
    gleich = sum(v["mit"] == v["ohne"] for v in paare.values())
    schlechter = sum(v["mit"] < v["ohne"] for v in paare.values())
    out.append(f"Paarvergleich: mit Retrieval höher bei {besser}, gleich bei {gleich}, niedriger bei {schlechter}; Vorzeichentest (ohne Gleiche) p = {binom_p(min(besser, schlechter), besser + schlechter):.4f}")
    nach = defaultdict(list)
    for i, v in paare.items():
        nach[typ[i]].append(v)
    out.append("Nach Fragetyp (n; mit / ohne):")
    for t, vs in sorted(nach.items()):
        out.append(f"  {t:12} n={len(vs):3}   {m([v['mit'] for v in vs]):.3f} / {m([v['ohne'] for v in vs]):.3f}")
    if os.path.exists(ALT):
        alt = [float(r["faithfulness"]) for r in csv.DictReader(open(ALT, encoding="utf-8"))
               if r["sitzungs_id"] == "RAGVGL-N100B-V11B-BEIDE7" and r["faithfulness"] != ""]
        neu = [v["mit"] for i, v in d.items() if i.startswith("B") and "mit" in v]
        if alt and neu:
            out.append(f"Kontrolle Mit-RAG-Arm, 30 Fragen des zweiten Teilsatzes: früherer Lauf {m(alt):.3f} (n={len(alt)}), dieser Lauf {m(neu):.3f} (n={len(neu)})")
    out.append("Hinweis: Entwicklungs-/Pilotfragen; Richter nicht an Handurteilen validiert; Rechenschritte werden teils als nicht gestützt gewertet.")
    text = "\n".join(out)
    print("\n" + text)
    open(ZUS, "w", encoding="utf-8").write(text + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="nur die ersten N Fragen (Probe)")
    ap.add_argument("--judge", default=ra.JUDGE_MODELL_STANDARD)
    ap.add_argument("--nur-zusammenfassung", action="store_true")
    args = ap.parse_args(argv)
    if args.nur_zusammenfassung:
        return zusammenfassung()
    if args.judge.split(":")[0] == rp.MODEL_NAME.split(":")[0]:
        raise SystemExit("ABBRUCH: Richter = Generator (Selbstbewertung).")
    chunks = rp.lade_wissensbasis(KB)
    faelle, uebersp = lade_faelle(chunks)
    print(f"Fragen bewertbar: {len(faelle)}; übersprungen (Ablehnung/ohne Quellen): {len(uebersp)} {[u[0] for u in uebersp]}", flush=True)
    if args.limit:
        faelle = faelle[:args.limit]
    fertig = vorhanden()
    neu_aus, neu_det = not os.path.exists(AUS), not os.path.exists(DET)
    gesamt = len(faelle) * 2
    erledigt = sum((f["id"], a) in fertig for f in faelle for a in ("mit", "ohne"))
    t_start, n_neu = time.time(), 0
    with open(AUS, "a", newline="", encoding="utf-8") as fa, open(DET, "a", newline="", encoding="utf-8") as fd:
        wa, wd = csv.DictWriter(fa, fieldnames=FELDER), csv.DictWriter(fd, fieldnames=DET_FELDER)
        if neu_aus: wa.writeheader()
        if neu_det: wd.writeheader()
        for f in faelle:
            for arm in ("mit", "ohne"):
                if (f["id"], arm) in fertig:
                    continue
                t0 = time.time()
                fall = {"frage": f["frage"], "hinweis": "", "erklaerung": "", "loesung": f[arm], "kontext_chunks": f["kontext_chunks"]}
                try:
                    score, details, verworfen = ra.berechne_faithfulness(fall, args.judge)
                except Exception as e:
                    print(f"{f['id']} {arm}: FEHLER {e}", flush=True)
                    continue
                n_ja = sum(x["urteil"] is True for x in details)
                n_un = sum(x["urteil"] is None for x in details)
                wa.writerow({"id": f["id"], "typ": f["typ"], "arm": arm, "n_aussagen": len(details), "n_gestuetzt": n_ja, "n_unlesbar": n_un,
                             "n_meta_verworfen": verworfen, "faithfulness": round(score, 4) if score is not None else ""})
                wd.writerows([{"id": f["id"], "arm": arm, "aussage": x["aussage"], "urteil": x["urteil"], "begruendung": x["begruendung"]} for x in details])
                fa.flush(); fd.flush()
                erledigt += 1; n_neu += 1
                rest = (time.time() - t_start) / n_neu * (gesamt - erledigt)
                print(f"{f['id']:5} {arm:5} F={'--' if score is None else f'{score:.2f}'} ({n_ja}/{len(details) - n_un})  {time.time() - t0:5.0f} s   "
                      f"[{erledigt}/{gesamt}, Rest ca. {rest / 60:.0f} min]", flush=True)
    zusammenfassung()


if __name__ == "__main__":
    main()
