"""
retrieval_erklaeren.py
----------------------
Zeigt für EINE Frage Schritt für Schritt, wie die Retrieval-Verfahren mit der
echten Wissensbasis arbeiten, als eine HTML-Seite (zum Vorführen / Methodenteil):

  1  Dense:        Kosinus-Ähnlichkeit, Top-Chunks, Zielscheibe (Abstand = 1 − Kosinus)
  2  BM25:         Tokenisierung der Frage (klein, Stoppwörter, Stämme), IDF je Wort,
                   Beitrag jedes Wortes zum Score, Treffer im Chunk markiert
  3  Begriffsgraph: Start-Begriffe, PageRank-Ausbreitung (interaktiver Teilgraph),
                   Begriffe, die den Chunk-Score tragen
  4  RRF:          Ränge der drei Listen und ihre Beiträge 1/(k + Rang)
  5  Reranker:     Cross-Encoder bewertet nur die Kandidaten neu; Rangwechsel
  6  Überblick:    Rang des erwarteten Chunks in jedem Verfahren, Top 4 je Verfahren

Rechnet mit denselben Funktionen und Parametern wie rag_pipeline.retrieval()
(Methode hybrid_kg_rr) und prüft am Ende, dass die Top-Kandidaten übereinstimmen.

Start:
  python retrieval_erklaeren.py "Wie funktioniert eine Zweihandverriegelung in der SPS?"
  python retrieval_erklaeren.py "…" --erwartet pdf_27720 --rrf-k 5 --top 8
  python retrieval_erklaeren.py "…" --ohne-reranker        (schneller, ohne Cross-Encoder)

Ausgabe: evaluationsdaten/frage_erklaerung_<frage>.html
  7  Generierung: Prompt, Rohausgabe, Hinweis + Lösung, regelbasierte Prüfungen
  8  Bewertung:   Faithfulness, Answer Relevance, Context Relevance mit Formel und Rechenweg
  9  Retrieval-Metriken für diese Frage (Beitrag zu Recall@4 und MRR)
⚠ Die Seite enthält wörtliche Handbuch-Auszüge -> nicht ins Git (siehe .gitignore),
  nicht hochladen; nur lokal / in der Besprechung zeigen.
"""
import argparse
import csv
import html
import json
import re
from pathlib import Path

import numpy as np

import rag_pipeline as rp
import wissensgraph as wg

FARBE = {"dense": "#2a78d6", "bm25": "#1f9e6e", "graph": "#e07b28", "rrf": "#7a4fd1",
         "rr": "#c2364a", "erwartet": "#d9a400"}


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def esc(t):
    return html.escape(str(t))


def kurz(text, n=420):
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def balken(wert, maximum, farbe, breite=180):
    b = 0 if maximum <= 0 else max(1, int(breite * wert / maximum))
    return f'<span class="bar" style="width:{b}px;background:{farbe}"></span>'


def markiere_stamm(text, stamm_menge):
    """Wörter markieren, deren BM25-Stamm in der Frage vorkommt."""
    rp.tokenisiere("")  # Stemmer initialisieren
    def ersetze(m):
        w = m.group(0)
        if w.lower() in rp.BM25_STOPPWOERTER or len(w) < 2:
            return esc(w)
        return f"<mark>{esc(w)}</mark>" if rp._stemmer.stemWord(w.lower()) in stamm_menge else esc(w)
    teile, pos = [], 0
    for m in re.finditer(r"[A-Za-zÄÖÜäöüß0-9]+", text):
        teile.append(esc(text[pos:m.start()]))
        teile.append(ersetze(m))
        pos = m.end()
    teile.append(esc(text[pos:]))
    return "".join(teile)


def erwarteten_chunk_finden(frage):
    pfad = Path("testfragen_v1.csv")
    if not pfad.exists():
        return []
    with open(pfad, encoding="utf-8") as f:
        for z in csv.DictReader(f):
            if z["frage"].strip() == frage.strip() and z.get("chunk_id", "").strip():
                return [z["chunk_id"].strip()]
    return []


# ---------------------------------------------------------------------------
# Berechnung (gleiche Logik wie rag_pipeline.retrieval)
# ---------------------------------------------------------------------------
def berechne(frage, chunks, mit_reranker):
    modell = rp._lade_embedding_modell()
    E = rp._embeddings_fuer_chunks(chunks)
    q = modell.encode([frage], convert_to_numpy=True, normalize_embeddings=True)[0]
    from sklearn.metrics.pairwise import cosine_similarity
    dense = cosine_similarity(q[None, :], E)[0]  # exakt wie rag_pipeline.retrieval

    bm25 = rp._bm25_index(chunks)
    q_tok = rp.tokenisiere(frage)
    bm = np.asarray(bm25.get_scores(q_tok), dtype=np.float64)

    graph, gd = wg.graph_scores(frage, chunks, frage_embedding=q, details=True)

    k = rp.RRF_K
    r_dense, r_bm, r_graph = rp._raenge(dense), rp._raenge(bm), rp._raenge(graph)
    b_dense, b_bm = 1.0 / (k + r_dense), 1.0 / (k + r_bm)
    b_graph = rp.KG_GEWICHT * np.where(graph > 0, 1.0 / (k + r_graph), 0.0)
    rrf = (1.0 / (k + r_dense) + 1.0 / (k + r_bm) + b_graph)  # gleiche Rechenreihenfolge wie die Pipeline
    reihenfolge = np.argsort(-rrf, kind="stable")

    rr = None
    if mit_reranker:
        import reranker
        n = min(reranker.RERANK_KANDIDATEN, len(chunks))
        kand = reihenfolge[:n]
        werte = reranker.bewerte(frage, [chunks[i]["text"] for i in kand])
        neu = sorted(range(n), key=lambda j: -werte[j])
        rr = {"kandidaten": kand, "werte": np.array(werte), "neu": neu, "n": n}

    return {"q": q, "E": E, "dense": dense, "bm25": bm25, "q_tok": q_tok, "bm": bm,
            "graph": graph, "gd": gd, "k": k, "r_dense": r_dense, "r_bm": r_bm, "r_graph": r_graph,
            "b_dense": b_dense, "b_bm": b_bm, "b_graph": b_graph, "rrf": rrf,
            "reihenfolge": reihenfolge, "rr": rr}


def bm25_beitraege(bm25, q_tok, i):
    """Beitrag jedes Frage-Stamms zum BM25-Score von Chunk i (BM25Okapi-Formel)."""
    tf_d, dl = bm25.doc_freqs[i], bm25.doc_len[i]
    out = {}
    for t in q_tok:
        tf = tf_d.get(t, 0)
        idf = bm25.idf.get(t, 0.0)
        w = idf * tf * (bm25.k1 + 1) / (tf + bm25.k1 * (1 - bm25.b + bm25.b * dl / bm25.avgdl)) if tf else 0.0
        out[t] = out.get(t, 0.0) + w
    return out


