"""Vergleich von N100-Läufen (mit Retrieval) gegen den Referenzlauf (Standard V11B).

Eingabe: evaluationsdaten/vergleich_rag_RAGVGL-N100{F,B}-<LABEL>-BEIDE7.csv je Lauf.
Ausgabe: evaluationsdaten/vergleich_laeufe_N100_<REF>_<L1>_<L2>.md  (Bericht)
         evaluationsdaten/aenderungen_N100_<LABEL>_gegen_<REF>.csv   (geänderte Antworten zur Handbewertung; Spalten hand_neu leer)
Start: python skripte/evaluation/vergleich_laeufe_n100.py V19AUS V19AB [--ref V11B]
"""
import csv, sys, os, re, argparse, statistics, collections

csv.field_size_limit(10 ** 9)


def lade(label):
    d = {}
    for p, f in (("F", f"evaluationsdaten/vergleich_rag_RAGVGL-N100F-{label}-BEIDE7.csv"),
                 ("B", f"evaluationsdaten/vergleich_rag_RAGVGL-N100B-{label}-BEIDE7.csv")):
        if not os.path.exists(f):
            raise SystemExit(f"FEHLT: {f}")
        for r in csv.DictReader(open(f, encoding="utf-8")):
            d[p + r["nr"]] = r
    return d


def norm(t):
    return re.sub(r"\s+", " ", (t or "").strip())


def med(xs):
    xs = [float(x) for x in xs if x not in ("", None)]
    return statistics.median(xs) if xs else float("nan")


def kennzahlen(d):
    st = collections.Counter(r["status_mit"] for r in d.values())
    rp = collections.Counter(r.get("rechen_pruefung_mit", "") or "-" for r in d.values())
    hand = collections.Counter((r.get("hand_mit") or "-") for r in d.values())
    return st, rp, hand


