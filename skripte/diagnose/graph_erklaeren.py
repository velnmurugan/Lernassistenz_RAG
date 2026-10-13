"""
graph_erklaeren.py
------------------
Rechnet den Graph-Score für EINE Frage Schritt für Schritt mit den echten
Zahlen aus dem Wissensgraphen nach (zum Verstehen / für den Methodenteil):

  Schritt 1  Start-Begriffe: df, IDF, Startgewicht
  Schritt 2  Kanten der Start-Begriffe: wohin fließt wie viel (Runde 1 im Detail)
  Schritt 3  PageRank-Werte nach Runde 0, 1, 2, 3, 5, 10, 30
  Schritt 4  Chunk-Score: Begriffe im Chunk, r × IDF, Summe, √n, Score, Rang
  Schritt 5  Fusion: Ränge dense/BM25/Graph und RRF-Beiträge

Start:
  python graph_erklaeren.py "Was bringt der D-Anteil in einem Regler?" > graph_erklaerung.txt
  python graph_erklaeren.py "…" --chunks pdf_29143,pdf_29074 --rrf-k 5
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse

import numpy as np

import rag_pipeline
import wissensgraph as wg

RUNDEN_ZEIGEN = (0, 1, 2, 3, 5, 10, 30)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frage")
    ap.add_argument("--chunks", default="", help="zusätzliche Chunk-IDs für Schritt 4/5, kommagetrennt")
    ap.add_argument("--rrf-k", type=int, default=5)
    ap.add_argument("--nachbarn", type=int, default=8)
    args = ap.parse_args()

    chunks = rag_pipeline.lade_wissensbasis("daten/wissensbasen/knowledge_base_boege.json")
    g = wg.lade_graph(chunks)
    N = len(chunks)
    L, idf, df = g["labels"], g["idf"], g["df"]
    P = g["PT"].T.tocsr()  # Übergangsmatrix: Zeile i = Anteile, die Begriff i weitergibt
    d = wg.KG_DAEMPFUNG

    # ---------------- Schritt 1 ----------------
    seeds = wg.start_knoten(args.frage, g)
    print(f"FRAGE: {args.frage}\n")
    print("=" * 90)
    print("SCHRITT 1 – Start-Begriffe und Startgewicht")
    print("=" * 90)
    if not seeds:
        print("Keine Start-Begriffe gefunden -> Graph liefert für alle Chunks 0.")
        return
    summe = sum(w for w, _ in seeds.values())
    print(f"{'Begriff':<28}{'Herkunft':<10}{'df':>6}{'IDF = ln(N/df)':>22}{'Gewicht':>10}{'Start p':>10}")
    for i, (w, h) in sorted(seeds.items(), key=lambda t: -t[1][0]):
        print(f"{L[i]:<28}{h:<10}{int(df[i]):>6}   ln({N}/{int(df[i])}) = {idf[i]:>5.2f}{w:>10.2f}{w / summe:>10.3f}")
    print(f"Summe der Gewichte = {summe:.2f}; Start p = Gewicht / Summe (ergibt zusammen 1.000)")

    p = np.zeros(len(L))
    for i, (w, _) in seeds.items():
        p[i] = w / summe

    # ---------------- Schritt 2 ----------------
    print("\n" + "=" * 90)
    print("SCHRITT 2 – Kanten der Start-Begriffe (Runde 1 im Detail)")
    print("=" * 90)
    print(f"Jede Runde: neuer Wert = {1 - d:.1f} × Start p (Nachfüllung) + {d:.1f} × (was von Nachbarn hereinfließt)")
    print("Kantengewicht = gemeinsame Chunks / √(df_a × df_b); Anteil = Kantengewicht / Summe aller Kanten des Begriffs\n")
    for i in sorted(seeds, key=lambda j: -p[j]):
        zeile = P.getrow(i)
        raus = d * p[i]
        print(f"{L[i]} hat {p[i]:.3f} -> gibt {d:.1f} × {p[i]:.3f} = {raus:.4f} weiter an {zeile.nnz} Nachbarn:")
        if zeile.nnz == 0:
            print("   (keine Kanten – Gewicht geht zurück an die Start-Begriffe)\n")
            continue
        K = g["K"].getrow(i)
        reihen = sorted(zip(zeile.indices, zeile.data), key=lambda t: -t[1])
        for j, anteil in reihen[:args.nachbarn]:
            kg = K[0, j]
            gemeinsam = kg * np.sqrt(df[i] * df[j]) if kg else 0
            print(f"   -> {L[j]:<28} gemeinsame Chunks ≈{gemeinsam:>4.0f}  Kantengewicht {kg:.3f}  "
                  f"Anteil {anteil * 100:>5.1f} %  bekommt {raus:.4f} × {anteil:.3f} = {raus * anteil:.4f}")
        rest = sum(a for _, a in reihen[args.nachbarn:])
        if rest > 0:
            print(f"   -> {len(reihen) - args.nachbarn} weitere Nachbarn zusammen {rest * 100:.1f} % = {raus * rest:.4f}")
        print()

    # ---------------- Schritt 3 ----------------
    verlauf = {0: p.copy()}
    r = p.copy()
    for k in range(1, wg.KG_ITERATIONEN + 1):
        haengend = r[g["haengend"]].sum()
        r = (1 - d) * p + d * (g["PT"] @ r + haengend * p)
        verlauf[k] = r.copy()
    r_end = verlauf[wg.KG_ITERATIONEN]
    zeigen = [int(i) for i in np.argsort(-r_end)[:12]]
    print("=" * 90)
    print("SCHRITT 3 – PageRank-Werte r pro Runde (12 Begriffe mit dem höchsten Endwert)")
    print("=" * 90)
    runden = [k for k in RUNDEN_ZEIGEN if k in verlauf]
    print(f"{'Begriff':<28}" + "".join(f"{'R' + str(k):>8}" for k in runden) + f"{'IDF':>7}")
    for i in zeigen:
        print(f"{L[i]:<28}" + "".join(f"{verlauf[k][i]:>8.4f}" for k in runden) + f"{idf[i]:>7.2f}")
    print(f"{'(Summe aller Begriffe)':<28}" + "".join(f"{verlauf[k].sum():>8.3f}" for k in runden))
    print(f"Begriffe mit r > 0.001 nach Runde {wg.KG_ITERATIONEN}: {int((r_end > 0.001).sum())} von {len(L)}")

    # ---------------- Schritt 4 ----------------
    scores = np.asarray((g["A"] @ (r_end * idf)) / g["chunk_norm"]).ravel()
    reihenfolge = np.argsort(-scores, kind="stable")
    graph_rang = {int(ci): rang for rang, ci in enumerate(reihenfolge, start=1) if scores[ci] > 0}
    id_zu_idx = {cid: i for i, cid in enumerate(g["chunk_ids"])}
    auswahl = [int(ci) for ci in reihenfolge[:5]]
    for cid in [c.strip() for c in args.chunks.split(",") if c.strip()]:
        if cid in id_zu_idx and id_zu_idx[cid] not in auswahl:
            auswahl.append(id_zu_idx[cid])

    print("\n" + "=" * 90)
    print("SCHRITT 4 – Chunk-Score = Σ (r × IDF) über die Begriffe im Chunk  /  √(Anzahl Begriffe)")
    print("=" * 90)
    for ci in auswahl:
        begriffe = g["A"][ci].indices
        print(f"\n{g['chunk_ids'][ci]}  (Graph-Rang {graph_rang.get(ci, '–')})")
        print(f"   Text: {chunks[ci]['text'][:160]}…")
        teile = sorted(((L[j], r_end[j], idf[j], r_end[j] * idf[j]) for j in begriffe), key=lambda t: -t[3])
        for name, rj, ij, prod in teile:
            print(f"     {name:<28} r={rj:.4f} × IDF={ij:5.2f} = {prod:.4f}")
        s = sum(t[3] for t in teile)
        n = len(teile)
        print(f"   Summe = {s:.4f};  {n} Begriffe -> √{n} = {np.sqrt(max(n, 1)):.2f};  "
              f"Score = {s:.4f} / {np.sqrt(max(n, 1)):.2f} = {scores[ci]:.4f}")

    # ---------------- Schritt 5 ----------------
    print("\n" + "=" * 90)
    print(f"SCHRITT 5 – Fusion (RRF, k={args.rrf_k}): Beitrag je Liste = 1 / (k + Rang)")
    print("=" * 90)
    rag_pipeline.RRF_K = args.rrf_k
    raenge = {}
    for m in ("dense", "bm25"):
        _, alle = rag_pipeline.retrieval(args.frage, chunks, top_k=1, methode=m)
        raenge[m] = {c["id"]: i for i, c in enumerate(alle, start=1)}
    k = args.rrf_k
    print(f"{'Chunk':<12}{'dense':>7}{'bm25':>7}{'graph':>7}   {'1/(k+d)':>8}{'1/(k+b)':>8}{'1/(k+g)':>8}"
          f"{'V1 ohne Graph':>15}{'V2 mit Graph':>14}")
    zeilen = []
    for ci in auswahl:
        cid = g["chunk_ids"][ci]
        rd, rb, rg = raenge["dense"][cid], raenge["bm25"][cid], graph_rang.get(ci)
        bd, bb = 1 / (k + rd), 1 / (k + rb)
        bg = 1 / (k + rg) if rg else 0.0
        zeilen.append((cid, rd, rb, rg, bd, bb, bg))
    for cid, rd, rb, rg, bd, bb, bg in sorted(zeilen, key=lambda z: -(z[4] + z[5] + z[6])):
        print(f"{cid:<12}{rd:>7}{rb:>7}{rg or '–':>7}   {bd:>8.4f}{bb:>8.4f}{bg:>8.4f}{bd + bb:>15.4f}{bd + bb + bg:>14.4f}")
    print("\n(Nur die Chunks aus Schritt 4. Die echten Top-4 hängen auch von allen anderen Chunks ab –"
          " siehe frage_testen.py.)")


if __name__ == "__main__":
    main()