# ---------------------------------------------------------------------------
# HTML-Abschnitte
# ---------------------------------------------------------------------------
def abschnitt_ueberblick(frage, res, chunks, erwartet, top4_final):
    n = len(chunks)
    rr_n = res["rr"]["n"] if res["rr"] else 0
    stufen = [
        ("Frage", esc(frage), "#555"),
        ("Erste Stufe", f'<b style="color:{FARBE["dense"]}">Dense</b> · <b style="color:{FARBE["bm25"]}">BM25</b> · '
                        f'<b style="color:{FARBE["graph"]}">Graph</b><br>je eine Rangliste über alle {n:,} Chunks', "#333"),
        ("Fusion", f'<b style="color:{FARBE["rrf"]}">RRF</b> (k = {res["k"]})<br>eine gemeinsame Rangliste', "#333"),
    ]
    if rr_n:
        stufen.append(("Zweite Stufe", f'<b style="color:{FARBE["rr"]}">Cross-Encoder</b><br>bewertet nur die besten {rr_n} neu', "#333"))
    stufen.append(("An qwen", "die besten 4 Chunks:<br>" + ", ".join(esc(chunks[i]["id"]) for i in top4_final), "#333"))
    stufen.append(("Generierung", "qwen schreibt Hinweis + Lösung", "#333"))
    stufen.append(("Bewertung", "Richter prüft gegen die 4 Chunks:<br>Faithfulness · Answer Relevance · Context Relevance", "#333"))
    boxen = '<span class="pfeil">→</span>'.join(
        f'<div class="stufe"><div class="st-titel">{t}</div><div>{inhalt}</div></div>' for t, inhalt, _ in stufen)
    hinweis = ""
    if erwartet:
        hinweis = f'<p>Erwarteter Quell-Chunk (aus den Testfragen oder <code>--erwartet</code>): ' \
                  f'<span class="erw">{", ".join(esc(e) for e in erwartet)}</span> – in allen Tabellen gelb markiert.</p>'
    return f'<section><h2>Ablauf</h2><div class="pipeline">{boxen}</div>{hinweis}</section>'


def chunk_zeile(rang, c, wert_html, erw, extra=""):
    cls = ' class="erw-zeile"' if erw else ""
    return (f'<tr{cls}><td class="r">{rang}</td><td><code>{esc(c["id"])}</code><br>'
            f'<span class="thema">{esc(c.get("thema", ""))}</span></td><td>{wert_html}</td>'
            f'<td class="text">{extra or esc(kurz(c["text"]))}</td></tr>')


def abschnitt_dense(res, chunks, erwartet, top):
    d = res["dense"]
    idx = np.argsort(-d)[:top]
    zeilen = "".join(chunk_zeile(r, chunks[i], f'{d[i]:.3f} {balken(d[i], d[idx[0]], FARBE["dense"], 120)}',
                                 chunks[i]["id"] in erwartet) for r, i in enumerate(idx, 1))
    # Zielscheibe: Frage in der Mitte, Abstand = 1 − Kosinus (exakt).
    # Nur der Winkel ist frei gewählt (aus einer PCA der Chunks, damit ähnliche Chunks nebeneinander liegen).
    menge = list(np.argsort(-d)[:40])
    for e in erwartet:
        j = next((i for i, c in enumerate(chunks) if c["id"] == e), None)
        if j is not None and j not in menge:
            menge.append(j)
    X = res["E"][menge]
    Xc = X - X.mean(axis=0)
    _, _, vt = np.linalg.svd(Xc, full_matrices=False)
    P = Xc @ vt[:2].T
    winkel = np.arctan2(P[:, 1], P[:, 0])
    abstand = 1.0 - d[menge]
    amax = float(abstand.max()) * 1.05
    S, M = 420, 210            # Bildgröße, Mittelpunkt
    RMAX = 190
    rad = lambda a: RMAX * a / amax
    top4 = [int(i) for i in np.argsort(-d)[:4]]
    teile = []
    # Ringe mit Kosinus-Beschriftung
    for c in np.arange(np.ceil((1 - amax) * 10) / 10, 1.0, 0.1):
        r = rad(1 - c)
        if r <= 0:
            continue
        teile.append(f'<circle cx="{M}" cy="{M}" r="{r:.1f}" fill="none" stroke="#e3e6eb"/>'
                     f'<text x="{M + 3}" y="{M - r + 12:.1f}" font-size="10" fill="#8a93a3">Kosinus {c:.1f}</text>')
    r4 = rad(1 - d[top4[-1]])
    teile.append(f'<circle cx="{M}" cy="{M}" r="{r4:.1f}" fill="none" stroke="{FARBE["dense"]}" stroke-dasharray="5 4" stroke-width="1.5"/>'
                 f'<text x="{M}" y="{M + r4 + 13:.1f}" text-anchor="middle" font-size="11" fill="{FARBE["dense"]}">Grenze Top 4</text>')
    for w, a, i in zip(winkel, abstand, menge):
        x, y = M + rad(a) * np.cos(w), M + rad(a) * np.sin(w)
        farbe = FARBE["dense"] if int(i) in top4 else "#b8c0cc"
        rand = f' stroke="{FARBE["erwartet"]}" stroke-width="3"' if chunks[i]["id"] in erwartet else ""
        teile.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{farbe}"{rand}>'
                     f'<title>{esc(chunks[i]["id"])} · Rang {int(res["r_dense"][i])} · Kosinus {d[i]:.3f}\n'
                     f'{esc(kurz(chunks[i]["text"], 160))}</title></circle>')
    teile.append(f'<text x="{M}" y="{M + 8}" text-anchor="middle" font-size="24" fill="#c2364a">★</text>')
    svg = f'<svg width="{S}" height="{S}" class="plot">{"".join(teile)}</svg>'
    return f"""<section><h2 style="color:{FARBE['dense']}">1 · Dense Retrieval</h2>
<p>Frage und jeder Chunk werden <b>getrennt</b> in einen Vektor umgewandelt (Bi-Encoder,
<code>{esc(rp.EMBEDDING_MODELL_NAME)}</code>). Die Chunk-Vektoren liegen bereits vor; verglichen wird nur noch per
Kosinus-Ähnlichkeit (1 = gleiche Richtung). Gefunden wird Ähnlichkeit der <b>Bedeutung</b>, nicht der Wörter.</p>
<div class="zwei"><div><table><tr><th>Rang</th><th>Chunk</th><th>Kosinus</th><th>Text</th></tr>{zeilen}</table></div>
<div><figure>{svg}<figcaption>★ = Frage in der Mitte. Jeder Punkt ist ein Chunk der Top 40; <b>Abstand zur Mitte = 1 − Kosinus</b>
(je näher, desto ähnlicher). <span style="color:{FARBE['dense']}">●</span> Top 4 dense (innerhalb der gestrichelten Grenze),
● weitere, gelber Rand = erwarteter Chunk. Der Winkel trägt keine Bedeutung (nur: ähnliche Chunks liegen nebeneinander).
Mauszeiger auf einen Punkt zeigt Chunk, Rang und Text.</figcaption></figure></div></div>
</section>"""


