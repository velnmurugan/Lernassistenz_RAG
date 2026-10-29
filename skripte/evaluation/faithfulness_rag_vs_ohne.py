"""Faithfulness mit und ohne Retrieval (N100).

Zweck: Wie viel jeder Antwort wird durch das Lernmaterial gestützt? Beide Antwortarten (mit Retrieval, ohne Retrieval = Prompt O-v1)
werden mit demselben Richter (mistral-nemo, J-v1) und derselben Funktion wie in ragas_auswertung.py gegen DIESELBEN vier Textabschnitte
geprüft, die das System für die Frage abgerufen hat. Quelle der Antworten und Abschnitte:
evaluationsdaten/vergleich_rag_RAGVGL-N100{F,B}-<LABEL>-BEIDE7.csv (antwort_mit, antwort_ohne, quellen_mit).
Bewertet werden die beantwortbaren Fragen (Ablehnungen entfallen). Ergebnis wird nach jeder Antwort gespeichert; ein abgebrochener Lauf
setzt beim nächsten Start fort. Nur Faithfulness (keine Answer/Context Relevance).

Wiederverwendung: Ist bei einem anderen LABEL (z. B. V19AB) Antworttext UND Quellenliste identisch mit dem Basislauf (--basis, Standard V11B)
und hat der Basislauf dafür einen Wert, wird dieser übernommen (Richter und Eingabe sind identisch, T = 0). Nur geänderte Antworten werden neu
bewertet. Kontrolle: --kontrolle N bewertet N übernommene Werte neu und meldet Abweichungen (Richter reproduzierbar?).

Start (aus ~/RAG, Umgebung pilot_rag):
  python skripte/evaluation/faithfulness_rag_vs_ohne.py                              # V11B, alle Fragen, beide Arme
  python skripte/evaluation/faithfulness_rag_vs_ohne.py --label V19AB --basis V11B   # nur geänderte Antworten neu
  python skripte/evaluation/faithfulness_rag_vs_ohne.py --limit 3                    # Probe
  python skripte/evaluation/faithfulness_rag_vs_ohne.py --label V19AB --nur-zusammenfassung
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse, csv, math, os, time
from collections import defaultdict

import ragas_auswertung as ra
import rag_pipeline as rp

csv.field_size_limit(10 ** 9)
KB = "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json"
ALT = "evaluationsdaten/ragas_ergebnisse_N100_NACHT.csv"  # früherer Lauf (Kontrollwert, nur für V11B)
FELDER = ["id", "typ", "arm", "n_aussagen", "n_gestuetzt", "n_unlesbar", "n_meta_verworfen", "faithfulness", "herkunft"]
DET_FELDER = ["id", "arm", "aussage", "urteil", "begruendung"]


def pfade(label):
    quellen = [("F", f"evaluationsdaten/vergleich_rag_RAGVGL-N100F-{label}-BEIDE7.csv"),
               ("B", f"evaluationsdaten/vergleich_rag_RAGVGL-N100B-{label}-BEIDE7.csv")]
    basis = f"evaluationsdaten/faithfulness_rag_vs_ohne_{label}"
    return quellen, basis + ".csv", basis + "_details.csv", basis + "_zusammenfassung.txt", basis + "_kontrolle.csv"


def lade_faelle(label, lookup=None):
    quellen = pfade(label)[0]
    faelle, uebersprungen = [], []
    for praefix, datei in quellen:
        for z in csv.DictReader(open(datei, encoding="utf-8")):
            fid = f"{praefix}{z['nr']}"
            ids = [i.strip() for i in z["quellen_mit"].split(";") if i.strip()]
            if z["status_mit"] != "BEANTWORTET" or not ids:
                uebersprungen.append((fid, z["status_mit"] or "ohne Quellen"))
                continue
            if lookup is not None:
                fehlend = [i for i in ids if i not in lookup]
                if fehlend:
                    raise SystemExit(f"ABBRUCH: Chunks fehlen in der Wissensbasis ({fid}): {fehlend}")
            faelle.append({"id": fid, "typ": z["typ"], "frage": z["frage"], "mit": z["antwort_mit"], "ohne": z["antwort_ohne"],
                           "ids": ids, "kontext_chunks": [lookup[i] for i in ids] if lookup is not None else []})
    return faelle, uebersprungen


def lade_werte(aus):
    if not os.path.exists(aus):
        return {}
    return {(r["id"], r["arm"]): r for r in csv.DictReader(open(aus, encoding="utf-8"))}


def binom_p(k, n):  # zweiseitiger exakter Vorzeichentest, p = 0,5
    if n == 0:
        return 1.0
    s = sum(math.comb(n, i) for i in range(0, min(k, n - k) + 1)) / 2 ** n
    return min(1.0, 2 * s)


def zusammenfassung(label):
    _, aus, _, zus, _ = pfade(label)
    if not os.path.exists(aus):
        print("Keine Ergebnisse vorhanden.")
        return
    zeilen = list(csv.DictReader(open(aus, encoding="utf-8")))
    d = defaultdict(dict)
    typ = {}
    for r in zeilen:
        typ[r["id"]] = r["typ"]
        if r["faithfulness"] != "":
            d[r["id"]][r["arm"]] = float(r["faithfulness"])
    paare = {i: v for i, v in d.items() if "mit" in v and "ohne" in v}
    m = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    neu = sum(r.get("herkunft", "neu") == "neu" for r in zeilen)
    out = [f"Faithfulness {label} (Anteil durch die vier abgerufenen Textabschnitte gestützter Aussagen), Richter {ra.JUDGE_MODELL_STANDARD}, Prompt {ra.PROMPT_VERSION}",
           f"Bewertete Antworten: mit Retrieval {sum('mit' in v for v in d.values())}, ohne Retrieval {sum('ohne' in v for v in d.values())}; Paare (beide bewertet): {len(paare)}",
           f"Davon neu bewertet: {neu} von {len(zeilen)} Werten; übernommen aus dem Basislauf: {len(zeilen) - neu}",
           f"Mittelwert über die Paare:  mit Retrieval {m([v['mit'] for v in paare.values()]):.3f}   ohne Retrieval {m([v['ohne'] for v in paare.values()]):.3f}"]
    besser = sum(v["mit"] > v["ohne"] for v in paare.values())
    gleich = sum(v["mit"] == v["ohne"] for v in paare.values())
    schlechter = sum(v["mit"] < v["ohne"] for v in paare.values())
    out.append(f"Paarvergleich: mit Retrieval höher bei {besser}, gleich bei {gleich}, niedriger bei {schlechter}; Vorzeichentest (ohne Gleiche) p = {binom_p(min(besser, schlechter), besser + schlechter):.4g}")
    nach = defaultdict(list)
    for i, v in paare.items():
        nach[typ[i]].append(v)
    out.append("Nach Fragetyp (n; mit / ohne):")
    for t, vs in sorted(nach.items()):
        out.append(f"  {t:12} n={len(vs):3}   {m([v['mit'] for v in vs]):.3f} / {m([v['ohne'] for v in vs]):.3f}")
    ohne_rechn = [v for i, v in paare.items() if typ[i] != "rechnung"]
    out.append(f"Ohne Rechenfragen (n={len(ohne_rechn)}): mit {m([v['mit'] for v in ohne_rechn]):.3f} / ohne {m([v['ohne'] for v in ohne_rechn]):.3f}")
    kontrolle = pfade(label)[4]
    if os.path.exists(kontrolle):
        k = list(csv.DictReader(open(kontrolle, encoding="utf-8")))
        abw = [r for r in k if abs(float(r["neu"]) - float(r["alt"])) > 1e-9]
        out.append(f"Kontrolle (übernommene Werte neu bewertet): {len(k)} geprüft, {len(abw)} abweichend" + ("" if not abw else f" ({', '.join(r['id'] + '/' + r['arm'] for r in abw)})"))
    if label == "V11B" and os.path.exists(ALT):
        alt = [float(r["faithfulness"]) for r in csv.DictReader(open(ALT, encoding="utf-8"))
               if r["sitzungs_id"] == "RAGVGL-N100B-V11B-BEIDE7" and r["faithfulness"] != ""]
        neu_b = [v["mit"] for i, v in d.items() if i.startswith("B") and "mit" in v]
        if alt and neu_b:
            out.append(f"Kontrolle Mit-RAG-Arm, 30 Fragen des zweiten Teilsatzes: früherer Lauf {m(alt):.3f} (n={len(alt)}), dieser Lauf {m(neu_b):.3f} (n={len(neu_b)})")
    out.append("Hinweis: Entwicklungs-/Pilotfragen; Richter nicht an Handurteilen validiert; Rechenschritte werden teils als nicht gestützt gewertet.")
    text = "\n".join(out)
    print("\n" + text)
    open(zus, "w", encoding="utf-8").write(text + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="V11B", help="Lauf, z. B. V11B oder V19AB")
    ap.add_argument("--basis", default=None, help="Basislauf für die Wiederverwendung identischer Antworten (z. B. V11B)")
    ap.add_argument("--kontrolle", type=int, default=5, help="so viele übernommene Werte je Arm zur Kontrolle neu bewerten")
    ap.add_argument("--limit", type=int, default=None, help="nur die ersten N Fragen (Probe)")
    ap.add_argument("--judge", default=ra.JUDGE_MODELL_STANDARD)
    ap.add_argument("--nur-zusammenfassung", action="store_true")
    args = ap.parse_args(argv)
    if args.nur_zusammenfassung:
        return zusammenfassung(args.label)
    if args.judge.split(":")[0] == rp.MODEL_NAME.split(":")[0]:
        raise SystemExit("ABBRUCH: Richter = Generator (Selbstbewertung).")
    _, AUS, DET, _, KON = pfade(args.label)
    chunks = rp.lade_wissensbasis(KB)
    lookup = {c["id"]: c for c in chunks}
    faelle, uebersp = lade_faelle(args.label, lookup)
    print(f"[{args.label}] Fragen bewertbar: {len(faelle)}; übersprungen (Ablehnung/ohne Quellen): {len(uebersp)} {[u[0] for u in uebersp]}", flush=True)
    basis_faelle, basis_werte = {}, {}
    if args.basis and args.basis != args.label:
        bf, _ = lade_faelle(args.basis)
        basis_faelle = {f["id"]: f for f in bf}
        basis_werte = lade_werte(pfade(args.basis)[1])
        print(f"Basislauf {args.basis}: {len(basis_faelle)} Fälle, {len(basis_werte)} Werte (identische Antworten werden übernommen)", flush=True)
    if args.limit:
        faelle = faelle[:args.limit]
    if os.path.exists(AUS):  # älteres Format (ohne Spalte herkunft) ergänzen
        zl = list(csv.DictReader(open(AUS, encoding="utf-8")))
        if zl and "herkunft" not in zl[0]:
            with open(AUS, "w", newline="", encoding="utf-8") as fo:
                wo = csv.DictWriter(fo, fieldnames=FELDER); wo.writeheader()
                for z in zl:
                    wo.writerow({k: z.get(k, "") for k in FELDER} | {"herkunft": "neu"})
    fertig = set(lade_werte(AUS))
    neu_aus, neu_det = not os.path.exists(AUS), not os.path.exists(DET)
    gesamt = len(faelle) * 2
    erledigt = sum((f["id"], a) in fertig for f in faelle for a in ("mit", "ohne"))
    t_start, n_neu = time.time(), 0
    uebernommen = []   # (fall, arm) für die Kontrolle

    def bewerte(f, arm):
        fall = {"frage": f["frage"], "hinweis": "", "erklaerung": "", "loesung": f[arm], "kontext_chunks": f["kontext_chunks"]}
        return ra.berechne_faithfulness(fall, args.judge)

    with open(AUS, "a", newline="", encoding="utf-8") as fa, open(DET, "a", newline="", encoding="utf-8") as fd:
        wa, wd = csv.DictWriter(fa, fieldnames=FELDER), csv.DictWriter(fd, fieldnames=DET_FELDER)
        if neu_aus: wa.writeheader()
        if neu_det: wd.writeheader()
        for f in faelle:
            for arm in ("mit", "ohne"):
                if (f["id"], arm) in fertig:
                    continue
                b = basis_faelle.get(f["id"])
                bw = basis_werte.get((f["id"], arm))
                if b and bw and bw["faithfulness"] != "" and b[arm] == f[arm] and b["ids"] == f["ids"]:
                    wa.writerow({**{k: bw.get(k, "") for k in FELDER if k != "herkunft"}, "id": f["id"], "typ": f["typ"], "arm": arm,
                                 "herkunft": f"übernommen aus {args.basis}"})
                    fa.flush(); erledigt += 1
                    uebernommen.append((f, arm, float(bw["faithfulness"])))
                    continue
                t0 = time.time()
                try:
                    score, details, verworfen = bewerte(f, arm)
                except Exception as e:
                    print(f"{f['id']} {arm}: FEHLER {e}", flush=True)
                    continue
                n_ja = sum(x["urteil"] is True for x in details)
                n_un = sum(x["urteil"] is None for x in details)
                wa.writerow({"id": f["id"], "typ": f["typ"], "arm": arm, "n_aussagen": len(details), "n_gestuetzt": n_ja, "n_unlesbar": n_un,
                             "n_meta_verworfen": verworfen, "faithfulness": round(score, 4) if score is not None else "", "herkunft": "neu"})
                wd.writerows([{"id": f["id"], "arm": arm, "aussage": x["aussage"], "urteil": x["urteil"], "begruendung": x["begruendung"]} for x in details])
                fa.flush(); fd.flush()
                erledigt += 1; n_neu += 1
                rest = (time.time() - t_start) / n_neu * (gesamt - erledigt) if n_neu else 0
                print(f"{f['id']:5} {arm:5} F={'--' if score is None else f'{score:.2f}'} ({n_ja}/{len(details) - n_un})  {time.time() - t0:5.0f} s   "
                      f"[{erledigt}/{gesamt}, Rest max. ca. {rest / 60:.0f} min]", flush=True)
    print(f"Übernommen aus {args.basis}: {len(uebernommen)}; neu bewertet: {n_neu}", flush=True)
    # Kontrolle: einige übernommene Werte neu bewerten (Richter reproduzierbar?)
    if uebernommen and args.kontrolle > 0 and not os.path.exists(KON):
        schritt = max(1, len(uebernommen) // args.kontrolle)
        auswahl = uebernommen[::schritt][:args.kontrolle]
        with open(KON, "w", newline="", encoding="utf-8") as fk:
            wk = csv.DictWriter(fk, fieldnames=["id", "arm", "alt", "neu"]); wk.writeheader()
            for f, arm, alt in auswahl:
                try:
                    score, _, _ = bewerte(f, arm)
                except Exception as e:
                    print(f"Kontrolle {f['id']} {arm}: FEHLER {e}", flush=True); continue
                if score is None:
                    continue
                wk.writerow({"id": f["id"], "arm": arm, "alt": alt, "neu": round(score, 4)}); fk.flush()
                print(f"Kontrolle {f['id']:5} {arm:5} übernommen {alt:.4f}  neu {score:.4f}  {'OK' if abs(score - alt) < 1e-3 else 'ABWEICHUNG'}", flush=True)
    zusammenfassung(args.label)


if __name__ == "__main__":
    main()
