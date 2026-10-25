"""Vergleicht N100-Läufe mit V11B (mit RAG). Nutzung (aus ~/RAG): python skripte/evaluation/vergleiche_n100_laeufe.py V11B V13A [V13B]
Ausgabe: evaluationsdaten/n100_vergleich_<Labels>.csv + Konsole. Bewertung V11B = Vels Endbewertung (evaluationsdaten/n100_v11b_bewertung.csv).
Neue Läufe sind NICHT bewertet: Spalte 'aenderung' zeigt nur, wo sich Antwort/Status geändert hat -> nur diese Fragen von Hand bewerten."""
import sys, pathlib, re
import pandas as pd

D = pathlib.Path("evaluationsdaten")
labels = sys.argv[1:] or ["V11B", "V13A"]

def lade(label):
    teile = []
    for k, pre in (("F", "F"), ("B", "B")):
        p = D / f"vergleich_rag_RAGVGL-N100{k}-{label}-BEIDE7.csv"
        if not p.exists():
            print(f"[fehlt] {p}"); continue
        d = pd.read_csv(p); d["id"] = pre + d["nr"].astype(str); teile.append(d)
    if not teile: return None
    return pd.concat(teile).set_index("id")

def norm(t):
    return re.sub(r"\s+", " ", str(t)).strip()

basis = lade(labels[0])
bew = pd.read_csv(D / "n100_v11b_bewertung.csv").set_index("id")["bewertung_v11b"]
if basis is None: sys.exit("Basislauf fehlt")
aus = pd.DataFrame(index=basis.index)
aus["typ"] = basis["typ"]; aus["bew_V11B"] = bew
aus[f"status_{labels[0]}"] = basis["rechen_pruefung_mit"]
for lb in labels[1:]:
    n = lade(lb)
    if n is None: continue
    n = n.reindex(basis.index)
    aus[f"status_{lb}"] = n["rechen_pruefung_mit"]
    aus[f"sek_{lb}"] = n["sek_mit"].round(0)
    gleich = [norm(a) == norm(b) for a, b in zip(basis["antwort_mit"], n["antwort_mit"])]
    aus[f"aenderung_{lb}"] = ["" if g else "ANTWORT GEÄNDERT" for g in gleich]
    aus[f"antwort_{lb}"] = n["antwort_mit"]
    aus[f"befund_{lb}"] = n["rechen_befund_mit"]
aus["antwort_V11B"] = basis["antwort_mit"]
out = D / ("n100_vergleich_" + "_".join(labels) + ".csv")
aus.to_csv(out, encoding="utf-8-sig")
print(f"\nGespeichert: {out}")
for lb in labels[1:]:
    c = f"aenderung_{lb}"
    if c not in aus: continue
    g = aus[aus[c] != ""]
    print(f"\n=== {lb}: {len(g)} von {len(aus)} Antworten geändert ===")
    for i, r in g.iterrows():
        print(f"  {i:4s} [{r['typ']:9s}] V11B-Bewertung: {r['bew_V11B']:<12s} Status {r[f'status_{labels[0]}']} -> {r[f'status_{lb}']}")
    st = aus[f"status_{lb}"].value_counts(dropna=False)
    print("\nStatus der Rechenprüfung:\n" + st.to_string())
    print("\nWichtig zum Prüfen (Vergleich in der CSV): geänderte Fragen mit V11B-Bewertung korrekt = mögliche Verschlechterung;"
          " falsch/teilweise = mögliche Verbesserung. Zielfragen: F29 F62 F61 F52 F39 F9 F27 F1 F4.")
    ziel = ["F29", "F62", "F61", "F52", "F39", "F9", "F27", "F1", "F4"]
    for i in ziel:
        if i in aus.index:
            print(f"  {i}: V11B {aus.loc[i,'bew_V11B']} | {lb}-Status {aus.loc[i,f'status_{lb}']} | geändert: {aus.loc[i,c] != ''}")