def abschnitt_bm25(frage, res, chunks, erwartet, top):
    rp.tokenisiere("")
    roh = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", frage)
    woerter = re.findall(r"[a-zäöüß0-9]+", roh.lower())
    schritte = []
    for w in woerter:
        if len(w) < 2:
            schritte.append((w, "zu kurz", "–"))
        elif w in rp.BM25_STOPPWOERTER:
            schritte.append((w, "Stoppwort", "–"))
        else:
            schritte.append((w, "", rp._stemmer.stemWord(w)))
    bm25, q_tok = res["bm25"], res["q_tok"]
    N = len(chunks)
    tok_zeilen = "".join(
        f'<tr><td>{esc(w)}</td><td>{"<s>entfernt</s> (" + grund + ")" if grund else "behalten"}</td>'
        f'<td><code>{esc(s)}</code></td>'
        + (f'<td>{sum(1 for dfq in bm25.doc_freqs if s in dfq) if not grund else "–"}</td>'
           f'<td>{bm25.idf.get(s, 0.0):.2f}</td>' if not grund else "<td>–</td><td>–</td>")
        + "</tr>" for w, grund, s in schritte)
    b = res["bm"]
    idx = np.argsort(-b)[:top]
    stamm_menge = set(q_tok)
    farben = ["#1f9e6e", "#5cc39a", "#0f6b4a", "#9fdcc2", "#2e8b57", "#7fbf9f"]
    tok_farbe = {t: farben[n % len(farben)] for n, t in enumerate(dict.fromkeys(q_tok))}
    maxb = b[idx[0]] if len(idx) else 1
    zeilen = []
    for r, i in enumerate(idx, 1):
        beitr = bm25_beitraege(bm25, q_tok, i)
        stapel = "".join(f'<span class="bar" title="{esc(t)}: {v:.2f}" style="width:{max(1, int(160 * v / maxb))}px;'
                         f'background:{tok_farbe[t]}"></span>' for t, v in beitr.items() if v > 0)
        liste = " + ".join(f"{esc(t)} {v:.2f}" for t, v in beitr.items() if v > 0)
        zeilen.append(chunk_zeile(r, chunks[i], f'{b[i]:.2f}<br>{stapel}<div class="klein">{liste}</div>',
                                  chunks[i]["id"] in erwartet, markiere_stamm(kurz(chunks[i]["text"]), stamm_menge)))
    legende = " ".join(f'<span class="bar" style="width:12px;background:{f}"></span>{esc(t)}' for t, f in tok_farbe.items())
    return f"""<section><h2 style="color:{FARBE['bm25']}">2 · BM25 (Schlüsselwörter)</h2>
<p>Frage und Chunks werden gleich vorbereitet: Kleinschreibung, Stoppwörter entfernen, Wörter auf den Stamm kürzen
(Snowball-Stemmer, deutsch). Danach zählt BM25, welche Stämme der Frage im Chunk vorkommen. <b>Seltene Stämme
(hoher IDF) zählen mehr</b>, lange Chunks werden abgewertet. N = {N:,} Chunks.</p>
<table class="schmal"><tr><th>Wort der Frage</th><th>Schritt</th><th>Stamm</th><th>in Chunks (df)</th><th>IDF</th></tr>{tok_zeilen}</table>
<p class="klein">Beitrag je Stamm zum Score: {legende} · <mark>markiert</mark> = Wort im Chunk mit gleichem Stamm wie ein Fragewort.</p>
<table><tr><th>Rang</th><th>Chunk</th><th>BM25-Score = Summe der Beiträge</th><th>Text</th></tr>{"".join(zeilen)}</table></section>"""


def abschnitt_graph(frage, res, chunks, erwartet, top, n_knoten):
    g, r, seeds = res["gd"]["graph"], res["gd"]["ppr"], res["gd"]["seeds"]
    gs = res["graph"]
    if not seeds:
        return f"""<section><h2 style="color:{FARBE['graph']}">3 · Begriffsgraph</h2>
<p>Kein Wort der Frage ist ein Begriff im Graphen → der Graph liefert für alle Chunks 0 und trägt nichts zur Fusion bei.</p></section>"""
    summe = sum(w for w, _ in seeds.values())
    seed_zeilen = "".join(
        f'<tr><td><b>{esc(g["labels"][i])}</b></td><td>{esc(h)}</td><td>{int(g["df"][i])}</td>'
        f'<td>{g["idf"][i]:.2f}</td><td>{w / summe:.3f}</td></tr>'
        for i, (w, h) in sorted(seeds.items(), key=lambda t: -t[1][0]))
    top_begriffe = [int(i) for i in np.argsort(-r)[:12] if r[i] > 0]
    maxr = r[top_begriffe[0]] if top_begriffe else 1
    ppr_zeilen = "".join(
        f'<tr><td>{esc(g["labels"][i])}{" ★" if i in seeds else ""}</td><td>{r[i]:.4f} '
        f'{balken(r[i], maxr, FARBE["graph"], 140)}</td></tr>' for i in top_begriffe)

    # Teilgraph (vis-network): Begriffe mit der meisten PageRank-Masse + Top-Chunks
    knoten = [int(i) for i in np.argsort(-r)[:n_knoten] if r[i] > 0]
    menge = set(knoten)
    nodes, edges = [], []
    for i in knoten:
        start = i in seeds
        nodes.append({"id": f"b{i}", "label": g["labels"][i], "value": float(r[i]),
                      "color": FARBE["graph"] if start else "#f3c9a6",
                      "title": f"{g['labels'][i]} | PageRank {r[i]:.4f} | df {int(g['df'][i])}" + (" | Start" if start else "")})
    sub = g["K"][knoten][:, knoten].tocoo()
    for a, b, w in zip(sub.row, sub.col, sub.data):
        if a < b:
            edges.append({"from": f"b{knoten[a]}", "to": f"b{knoten[b]}", "width": 1 + 4 * float(min(w, 1.0)),
                          "title": f"Kantengewicht {w:.2f}", "color": {"color": "#c9ced6"}})
    idx = [int(i) for i in np.argsort(-gs)[:top] if gs[i] > 0]
    for rang, ci in enumerate(idx[:4], 1):
        nodes.append({"id": f"c{ci}", "label": f"#{rang} {chunks[ci]['id']}", "shape": "box",
                      "color": FARBE["erwartet"] if chunks[ci]["id"] in erwartet else "#9aa4b2",
                      "title": kurz(chunks[ci]["text"], 300)})
        for i in g["A"][ci].indices:
            if int(i) in menge:
                edges.append({"from": f"c{ci}", "to": f"b{int(i)}", "dashes": True, "color": {"color": "#9aa4b2"}})

    zeilen = []
    for rang, ci in enumerate(idx, 1):
        begr = g["A"][ci].indices
        beitr = sorted(((r[i] * g["idf"][i], i) for i in begr if r[i] > 0), reverse=True)[:5]
        liste = ", ".join(f'{esc(g["labels"][i])} ({v:.3f})' for v, i in beitr)
        zeilen.append(chunk_zeile(rang, chunks[ci],
                                  f'{gs[ci]:.4f}<div class="klein">{len(begr)} Begriffe, √n = {g["chunk_norm"][ci]:.2f}<br>'
                                  f'tragend (PageRank × IDF): {liste}</div>', chunks[ci]["id"] in erwartet))
    return f"""<section><h2 style="color:{FARBE['graph']}">3 · Begriffsgraph (Personalized PageRank)</h2>
<p>Knoten = Fachbegriffe des Handbuchs, Kante = Begriffe kommen oft in denselben Chunks vor. Die Begriffe der Frage sind
die <b>Start-Begriffe</b> (Gewicht nach Seltenheit, IDF). PageRank verteilt ihr Gewicht über die Kanten auf verwandte
Begriffe (Dämpfung {wg.KG_DAEMPFUNG}, {wg.KG_ITERATIONEN} Runden). Chunk-Score = Σ (PageRank × IDF) der Begriffe im Chunk / √(Anzahl Begriffe).</p>
<div class="zwei"><div><h3>Start-Begriffe</h3><table class="schmal"><tr><th>Begriff</th><th>Herkunft</th><th>df</th><th>IDF</th><th>Startgewicht</th></tr>{seed_zeilen}</table>
<h3>Nach PageRank (★ = Start)</h3><table class="schmal"><tr><th>Begriff</th><th>PageRank</th></tr>{ppr_zeilen}</table></div>
<div><div id="graphnetz" class="netz"><p class="klein" style="padding:12px">Das Graph-Bild lädt vis-network aus dem Internet (unpkg.com). Ohne Verbindung bleibt dieses Feld leer; die Tabellen gelten trotzdem.</p></div><p class="klein">Interaktiv: Knotengröße = PageRank, dunkel = Start-Begriff,
graue Kästen = Top-4-Chunks des Graphen (gestrichelt: enthält den Begriff). Knoten lassen sich ziehen, Mausover zeigt Werte.</p></div></div>
<table><tr><th>Rang</th><th>Chunk</th><th>Graph-Score</th><th>Text</th></tr>{"".join(zeilen)}</table>
<script>window.GRAPH_DATEN = {json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)};</script></section>"""