def bericht(ref, labels, aus_md, aenderungs_pfad):
    R = lade(ref)
    out = [f"# N100: Vergleich der Läufe mit Retrieval gegen {ref}", ""]
    out.append(f"Fragen im Referenzlauf: {len(R)}. Alle Läufe T = 0, Seed 42; unveränderte Pipeline-Teile liefern identische Antworten.")
    out.append("")
    out.append("## Kennzahlen")
    out.append("| Lauf | beantwortet | NICHT_IM_MATERIAL | GATE/andere | Median s (mit) | Median s (ohne) |")
    out.append("|---|---|---|---|---|---|")
    alle = {ref: R}
    for l in labels:
        alle[l] = lade(l)
    for l, d in alle.items():
        st, _, _ = kennzahlen(d)
        andere = sum(v for k, v in st.items() if k not in ("BEANTWORTET", "NICHT_IM_MATERIAL"))
        out.append(f"| {l} | {st.get('BEANTWORTET', 0)} | {st.get('NICHT_IM_MATERIAL', 0)} | {andere} | {med(r['sek_mit'] for r in d.values()):.0f} | {med(r['sek_ohne'] for r in d.values()):.0f} |")
    out.append("")
    out.append("## Rechenprüfung (Status, Arm mit Retrieval)")
    stati = sorted({k for d in alle.values() for k in kennzahlen(d)[1]})
    out.append("| Lauf | " + " | ".join(stati) + " |")
    out.append("|---|" + "---|" * len(stati))
    for l, d in alle.items():
        rp = kennzahlen(d)[1]
        out.append(f"| {l} | " + " | ".join(str(rp.get(s, 0)) for s in stati) + " |")
    out.append("")
    # Ablehnungen: welche Fragen
    out.append("## Ablehnungen (NICHT_IM_MATERIAL)")
    for l, d in alle.items():
        ids = sorted(k for k, r in d.items() if r["status_mit"] == "NICHT_IM_MATERIAL")
        out.append(f"- {l}: {len(ids)}: {', '.join(ids) if ids else '-'}")
    out.append("")
    # Ohne-RAG-Arm identisch?
    for l in labels:
        d = alle[l]
        gl = sum(norm(d[k]["antwort_ohne"]) == norm(R[k]["antwort_ohne"]) for k in R if k in d)
        out.append(f"- Arm ohne Retrieval {l} gegenüber {ref}: {gl} von {len(R)} Antworten identisch (Kontrolle der Reproduzierbarkeit).")
    out.append("")
    # Änderungen je Lauf
    for l in labels:
        d = alle[l]
        gleich, geaendert, status_wechsel = 0, [], []
        for k in sorted(R, key=lambda x: (x[0], int(re.sub(r"\D", "", x) or 0))):
            if k not in d:
                continue
            if norm(d[k]["antwort_mit"]) == norm(R[k]["antwort_mit"]) and d[k]["status_mit"] == R[k]["status_mit"]:
                gleich += 1
            else:
                geaendert.append(k)
                if d[k]["status_mit"] != R[k]["status_mit"]:
                    status_wechsel.append(k)
        out.append(f"## {l} gegenüber {ref}")
        out.append(f"Identische Antworten (mit Retrieval): {gleich} von {len(R)}; geändert: {len(geaendert)}; davon Statuswechsel: {len(status_wechsel)} ({', '.join(status_wechsel) or '-'}).")
        # Handbewertung des Referenzlaufs für geänderte Fragen
        hr = collections.Counter((R[k].get("hand_mit") or "-") for k in geaendert)
        out.append(f"Handurteil des Referenzlaufs bei den geänderten Fragen: {dict(hr)}")
        out.append("")
        out.append("| Frage | Typ | Referenz: Urteil | Rechenprüfung ref → neu | Quellen gleich |")
        out.append("|---|---|---|---|---|")
        pfad = aenderungs_pfad.format(label=l, ref=ref)
        with open(pfad, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["id", "typ", "frage", "referenz", "hand_ref", "antwort_ref", "antwort_neu", "status_ref", "status_neu",
                        "rechenpruefung_ref", "rechenpruefung_neu", "quellen_gleich", "hand_neu (KORREKT/TEILWEISE/FALSCH, leer lassen)"])
            for k in geaendert:
                a, b = R[k], d[k]
                qg = "ja" if (a["quellen_mit"] == b["quellen_mit"]) else "nein"
                w.writerow([k, a["typ"], a["frage"], a["referenz"], a.get("hand_mit", ""), a["antwort_mit"], b["antwort_mit"], a["status_mit"], b["status_mit"],
                            a.get("rechen_pruefung_mit", ""), b.get("rechen_pruefung_mit", ""), qg, ""])
                out.append(f"| {k} | {a['typ']} | {a.get('hand_mit') or '-'} | {a.get('rechen_pruefung_mit') or '-'} → {b.get('rechen_pruefung_mit') or '-'} | {qg} |")
        out.append("")
        out.append(f"Zur Handbewertung: {pfad}")
        out.append("")
    # direkter Vergleich der Läufe untereinander
    if len(labels) == 2:
        a, b = alle[labels[0]], alle[labels[1]]
        unt = [k for k in R if k in a and k in b and norm(a[k]["antwort_mit"]) != norm(b[k]["antwort_mit"])]
        out.append(f"## {labels[0]} gegen {labels[1]}: {len(unt)} Fragen mit unterschiedlicher Antwort: {', '.join(sorted(unt)) or '-'}")
        out.append("")
    out.append("Hinweis: Skript wertet nur Gleichheit und Status; ob eine geänderte Antwort besser oder schlechter ist, entscheidet die Handbewertung (hand_neu).")
    open(aus_md, "w", encoding="utf-8").write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--ref", default="V11B")
    a = ap.parse_args()
    bericht(a.ref, a.labels, f"evaluationsdaten/vergleich_laeufe_N100_{a.ref}_{'_'.join(a.labels)}.md",
            "evaluationsdaten/aenderungen_N100_{label}_gegen_{ref}.csv")
