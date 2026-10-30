"""Modellvergleich N100 (Konfiguration V11B, nur das Generator-Modell wechselt): Kennzahlen je Modell und Antwortbogen zur Bewertung.
Aufruf: python skripte/evaluation/modell_kennzahlen.py V11BQWEN4B V11BGEMMA12 [V11BGPTOSS20] [--ref V11B]
Ausgabe: evaluationsdaten/modellvergleich_N100_kennzahlen.md   und   evaluationsdaten/modellvergleich_N100_antworten.csv (Antwort je Modell, Spalten hand_* leer)."""
import csv, os, re, sys, argparse, statistics, collections

csv.field_size_limit(10 ** 9)
DENK = re.compile(r"<think>|</think>|\b(Warte|Moment mal|Hmm+|Okay, so|Let me|Wait,|Entscheidung:|Korrektur\*)", re.I)
DE = set("der die das und ist nicht mit von zu den dem ein eine einer auf für wird werden sich als auch bei oder wenn dass durch wie".split())
EN = set("the and is of to in that for with are this which be by as it from not or an".split())


def lade(label):
    d = {}
    for p in "FB":
        f = f"evaluationsdaten/vergleich_rag_RAGVGL-N100{p}-{label}-BEIDE7.csv"
        if not os.path.exists(f):
            raise SystemExit(f"FEHLT: {f}")
        for r in csv.DictReader(open(f, encoding="utf-8")):
            d[p + r["nr"]] = r
    return d


def deutsch(t):
    w = re.findall(r"[a-zäöüß]+", (t or "").lower())
    return sum(x in DE for x in w) >= sum(x in EN for x in w) if w else True


def med(xs):
    xs = [float(x) for x in xs if x not in ("", None)]
    return statistics.median(xs) if xs else float("nan")


def zeile(l, d):
    n = len(d)
    out = {}
    for arm in ("mit", "ohne"):
        a = [r[f"antwort_{arm}"] for r in d.values()]
        out[arm] = dict(fehler=sum(x.startswith("FEHLER") for x in a), leer=sum(not x.strip() for x in a),
                        denk=sum(bool(DENK.search(x)) for x in a), de=sum(deutsch(x) for x in a),
                        laenge=statistics.median(len(x) for x in a), sek=med(r[f"sek_{arm}"] for r in d.values()),
                        std=sum(float(r[f"sek_{arm}"] or 0) for r in d.values()) / 3600)
    st = collections.Counter(r["status_mit"] for r in d.values())
    aus = [r for r in d.values() if r["typ"] == "ausserhalb"]
    abg = sum(r["status_mit"] in ("NICHT_IM_MATERIAL", "GATE") for r in aus)
    inb = [r for r in d.values() if r["typ"] != "ausserhalb"]
    zu_unrecht = sum(r["status_mit"] in ("NICHT_IM_MATERIAL", "GATE") for r in inb)
    rp = collections.Counter(r.get("rechen_pruefung_mit", "") or "-" for r in d.values())
    return n, out, st, (abg, len(aus)), (zu_unrecht, len(inb)), rp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("labels", nargs="+")
    ap.add_argument("--ref", default="V11B")
    a = ap.parse_args()
    alle = {a.ref: lade(a.ref)}
    for l in a.labels:
        alle[l] = lade(l)
    z = {l: zeile(l, d) for l, d in alle.items()}
    M = ["# N100: Modellvergleich bei gleicher Pipeline-Konfiguration (V11B)", "",
         "Nur das Generator-Modell wechselt (T = 0, Seed 42). Referenz: " + a.ref + " (qwen3.5:9b). Kennzahlen sind formal (Status, Format, Zeit); die Richtigkeit wird per Handbewertung festgelegt.", "",
         "## Mit Retrieval", "| Lauf | Fragen | beantwortet | Ablehnung | zu Recht abgelehnt (außerhalb) | zu Unrecht abgelehnt | FEHLER | Denkreste | deutsch | Median Zeichen | Median s | Gesamt h |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for l, (n, o, st, (abg, na), (zu, ni), rp) in z.items():
        m = o["mit"]
        M.append(f"| {l} | {n} | {st.get('BEANTWORTET', 0)} | {st.get('NICHT_IM_MATERIAL', 0) + st.get('GATE', 0)} | {abg}/{na} | {zu}/{ni} | {m['fehler']} | {m['denk']} | {m['de']} | {m['laenge']:.0f} | {m['sek']:.0f} | {m['std']:.2f} |")
    M += ["", "## Ohne Retrieval", "| Lauf | FEHLER | Denkreste | deutsch | Median Zeichen | Median s | Gesamt h |", "|---|---|---|---|---|---|---|"]
    for l, (n, o, *_r) in z.items():
        m = o["ohne"]
        M.append(f"| {l} | {m['fehler']} | {m['denk']} | {m['de']} | {m['laenge']:.0f} | {m['sek']:.0f} | {m['std']:.2f} |")
    stati = sorted({k for v in z.values() for k in v[5]})
    M += ["", "## Rechenprüfung (RP-v5, Arm mit Retrieval)", "| Lauf | " + " | ".join(stati) + " |", "|---|" + "---|" * len(stati)]
    for l, v in z.items():
        M.append(f"| {l} | " + " | ".join(str(v[5].get(s, 0)) for s in stati) + " |")
    R = alle[a.ref]
    M += ["", "## Übereinstimmung mit der Referenz (Status)"]
    for l in a.labels:
        d = alle[l]
        gl = sum(d[k]["status_mit"] == R[k]["status_mit"] for k in R if k in d)
        M.append(f"- {l}: gleicher Status wie {a.ref} bei {gl} von {len(R)} Fragen.")
    M += ["", "Hinweis: Entwicklungs- und Pilotfragen; keine Evidenz für den Beitrag ohne unabhängigen Satz."]
    open("evaluationsdaten/modellvergleich_N100_kennzahlen.md", "w", encoding="utf-8").write("\n".join(M) + "\n")
    print("\n".join(M))
    with open("evaluationsdaten/modellvergleich_N100_antworten.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        kopf = ["id", "typ", "frage", "referenz", "hand_ref"]
        for l in [a.ref] + a.labels:
            kopf += [f"status_{l}", f"antwort_mit_{l}", f"hand_{l} (KORREKT/TEILWEISE/FALSCH)"]
        w.writerow(kopf)
        for k in sorted(R, key=lambda x: (x[0], int(re.sub(r"\D", "", x) or 0))):
            r = R[k]
            zl = [k, r["typ"], r["frage"], r["referenz"], r.get("hand_mit", "")]
            for l in [a.ref] + a.labels:
                x = alle[l].get(k, {})
                zl += [x.get("status_mit", ""), x.get("antwort_mit", ""), r.get("hand_mit", "") if l == a.ref else ""]
            w.writerow(zl)
    print("Antwortbogen: evaluationsdaten/modellvergleich_N100_antworten.csv")


if __name__ == "__main__":
    main()