def abschnitt_rrf(res, chunks, erwartet, top):
    k = res["k"]
    idx = list(res["reihenfolge"][:top])
    for e in erwartet:
        j = next((i for i, c in enumerate(chunks) if c["id"] == e), None)
        if j is not None and j not in idx:
            idx.append(j)
    rang_rrf = rp._raenge(res["rrf"])
    maxs = res["rrf"][idx[0]]
    zeilen = []
    for i in idx:
        def zelle(r, b, farbe, aktiv=True):
            return (f'<td>{r:,}<br><span class="klein">1/({k}+{r:,}) = {b:.4f}</span></td>' if aktiv
                    else '<td>–<br><span class="klein">kein Graph-Bezug: 0</span></td>')
        gaktiv = res["graph"][i] > 0
        stapel = (f'<span class="bar" style="width:{int(160 * res["b_dense"][i] / maxs)}px;background:{FARBE["dense"]}"></span>'
                  f'<span class="bar" style="width:{int(160 * res["b_bm"][i] / maxs)}px;background:{FARBE["bm25"]}"></span>'
                  f'<span class="bar" style="width:{int(160 * res["b_graph"][i] / maxs)}px;background:{FARBE["graph"]}"></span>')
        cls = ' class="erw-zeile"' if chunks[i]["id"] in erwartet else ""
        zeilen.append(f'<tr{cls}><td class="r">{rang_rrf[i]:,}</td><td><code>{esc(chunks[i]["id"])}</code></td>'
                      + zelle(res["r_dense"][i], res["b_dense"][i], FARBE["dense"])
                      + zelle(res["r_bm"][i], res["b_bm"][i], FARBE["bm25"])
                      + zelle(res["r_graph"][i], res["b_graph"][i], FARBE["graph"], gaktiv)
                      + f'<td><b>{res["rrf"][i]:.4f}</b><br>{stapel}</td></tr>')
    return f"""<section><h2 style="color:{FARBE['rrf']}">4 · Fusion: Reciprocal Rank Fusion</h2>
<p>Jede der drei Listen gibt jedem Chunk Punkte nach seinem <b>Rang</b>: 1 / (k + Rang), hier k = {k}.
Die Punkte werden addiert. Es zählen nur Ränge, daher müssen Kosinus-, BM25- und Graph-Werte nicht vergleichbar sein.
Ein Chunk, der in mehreren Listen weit oben steht, steigt auf.</p>
<p class="klein">Balken: Anteil <span style="color:{FARBE['dense']}">Dense</span> ·
<span style="color:{FARBE['bm25']}">BM25</span> · <span style="color:{FARBE['graph']}">Graph</span> an der Summe.</p>
<table><tr><th>RRF-Rang</th><th>Chunk</th><th style="color:{FARBE['dense']}">Rang Dense</th><th style="color:{FARBE['bm25']}">Rang BM25</th>
<th style="color:{FARBE['graph']}">Rang Graph</th><th>RRF-Summe</th></tr>{"".join(zeilen)}</table></section>"""


def abschnitt_reranker(res, chunks, erwartet, top):
    rr = res["rr"]
    if rr is None:
        return '<section><h2>5 · Reranker</h2><p>Mit <code>--ohne-reranker</code> übersprungen.</p></section>'
    kand, werte, neu, n = rr["kandidaten"], rr["werte"], rr["neu"], rr["n"]
    neu_rang = {j: p + 1 for p, j in enumerate(neu)}
    # Steigungsdiagramm: links Rang nach RRF, rechts Rang nach Cross-Encoder
    zeige = sorted(set(range(min(top, n))) | set(neu[:top]) |
                   {j for j in range(n) if chunks[kand[j]]["id"] in erwartet})
    max_rang = max(max(j + 1, neu_rang[j]) for j in zeige)
    W, schritt, oben = 600, 18, 34
    H = oben + schritt * max_rang + 10
    y = lambda rang: oben + (rang - 1) * schritt
    linien = []
    for j in zeige:
        a, b = j + 1, neu_rang[j]
        erw = chunks[kand[j]]["id"] in erwartet
        farbe = FARBE["erwartet"] if erw else (FARBE["rr"] if b <= 4 else "#b8c0cc")
        breite = 3 if (erw or b <= 4) else 1.5
        cid = esc(chunks[kand[j]]["id"])
        linien.append(f'<line x1="150" y1="{y(a)}" x2="{W - 150}" y2="{y(b)}" stroke="{farbe}" stroke-width="{breite}"/>'
                      f'<text x="142" y="{y(a) + 4}" text-anchor="end" font-size="12">{a}. {cid}</text>'
                      f'<text x="{W - 142}" y="{y(b) + 4}" font-size="12">{b}. {cid}</text>')
    trenn = y(4) + schritt / 2
    svg = (f'<svg width="{W}" height="{H}" class="plot"><text x="150" y="16" text-anchor="middle" font-size="13" '
           f'font-weight="bold">Rang nach RRF</text><text x="{W - 150}" y="16" text-anchor="middle" font-size="13" '
           f'font-weight="bold">Rang nach Cross-Encoder</text>'
           f'<line x1="{W - 150}" y1="{trenn}" x2="{W - 10}" y2="{trenn}" stroke="#c2364a" stroke-dasharray="4 3"/>'
           f'<text x="{W / 2}" y="{trenn + 4}" text-anchor="middle" font-size="11" font-weight="bold" fill="#c2364a" '
           f'stroke="#fff" stroke-width="4" paint-order="stroke">↑ Top 4 an qwen</text>'
           + "".join(linien) + "</svg>")
    maxw, minw = werte.max(), werte.min()
    zeilen = "".join(
        chunk_zeile(p + 1, chunks[kand[j]],
                    f'{werte[j]:.3f} {balken(werte[j] - minw, maxw - minw, FARBE["rr"], 100)}'
                    f'<div class="klein">vorher Rang {j + 1}</div>', chunks[kand[j]]["id"] in erwartet)
        for p, j in enumerate(neu[:top]))
    import reranker
    return f"""<section><h2 style="color:{FARBE['rr']}">5 · Zweite Stufe: Cross-Encoder-Reranking</h2>
<p>Der Cross-Encoder (<code>{esc(reranker.RERANKER_MODELL)}</code>) liest Frage und Chunk <b>gemeinsam</b> und gibt einen
Relevanzwert aus. Er bewertet <b>nur die {n} besten Chunks der RRF-Liste</b>, nicht alle {len(chunks):,}. Die neue Reihenfolge
ergibt sich <b>allein</b> aus seinem Wert; die RRF-Punkte entscheiden nur, wer Kandidat wird. Ein Chunk außerhalb der
{n} Kandidaten kann qwen nicht erreichen.</p>
<div class="zwei"><div>{svg}</div><div><table><tr><th>Neuer Rang</th><th>Chunk</th><th>Cross-Encoder-Wert</th><th>Text</th></tr>{zeilen}</table></div></div>
</section>"""


def abschnitt_vergleich(res, chunks, erwartet, top4_final):
    listen = {
        "Dense": (np.argsort(-res["dense"])[:4], res["r_dense"], FARBE["dense"]),
        "BM25": (np.argsort(-res["bm"])[:4], res["r_bm"], FARBE["bm25"]),
        "Graph": ([i for i in np.argsort(-res["graph"])[:4] if res["graph"][i] > 0], res["r_graph"], FARBE["graph"]),
        "RRF (Dense + BM25 + Graph)": (res["reihenfolge"][:4], rp._raenge(res["rrf"]), FARBE["rrf"]),
    }
    if res["rr"] is not None:
        rang_final = np.full(len(chunks), 10 ** 9)
        for p, j in enumerate(res["rr"]["neu"], 1):
            rang_final[res["rr"]["kandidaten"][j]] = p
        listen["+ Cross-Encoder (an qwen)"] = (top4_final, rang_final, FARBE["rr"])
    kopf = "".join(f'<th style="color:{f}">{esc(n)}</th>' for n, (_, _, f) in listen.items())
    zellen = "".join("<td>" + "<br>".join(
        f'<span class="{"erw" if chunks[i]["id"] in erwartet else ""}">{esc(chunks[i]["id"])}</span>' for i in top)
        + "</td>" for top, _, _ in listen.values())
    zeile_erw = ""
    for e in erwartet:
        j = next((i for i, c in enumerate(chunks) if c["id"] == e), None)
        if j is None:
            continue
        def rtext(name, rang):
            if name == "Graph" and res["graph"][j] <= 0:
                return "kein Bezug"
            if rang[j] >= 10 ** 9:
                return f'nicht unter den {res["rr"]["n"]} Kandidaten'
            return f'{int(rang[j]):,}' + (" ✓" if rang[j] <= 4 else "")
        zeile_erw += f'<tr class="erw-zeile"><td>Rang von <code>{esc(e)}</code></td>' + "".join(
            f'<td>{rtext(n, rang)}</td>' for n, (_, rang, _) in listen.items()) + "</tr>"
    return f"""<section><h2>6 · Überblick: Top 4 je Verfahren</h2>
<table><tr><th></th>{kopf}</tr><tr><td>Top 4</td>{zellen}</tr>{zeile_erw}</table></section>"""


# ---------------------------------------------------------------------------
# Generierung und Bewertung (gleiche Funktionen wie Batchlauf und ragas_auswertung.py)
# ---------------------------------------------------------------------------
def nachbar_ids(chunk_id):
    try:
        nr = int(chunk_id.split("_")[-1])
    except ValueError:
        return set()
    return {f"pdf_{nr - 1:04d}", f"pdf_{nr + 1:04d}"}


def generierung(frage, res, chunks, top4_final):
    import time
    bester = float(res["dense"].max())
    out = {"bester": bester, "gate": bester >= rp.RELEVANZ_SCHWELLE, "version": rp.SCAFFOLDING_VERSION}
    if not out["gate"]:
        return out
    top = [chunks[i] for i in top4_final]
    out["prompt"] = rp.baue_scaffolding_prompt(frage, top)
    t0 = time.time()
    out["roh"] = rp.frage_llm(out["prompt"], options=rp.GENERIERUNGS_OPTIONEN)
    stufen = rp.parse_scaffolding_antwort(out["roh"])
    if rp.SCAFFOLDING_VERSION == "S2-v2" and hasattr(rp, "_hinweis_separat"):
        stufen.update(rp._hinweis_separat(frage, top, stufen))
    out["sekunden"] = time.time() - t0
    out["stufen"] = stufen
    from ragas_auswertung import ist_modell_verweigerung
    out["verweigerung"] = ist_modell_verweigerung(stufen["loesung"])
    return out


def bewertung(frage, gen, chunks, top4_final, judge):
    import requests
    import ragas_auswertung as ra
    try:  # Generator entladen, damit der Richter ganz auf die GPU passt
        requests.post(rp.OLLAMA_URL, json={"model": rp.MODEL_NAME, "keep_alive": 0}, timeout=30)
    except Exception:
        pass
    st = gen["stufen"]
    fall = {"frage": frage, "hinweis": st["hinweis"], "erklaerung": st["erklaerung"], "loesung": st["loesung"],
            "kontext_chunks": [chunks[i] for i in top4_final]}
    b = {"judge": judge}
    try:
        b["cr"] = ra.berechne_context_relevance(fall, judge)
        if not gen["verweigerung"]:
            b["f"] = ra.berechne_faithfulness(fall, judge)
            b["ar"] = ra.berechne_answer_relevance(fall, judge)
    except Exception as e:
        b["fehler"] = str(e)
    return b


def abschnitt_generierung(gen, chunks, top4_final):
    if not gen["gate"]:
        return f"""<section><h2>7 · Generierung</h2><p>Höchste Kosinus-Ähnlichkeit {gen['bester']:.3f} liegt unter der
Relevanzschwelle {rp.RELEVANZ_SCHWELLE} → kein LLM-Aufruf, feste Verweigerung.</p></section>"""
    st = gen["stufen"]
    import stufen_check as sc
    fall = {"frage": "", "hinweis": st["hinweis"], "loesung": st["loesung"]}
    h3 = sc.H3.findall(st["hinweis"]) if st["hinweis"] else []
    leck = sorted(sc.zahlen_leck({"frage": gen.get("frage", ""), "hinweis": st["hinweis"], "loesung": st["loesung"]})) if st["hinweis"] else []
    anrede = "du" if sc.DU.search(st["hinweis"] + " " + st["loesung"]) else ("Sie" if sc.SIE.search(st["hinweis"] + " " + st["loesung"]) else "–")
    zwei_aufrufe = gen["version"] == "S2-v2"
    hinweis_info = ""
    if zwei_aufrufe:
        quelle = st.get("hinweis_quelle", "")
        hinweis_info = (f'<p class="klein">Version S2-v2: Hinweis in einem zweiten Aufruf erzeugt, der die Lösung kennt '
                        f'(Quelle: <code>{esc(quelle)}</code>).</p>')
        if st.get("hinweis_ueberlegung"):
            hinweis_info += (f'<details><summary>Verdeckte Überlegung des Modells (wird Lernenden nicht gezeigt)</summary>'
                             f'<pre>{esc(st["hinweis_ueberlegung"])}</pre></details>')
    pruef = (f'<table class="schmal"><tr><th>Prüfung (regelbasiert)</th><th>Ergebnis</th></tr>'
             f'<tr><td>Format: beide Marker gefunden</td><td>{"ja" if st["vollstaendig_geparst"] else "nein (ganze Antwort als Lösung)"}</td></tr>'
             f'<tr><td>Modell-Verweigerung erkannt</td><td>{"ja" if gen["verweigerung"] else "nein"}</td></tr>'
             f'<tr><td>Hinweis verweist auf Text, den Lernende nicht sehen</td><td>{esc(", ".join(h3)) if h3 else "nein"}</td></tr>'
             f'<tr><td>Hinweis verrät Zahl aus der Lösung</td><td>{esc(", ".join(leck)) if leck else "nein"}</td></tr>'
             f'<tr><td>Anrede</td><td>{anrede}</td></tr></table>')
    return f"""<section><h2>7 · Generierung (qwen)</h2>
<p>Höchste Kosinus-Ähnlichkeit {gen['bester']:.3f} ≥ Relevanzschwelle {rp.RELEVANZ_SCHWELLE} → das Modell
<code>{esc(rp.MODEL_NAME)}</code> erhält die Frage und die 4 Chunks ({", ".join(esc(chunks[i]["id"]) for i in top4_final)})
mit dem Scaffolding-Prompt <code>{esc(gen['version'])}</code> (Temperatur 0, Seed 42). Dauer {gen['sekunden']:.1f} s.</p>
<details><summary>Vollständiger Prompt anzeigen</summary><pre>{esc(gen['prompt'])}</pre></details>
<details><summary>Rohausgabe des Modells</summary><pre>{esc(gen['roh'])}</pre></details>
<div class="stufen"><div class="stufe-box"><div class="st-titel">Stufe 1 · Hinweis</div>{esc(st['hinweis']) or "–"}</div>
<div class="stufe-box"><div class="st-titel">Stufe 2 · Lösung</div>{esc(st['loesung'])}</div></div>
{hinweis_info}{pruef}</section>"""


def abschnitt_bewertung(gen, bw, frage):
    if bw is None:
        return ""
    teile = [f"""<section><h2>8 · Bewertung mit RAGAS (Richter: <code>{esc(bw['judge'])}</code>)</h2>
<p>Ein zweites, anderes Sprachmodell prüft die Antwort <b>nur gegen die 4 abgerufenen Chunks</b> (Kontext c),
nicht gegen das ganze Handbuch und nicht gegen eigenes Wissen. Temperatur 0, Seed 42.</p>"""]
    if "fehler" in bw:
        teile.append(f'<p style="color:#c2364a">Fehler beim Richter: {esc(bw["fehler"])} (z. B. Zeitüberschreitung).</p>')

    # Faithfulness
    if gen["verweigerung"]:
        teile.append("<h3>Faithfulness und Answer Relevance</h3><p>Die Antwort ist eine Verweigerung → beide sind nicht "
                     "definiert; die Antwort wird als Verweigerung gezählt, nicht bewertet.</p>")
    elif "f" in bw:
        score, details, verworfen = bw["f"]
        n_ja = sum(1 for d in details if d["urteil"] is True)
        n_gueltig = sum(1 for d in details if d["urteil"] is not None)
        zeilen = "".join(
            f'<tr><td>{n}</td><td>{esc(d["aussage"])}</td><td><b style="color:{"#1f9e6e" if d["urteil"] else "#c2364a"}">'
            f'{"JA" if d["urteil"] else ("NEIN" if d["urteil"] is False else "?")}</b></td><td class="klein">{esc(d["begruendung"])}</td></tr>'
            for n, d in enumerate(details, 1))
        formel = (f"F = {n_ja} / {n_gueltig} = {score:.2f}" if score is not None else "F nicht berechenbar")
        teile.append(f"""<h3>Faithfulness: Ist jede Aussage durch den Kontext gestützt?</h3>
<p class="formel">F = |{{ sᵢ : Urteil(sᵢ) = JA }}| / |S|</p>
<p><b>Schritt 1:</b> Der Richter zerlegt die sichtbare Antwort (Hinweis + Lösung) in Einzelaussagen S
({verworfen} Meta-Aussagen wie „Überlege …“ verworfen). <b>Schritt 2:</b> Jede Aussage wird einzeln gegen c geprüft:
JA = steht im Kontext oder folgt direkt daraus; NEIN = fehlt, widerspricht oder verallgemeinert.</p>
<table><tr><th>#</th><th>Aussage sᵢ</th><th>Urteil</th><th>Begründung des Richters</th></tr>{zeilen}</table>
<p class="ergebnis">{formel}</p>""")

    # Answer Relevance
    if not gen["verweigerung"] and "ar" in bw:
        score, roh, ausweichend, paare = bw["ar"]
        zeilen = "".join(f'<tr><td>q{n}</td><td>{esc(q)}</td><td>{c:.3f}</td></tr>' for n, (q, c) in enumerate(paare, 1))
        summe = " + ".join(f"{c:.3f}" for _, c in paare)
        if roh is None:
            formel = "AR nicht berechenbar (keine Fragen erzeugt)"
        elif ausweichend:
            formel = f"Rohwert = ({summe}) / {len(paare)} = {roh:.2f} · Antwort ausweichend → AR = 0"
        else:
            formel = f"AR = ({summe}) / {len(paare)} = {score:.2f}"
        teile.append(f"""<h3>Answer Relevance: Passt die Lösung zur Frage?</h3>
<p class="formel">AR = (1/n) · Σ cos(E(qᵢ), E(q))</p>
<p>Der Richter sieht <b>nur die Lösung</b> (nicht die Frage) und formuliert {len(paare)} Fragen qᵢ, auf die sie passt.
Je ähnlicher diese der Originalfrage q sind (Kosinus der Embeddings), desto besser trifft die Lösung die Frage.
Originalfrage q: „{esc(frage)}“</p>
<table class="schmal"><tr><th></th><th>Rekonstruierte Frage qᵢ</th><th>cos(qᵢ, q)</th></tr>{zeilen}</table>
<p>Zusätzliche Prüfung (eigener Aufruf): Ist die Antwort <b>ausweichend</b>, also allgemein, obwohl ein konkreter Wert,
eine Liste oder ein Vorgehen gefragt war? → <b>{"JA" if ausweichend else ("NEIN" if ausweichend is False else "nicht lesbar")}</b></p>
<p class="ergebnis">{formel}</p>""")

    # Context Relevance
    if "cr" in bw:
        score, n, benoetigt, saetze, begruendung = bw["cr"]
        menge = set(benoetigt or [])
        zeilen = "".join(f'<tr{" class=erw-zeile" if i in menge else ""}><td>[{i}]</td><td>{esc(satz)}</td>'
                         f'<td>{"benötigt" if i in menge else ""}</td></tr>' for i, satz in enumerate(saetze, 1))
        formel = (f"CR = {len(menge)} / {n} = {score:.2f}" if score is not None else "CR nicht berechenbar (Urteil unlesbar)")
        teile.append(f"""<h3>Context Relevance: Wie viel des Kontexts wird gebraucht?</h3>
<p class="formel">CR = Anzahl benötigter Sätze / Anzahl der Sätze in c</p>
<p>Die 4 Chunks werden in nummerierte Sätze zerlegt (durch Überlappung doppelte Sätze zählen einmal); der Richter
nennt die Nummern der Sätze, die zur Beantwortung nötig sind. Begründung: <i>{esc(begruendung)}</i></p>
<details><summary>Alle {n} Sätze anzeigen</summary><table><tr><th>Nr.</th><th>Satz</th><th></th></tr>{zeilen}</table></details>
<p class="ergebnis">{formel}</p>
<p class="klein">CR ist konstruktionsbedingt niedrig (meist werden 1–2 von 6–10 Sätzen gebraucht); die Metrik dient dem Vergleich von Versionen.</p>""")

    # Einordnung
    if not gen["verweigerung"] and "f" in bw and bw["f"][0] is not None:
        f, ar = bw["f"][0], bw.get("ar", (None, None, None, []))
        ausw = ar[2]
        if f < 0.5:
            klasse = "kritisch (Faithfulness < 0,5: Quellenbindung verletzt)"
        elif f >= 0.75 and not ausw and ar[0] is not None:
            klasse = "sauber (Faithfulness ≥ 0,75, nicht ausweichend)"
        else:
            klasse = "mittel (weder sauber noch kritisch)"
        teile.append(f'<h3>Einordnung</h3><p class="ergebnis">{klasse}</p>')
    teile.append("</section>")
    return "".join(teile)


def abschnitt_retrieval_metriken(res, chunks, erwartet, top4_final):
    if not erwartet:
        return ""
    if res["rr"] is not None:
        reihen = [int(res["rr"]["kandidaten"][j]) for j in res["rr"]["neu"]] + \
                 [int(i) for i in res["reihenfolge"][res["rr"]["n"]:]]
    else:
        reihen = [int(i) for i in res["reihenfolge"]]
    ids = [chunks[i]["id"] for i in reihen]
    top4_ids = [chunks[i]["id"] for i in top4_final]
    zeilen = []
    for e in erwartet:
        if e not in ids:
            continue
        r = ids.index(e) + 1
        treffer = r <= 4
        nachbar = treffer or bool(nachbar_ids(e) & set(top4_ids))
        zeilen.append(f"""<tr><td><code>{esc(e)}</code></td><td>{r:,}</td>
<td>{"1 (Treffer)" if treffer else "0 (kein Treffer)"}</td><td>{"1" if nachbar else "0"}</td><td>1/{r:,} = {1 / r:.3f}</td></tr>""")
    if not zeilen:
        return ""
    return f"""<section><h2>9 · Retrieval-Metriken für diese Frage</h2>
<p>Über alle Testfragen gemittelt ergeben sich daraus Recall@4 und MRR (Mean Reciprocal Rank):</p>
<p class="formel">Recall@k = |{{ q : r(q) ≤ k }}| / |Q| &nbsp;&nbsp;&nbsp; MRR = (1/|Q|) · Σ 1/r(q)</p>
<table class="schmal"><tr><th>Erwarteter Chunk</th><th>Rang r nach Reranking</th><th>Beitrag zu Recall@4</th>
<th>… inkl. Nachbar-Chunk</th><th>Beitrag zum MRR</th></tr>{"".join(zeilen)}</table></section>"""


SEITE = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Retrieval erklärt</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
:root{--text:#1d2433;--muted:#5b6475;--rand:#e3e6eb;--hell:#f6f7f9}
body{margin:0 auto;max-width:1400px;padding:16px 24px;font:14px/1.45 system-ui,sans-serif;color:var(--text);background:#fff}
h1{font-size:22px;margin:8px 0}h2{font-size:18px;margin:0 0 8px}h3{font-size:14px;margin:12px 0 6px}
section{border:1px solid var(--rand);border-radius:10px;padding:16px 18px;margin:16px 0}
table{border-collapse:collapse;width:100%;margin:8px 0}th,td{border-bottom:1px solid var(--rand);padding:6px 8px;text-align:left;vertical-align:top}
th{background:var(--hell);font-weight:600}table.schmal{width:auto}td.r{font-weight:700;width:40px}
td.text{max-width:560px;color:#333}.thema{color:var(--muted);font-size:12px}.klein{font-size:12px;color:var(--muted)}
.bar{display:inline-block;height:10px;border-radius:2px;vertical-align:middle;margin-right:1px}
mark{background:#c8f0dc;padding:0 1px;border-radius:2px}
.erw-zeile{background:#fff6d6}.erw{background:#ffe48a;padding:0 4px;border-radius:3px}
.zwei{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:18px;align-items:start}
.pipeline{display:flex;align-items:center;flex-wrap:wrap;gap:6px}.stufe{border:1px solid var(--rand);border-radius:8px;padding:8px 10px;background:var(--hell);max-width:260px}
.st-titel{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}.pfeil{font-size:22px;color:var(--muted)}
.netz{height:460px;border:1px solid var(--rand);border-radius:8px}.plot{max-width:100%;height:auto}
figure{margin:0}pre{white-space:pre-wrap;background:var(--hell);padding:10px;border-radius:6px;font-size:12px;max-height:420px;overflow:auto}details{margin:6px 0}summary{cursor:pointer;color:var(--muted)}.formel{font-family:Georgia,serif;font-size:16px;background:#f3f0fb;display:inline-block;padding:6px 12px;border-radius:6px}.ergebnis{font-weight:700;font-size:16px}.stufen{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:10px 0}.stufe-box{border:1px solid var(--rand);border-radius:8px;padding:10px;white-space:pre-wrap}figcaption{font-size:12px;color:var(--muted)}
@media (max-width:900px){.zwei,.stufen{grid-template-columns:1fr}}
</style></head><body>
<h1>Eine Frage von Anfang bis Ende: Retrieval, Generierung, Bewertung</h1>
<p><b>Frage:</b> „__FRAGE__“ · Wissensbasis: __N__ Chunks (kb_hash __KB__) · Parameter wie Version V3 (hybrid_kg_rr)</p>
__INHALT__
<script>
if (window.GRAPH_DATEN && window.vis) {
  new vis.Network(document.getElementById("graphnetz"),
    {nodes: new vis.DataSet(GRAPH_DATEN.nodes), edges: new vis.DataSet(GRAPH_DATEN.edges)},
    {nodes:{shape:"dot",scaling:{min:8,max:36},font:{size:13}}, physics:{stabilization:true,barnesHut:{springLength:130}},
     interaction:{hover:true}});
}
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frage")
    ap.add_argument("--erwartet", default="", help="erwartete Chunk-ID(s), kommagetrennt (sonst aus testfragen_v1.csv)")
    ap.add_argument("--rrf-k", type=int, default=None, help=f"Standard: RRF_K aus rag_pipeline ({rp.RRF_K})")
    ap.add_argument("--top", type=int, default=8, help="Zeilen pro Tabelle")
    ap.add_argument("--knoten", type=int, default=30, help="Begriffe im Graph-Bild")
    ap.add_argument("--ohne-reranker", action="store_true")
    ap.add_argument("--ohne-generierung", action="store_true", help="nur Retrieval (ohne qwen und Richter)")
    ap.add_argument("--ohne-bewertung", action="store_true", help="Generierung ja, RAGAS-Bewertung nein")
    ap.add_argument("--scaffolding", default=None, help=f"Stufen-Prompt (Standard: {rp.SCAFFOLDING_VERSION})")
    ap.add_argument("--judge", default=None, help="Richter-Modell (Standard: wie ragas_auswertung.py)")
    ap.add_argument("--kb", default="knowledge_base.json")
    args = ap.parse_args()
    if args.scaffolding:
        rp.SCAFFOLDING_VERSION = args.scaffolding
    if args.rrf_k is not None:
        rp.RRF_K = args.rrf_k

    chunks = rp.lade_wissensbasis(args.kb)
    erwartet = [e.strip() for e in args.erwartet.split(",") if e.strip()] or erwarteten_chunk_finden(args.frage)
    print(f"{len(chunks)} Chunks geladen; Berechnung läuft (Embeddings, BM25, Graph"
          + ("" if args.ohne_reranker else ", Cross-Encoder auf der CPU") + ") …")
    res = berechne(args.frage, chunks, not args.ohne_reranker)

    if res["rr"] is not None:
        top4_final = [int(res["rr"]["kandidaten"][j]) for j in res["rr"]["neu"][:4]]
        methode = "hybrid_kg_rr"
    else:
        top4_final = [int(i) for i in res["reihenfolge"][:4]]
        methode = "hybrid_kg"

    # Gegenprobe mit der echten Pipeline (ohne erneutes Reranking: Vorstufe vergleichen)
    _, alle = rp.retrieval(args.frage, chunks, top_k=4, methode="hybrid_kg")
    pipeline_ids = [c["id"] for c in alle[:50]]
    eigene_ids = [chunks[i]["id"] for i in res["reihenfolge"][:50]]
    if pipeline_ids != eigene_ids:
        print("WARNUNG: Reihenfolge weicht von rag_pipeline.retrieval(hybrid_kg) ab – Seite nicht verwenden.")
    else:
        print("Gegenprobe: erste Stufe identisch mit rag_pipeline.retrieval (hybrid_kg).")

    gen = bw = None
    if not args.ohne_generierung:
        print(f"Generierung mit {rp.MODEL_NAME} ({rp.SCAFFOLDING_VERSION}) …")
        gen = generierung(args.frage, res, chunks, top4_final)
        gen["frage"] = args.frage
        if gen["gate"] and not args.ohne_bewertung:
            import ragas_auswertung as ra
            judge = args.judge or ra.JUDGE_MODELL_STANDARD
            print(f"Bewertung mit Richter {judge} (dauert einige Minuten) …")
            bw = bewertung(args.frage, gen, chunks, top4_final, judge)

    inhalt = "".join([
        abschnitt_ueberblick(args.frage, res, chunks, erwartet, top4_final),
        abschnitt_dense(res, chunks, erwartet, args.top),
        abschnitt_bm25(args.frage, res, chunks, erwartet, args.top),
        abschnitt_graph(args.frage, res, chunks, erwartet, args.top, args.knoten),
        abschnitt_rrf(res, chunks, erwartet, args.top),
        abschnitt_reranker(res, chunks, erwartet, args.top),
        abschnitt_vergleich(res, chunks, erwartet, top4_final),
        abschnitt_generierung(gen, chunks, top4_final) if gen else "",
        abschnitt_bewertung(gen, bw, args.frage) if gen and gen["gate"] else "",
        abschnitt_retrieval_metriken(res, chunks, erwartet, top4_final),
    ])
    seite = (SEITE.replace("__FRAGE__", esc(args.frage)).replace("__N__", f"{len(chunks):,}")
             .replace("__KB__", esc(rp.berechne_kb_hash(args.kb))).replace("__INHALT__", inhalt))
    slug = re.sub(r"[^a-z0-9äöüß]+", "_", args.frage.lower())[:40].strip("_")
    rp.LOG_VERZEICHNIS.mkdir(exist_ok=True)
    pfad = rp.LOG_VERZEICHNIS / f"frage_erklaerung_{slug}.html"
    pfad.write_text(seite, encoding="utf-8")
    print(f"Top 4 an qwen ({methode}): {', '.join(chunks[i]['id'] for i in top4_final)}")
    print(f"Seite: {pfad}  (im Browser öffnen; enthält Handbuch-Auszüge -> nicht ins Git)")


if __name__ == "__main__":
    main()