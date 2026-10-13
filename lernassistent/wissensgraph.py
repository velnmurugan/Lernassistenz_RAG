"""
wissensgraph.py
---------------
V2: Konzept-Wissensgraph als dritte Retrieval-Liste neben dense und BM25.

Aufbau (einmalig, danach aus cache/ geladen):
  Knoten   = Fachbegriffe der Wissensbasis (deutsche Substantive, Abkürzungen,
             Normen wie "DIN EN 13001-2"), normalisiert per Snowball-Stamm.
  Kanten   = (a) Ko-Vorkommen: zwei Begriffe stehen in mindestens
                 KG_MIN_KOOKKURRENZ gemeinsamen Chunks
                 (Gewicht = gemeinsame Chunks / sqrt(df_i * df_j))
             (b) Synonymie/Nähe: Kosinus der Begriffs-Embeddings (dasselbe
                 MiniLM-Modell wie im dense Retrieval) >= KG_SYN_SCHWELLE.
                 Das ist die Fusion mit den bestehenden Embeddings: der Graph
                 verbindet z. B. "Zweihandschaltung" mit "Zweihandverriegelung",
                 auch wenn beide nie im selben Chunk stehen.
  Begriff -> Chunk: jeder Knoten kennt die Chunk-IDs, in denen er vorkommt.

Retrieval (pro Frage):
  1. Start-Knoten aus der Frage: exakte Begriffs-Treffer (Stamm), nicht
     gefundene Fragewörter über ihren nächsten Begriff im Embedding-Raum,
     zusätzlich die Begriffe, die der GANZEN Frage im Embedding-Raum am
     nächsten sind. Gewichtet mit IDF (seltene Fachbegriffe zählen mehr).
  2. Personalized PageRank über den Begriffsgraphen (Haveliwala 2002):
     verteilt Relevanz von den Start-Knoten auf verwandte Begriffe.
  3. Chunk-Score = Summe (PPR-Masse * IDF) der Begriffe im Chunk,
     normalisiert mit sqrt(Anzahl Begriffe im Chunk).
  Diese Rangliste fließt in rag_pipeline.retrieval() per RRF zu dense + BM25
  ("hybrid_kg") oder allein ("graph").

Vorbild: HippoRAG (Gutiérrez et al., NeurIPS 2024) — Begriffsgraph + Synonymie-
Kanten aus Embeddings + Personalized PageRank ab den Frage-Begriffen.
Unterschied: Knoten hier per Regeln extrahiert (Großschreibung, Abkürzungen,
Normen) statt per LLM-OpenIE. Begründung: LLM-Extraktion über ~32.000 Chunks
wären mit qwen3.5:9b auf der RTX 3070 ca. 20+ Stunden; die regelbasierte
Variante baut in wenigen Minuten und ist deterministisch. Eine LLM-extrahierte
Variante (Tripel mit Relationen wie "ist_Teil_von") ist als V2b möglich, falls
V2a zeigt, dass der Graph-Ansatz grundsätzlich hilft.
Weitere Bezüge: GraphRAG (Edge et al. 2024, Microsoft), LightRAG (Guo et al. 2024).

Alle Schwellen unten sind Startwerte — mit retrieval_vergleich.py kalibrieren.

Start (Diagnose/Visualisierung):
  python wissensgraph.py --stats
  python wissensgraph.py --frage "Was ist eine Zweihandverriegelung?"
    -> evaluationsdaten/graph_<frage>.html (im Browser öffnen)
"""
import argparse
import collections
import functools
import hashlib
import html
import json
import math
import pickle
import re
from pathlib import Path

import numpy as np
from scipy import sparse

import rag_pipeline

# ---------------------------------------------------------------------------
# Parameter (Startwerte, siehe Modul-Docstring)
# ---------------------------------------------------------------------------
KG_VERSION = "kg-v3"            # bei Logikänderung erhöhen -> Cache wird neu gebaut
KG_MAX_DF_ANTEIL = 0.05         # Begriffe in > 5 % aller Chunks sind zu allgemein
KG_MIN_NOMEN_ANTEIL = 0.2       # Begriff nur, wenn >= 20 % seiner Vorkommen mitten im Satz GROSS
                                # geschrieben sind (filtert Verben wie "bringt" -> "Bringt" in Überschriften)
KG_MIN_KOOKKURRENZ = 2          # Ko-Vorkommens-Kante erst ab 2 gemeinsamen Chunks
KG_KOOK_NACHBARN = 20           # je Begriff nur die 20 stärksten Ko-Vorkommens-Kanten
                                # (ohne Grenze hatten "C", "DIN", "System" Grad 2000–5000 -> PageRank
                                # lief in allgemeine Knoten ab statt zu verwandten Fachbegriffen)
KG_SYN_MODUS = "aus"            # "aus" | "schreibvariante" | "embedding" (siehe _synonymie_kanten)
                                # Befund retrieval_vergleich (25 Fragen, hybrid_kg@5): R@4 aus 13,
                                # schreibvariante 12, embedding 12 -> Synonymie-Kanten ohne messbaren
                                # Nutzen; Gewinn kommt aus Ko-Vorkommen + PageRank. Einfachste Variante gewählt.
KG_SYN_JACCARD = 0.45           # Mindest-Zeichen-Trigramm-Überlappung im Modus "schreibvariante"
KG_SYN_SCHWELLE = 0.85          # Kosinus für Synonymie-Kanten (0.80 ergab 110k Kanten, zu locker)
KG_SYN_NACHBARN = 3             # max. Synonymie-Kanten pro Begriff
KG_SYN_MIN_DF = 2               # Synonymie nur zwischen Begriffen mit df >= 2 (Rechenzeit)
KG_WORT_SCHWELLE = 0.75         # Fragewort ohne exakten Treffer -> nächster Begriff ab diesem Kosinus
KG_FRAGE_SCHWELLE = 0.50        # Begriffe nahe an der ganzen Frage ab diesem Kosinus
KG_FRAGE_NACHBARN = 0           # ... höchstens so viele (0 = aus; Einzelwort-Embeddings unzuverlässig, s. kg-v3)
KG_FRAGE_GEWICHT = 0.5          # ... mit halbem Gewicht gegenüber exakten Treffern
KG_DAEMPFUNG = 0.5              # PPR-Dämpfung wie HippoRAG (0.5 = bleibt nah an den Start-Knoten)
KG_ITERATIONEN = 30

CACHE_VERZEICHNIS = rag_pipeline.BM25_CACHE_VERZEICHNIS

# Großgeschriebene Wörter, die im Deutschen keine Fachbegriffe sind
# (Satzanfänge werden zusätzlich über die Mitte-des-Satzes-Regel gefiltert).
EXTRA_STOPPWOERTER = set("""
abb abbildung tab tabelle bild seite seiten kapitel abschnitt abschn bzw vgl kap nr gl bd hrsg aufl ca usw etc beispiel beispiele fall fälle art weise
teil teile ende anfang grund frage fragen antwort aufgabe aufgaben lösung übung übungen hinweis
literatur quelle quellen anhang verzeichnis inhalt inhaltsverzeichnis einleitung zusammenfassung
erkläre nenne beschreibe begründe berechne bestimme gib zeige vergleiche warum wozu wofür wann
welche welcher welches weshalb wieso daher dabei hierbei somit deshalb außerdem zudem jedoch
allerdings ebenfalls danach anschließend dazu darüber hierzu dadurch falls sobald während nachdem
bevor beide beiden viele einige weitere weiteren neue erste ersten zweite dritte siehe bitte
""".split())

_NORM_RE = re.compile(r"\b(?:DIN|EN|ISO|IEC|VDI|VDE)(?:\s+(?:EN|ISO|IEC|VDE))*\s+\d+(?:[-–.:]\d+)*")
_BEGRIFF_RE = re.compile(r"\b[A-ZÄÖÜ][A-Za-zÄÖÜäöüß0-9]*(?:-[A-Za-zÄÖÜäöüß0-9]+)*")
_FRAGEWORT_RE = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+(?:-[A-Za-zÄÖÜäöüß0-9]+)*")
_SATZENDE_RE = re.compile(r"(?:^|[.!?:•▪\-–])\s*$")

# CAN bewusst nicht enthalten (CAN-Bus ist ein Fachbegriff)
_STEUERZEICHEN_RE = re.compile(r"^(?:NUL|SOH|STX|ETX|EOT|ENQ|ACK|BEL|DLE|DC[1-4]|NAK|ETB)(?![a-zäöü])")

_KLEINWORT_RE = re.compile(r"(?<![\w-])[a-zäöüß][a-zäöüß0-9]*(?:-[a-zäöüß0-9]+)*")

_graph_cache = {}


def parameter():
    """Für lauf_<ID>.json (Reproduzierbarkeit)."""
    return {k: v for k, v in globals().items() if k.startswith("KG_")}


# ---------------------------------------------------------------------------
# Begriffs-Extraktion
# ---------------------------------------------------------------------------
@functools.lru_cache(maxsize=500_000)
def _stamm(wort):
    rag_pipeline.tokenisiere("")  # initialisiert den gemeinsamen Snowball-Stemmer
    return rag_pipeline._stemmer.stemWord(wort.lower())


def begriffs_schluessel(wort):
    """'Zweihandverriegelungen' -> 'zweihandverriegel', 'D-Anteil' -> 'd-anteil'."""
    teile = [t for t in wort.split("-") if t]
    return "-".join(_stamm(t) for t in teile)


def _ist_stoppwort(wort):
    w = wort.lower()
    return w in rag_pipeline.BM25_STOPPWOERTER or w in EXTRA_STOPPWOERTER


def extrahiere_begriffe(text):
    """Liefert [(schluessel, oberflaeche, mitten_im_satz)] für einen Chunk-Text."""
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)  # Silbentrennung wie in tokenisiere()
    treffer = []
    for m in _NORM_RE.finditer(text):
        oberflaeche = re.sub(r"\s+", " ", m.group(0))
        treffer.append((oberflaeche.lower().replace("–", "-"), oberflaeche, True))
    for m in _BEGRIFF_RE.finditer(text):
        wort = m.group(0).strip("-")
        if len(wort) < 2 or (len(wort) < 3 and not wort.isupper()):
            continue  # Einzelbuchstaben = Formelzeichen (C, N, F, W …)
        if _STEUERZEICHEN_RE.match(wort):
            continue  # Artefakt der PDF-Extraktion: ASCII-Steuerzeichen als Text ("NUL1C2", "SOH" …)
        if wort.isdigit() or _ist_stoppwort(wort):
            continue
        davor = text[max(0, m.start() - 3):m.start()]
        mitten = not _SATZENDE_RE.search(davor) and m.start() > 0
        treffer.append((begriffs_schluessel(wort), wort, mitten))
    return treffer


# ---------------------------------------------------------------------------
# Aufbau
# ---------------------------------------------------------------------------
def _fingerabdruck(chunks):
    h = hashlib.sha256()
    h.update(json.dumps(parameter(), sort_keys=True).encode())
    h.update(rag_pipeline.EMBEDDING_MODELL_NAME.encode())
    for c in chunks:
        h.update(c["text"].encode("utf-8"))
        h.update(b"\x1e")
    return h.hexdigest()[:12]


def _embedde(texte):
    modell = rag_pipeline._lade_embedding_modell()
    return modell.encode(list(texte), convert_to_numpy=True, normalize_embeddings=True,
                         batch_size=256, show_progress_bar=len(texte) > 2000).astype(np.float32)


def _trigramme(wort):
    w = f" {wort.lower().replace('-', '')} "
    return {w[i:i + 3] for i in range(len(w) - 2)}


def trigramm_jaccard(a, b):
    ta, tb = _trigramme(a), _trigramme(b)
    return len(ta & tb) / max(1, len(ta | tb))


def _synonymie_kanten(emb, kandidaten, labels):
    """Top-KG_SYN_NACHBARN Nachbarn je Begriff (nur kandidaten) mit Kosinus >= Schwelle.

    Befund kg-v2 (echte Wissensbasis): Kosinus einzelner Wörter mit MiniLM ist auch
    oberhalb 0.95 unzuverlässig ("Bogenzähnen ~ Gleitscheiben 0.97", "Blättchendicke ~
    Stapelkatze 0.96") — das Modell ist auf Sätze trainiert, isolierte Komposita landen
    eng beieinander. Modus "schreibvariante" verlangt daher zusätzlich Zeichen-Überlappung
    (Trigramm-Jaccard >= KG_SYN_JACCARD): behält "Prinzipien ~ Prinzips",
    "Reihenfolgenverriegelung ~ Reihenfolgeverriegelung", verwirft Zufallspaare.
    Echte Synonyme ohne gemeinsame Zeichen ("Kostenerhöhung ~ Kostensteigerung")
    gehen dabei verloren — bewusster Tausch Präzision gegen Abdeckung."""
    zeilen, spalten, werte = [], [], []
    if KG_SYN_MODUS == "aus":
        n = emb.shape[0]
        return sparse.csr_matrix((n, n))
    E = emb[kandidaten]
    for start in range(0, len(kandidaten), 2048):
        S = E[start:start + 2048] @ E.T
        for i_lokal in range(S.shape[0]):
            i = start + i_lokal
            S[i_lokal, i] = -1.0
            k = min(KG_SYN_NACHBARN, S.shape[1] - 1)
            if k <= 0:
                continue
            top = np.argpartition(-S[i_lokal], k)[:k]
            for j in top:
                if S[i_lokal, j] >= KG_SYN_SCHWELLE and (
                        KG_SYN_MODUS == "embedding"
                        or trigramm_jaccard(labels[kandidaten[i]], labels[kandidaten[j]]) >= KG_SYN_JACCARD):
                    zeilen.append(kandidaten[i])
                    spalten.append(kandidaten[j])
                    werte.append(float(S[i_lokal, j]))
    n = emb.shape[0]
    M = sparse.csr_matrix((werte, (zeilen, spalten)), shape=(n, n))
    return M.maximum(M.T)  # symmetrisch


def _behalte_top_n(M, n):
    """Je Zeile nur die n stärksten Kanten; danach symmetrisch (Vereinigung)."""
    M = M.tocsr()
    z, sp, w = [], [], []
    for i in range(M.shape[0]):
        a, b = M.indptr[i], M.indptr[i + 1]
        if a == b:
            continue
        daten, idx = M.data[a:b], M.indices[a:b]
        if b - a > n:
            top = np.argpartition(-daten, n)[:n]
            daten, idx = daten[top], idx[top]
        z.extend([i] * len(idx))
        sp.extend(idx.tolist())
        w.extend(daten.tolist())
    R = sparse.csr_matrix((w, (z, sp)), shape=M.shape)
    return R.maximum(R.T).tocsr()


def baue_graph(chunks):
    print(f"Wissensgraph wird gebaut ({len(chunks)} Chunks) …")
    n_chunks = len(chunks)
    pro_chunk, oberflaechen, mitten = [], collections.defaultdict(collections.Counter), collections.Counter()
    klein = collections.Counter()
    for c in chunks:
        for w in _KLEINWORT_RE.findall(c["text"]):
            if len(w) >= 3:
                klein[begriffs_schluessel(w)] += 1
        schluessel = set()
        for s, o, mi in extrahiere_begriffe(c["text"]):
            schluessel.add(s)
            oberflaechen[s][o] += 1
            mitten[s] += mi
        pro_chunk.append(schluessel)

    df = collections.Counter(s for menge in pro_chunk for s in menge)
    max_df = max(2, int(KG_MAX_DF_ANTEIL * n_chunks))
    # Nur Begriffe, die mitten im Satz großgeschrieben vorkommen (filtert Satzanfänge wie
    # "Erkläre") UND überwiegend groß geschrieben werden (filtert Verben/Adjektive, die in
    # Überschriften groß stehen: "Bringt" hat hunderte kleingeschriebene Vorkommen "bringt").
    vokabular = sorted(s for s, d in df.items() if d <= max_df and mitten[s] >= 1
                       and mitten[s] >= KG_MIN_NOMEN_ANTEIL * (mitten[s] + klein[s]))
    print(f"  Wortart-Filter: {sum(1 for s in df if mitten[s] >= 1 and mitten[s] < KG_MIN_NOMEN_ANTEIL * (mitten[s] + klein[s]))} "
          "Kandidaten verworfen (überwiegend kleingeschrieben)")
    index = {s: i for i, s in enumerate(vokabular)}
    labels = [oberflaechen[s].most_common(1)[0][0] for s in vokabular]
    df_arr = np.array([df[s] for s in vokabular], dtype=np.float64)
    idf = np.log(n_chunks / df_arr)

    z, sp = [], []
    for ci, menge in enumerate(pro_chunk):
        for s in menge:
            if s in index:
                z.append(ci)
                sp.append(index[s])
    A = sparse.csr_matrix((np.ones(len(z), dtype=np.float32), (z, sp)), shape=(n_chunks, len(vokabular)))

    # Ko-Vorkommen
    C = (A.T @ A).tocsr().astype(np.float64)
    C.setdiag(0)
    C.data[C.data < KG_MIN_KOOKKURRENZ] = 0
    C.eliminate_zeros()
    Ccoo = C.tocoo()
    gew = Ccoo.data / np.sqrt(df_arr[Ccoo.row] * df_arr[Ccoo.col])
    K = _behalte_top_n(sparse.csr_matrix((gew, (Ccoo.row, Ccoo.col)), shape=C.shape), KG_KOOK_NACHBARN)

    print(f"  {len(vokabular)} Begriffe, {K.nnz // 2} Ko-Vorkommens-Kanten; Begriffs-Embeddings …")
    emb = _embedde(labels)
    # Keine Synonymie für Begriffe mit Ziffern: "DIN EN ISO 14528-1" und "… 14529-1" sind
    # im Embedding-Raum fast identisch (1.00), inhaltlich aber verschiedene Normen.
    ohne_ziffer = np.array([not re.search(r"\d", l) for l in labels])
    kandidaten = np.where((df_arr >= KG_SYN_MIN_DF) & ohne_ziffer)[0]
    S = _synonymie_kanten(emb, kandidaten, labels)
    print(f"  {S.nnz // 2} Synonymie-Kanten (Kosinus >= {KG_SYN_SCHWELLE})")

    W = (K + S).tocsr()
    zeilensumme = np.asarray(W.sum(axis=1)).ravel()
    inv = np.divide(1.0, zeilensumme, out=np.zeros_like(zeilensumme), where=zeilensumme > 0)
    P = sparse.diags(inv) @ W  # Übergangsmatrix (zeilennormiert)

    begriffe_pro_chunk = np.asarray(A.sum(axis=1)).ravel()
    return {
        "version": KG_VERSION, "vokabular": vokabular, "index": index, "labels": labels,
        "df": df_arr, "idf": idf, "A": A, "K": K, "S": S, "PT": P.T.tocsr(),
        "haengend": zeilensumme == 0, "emb": emb,
        "chunk_norm": np.sqrt(np.maximum(begriffe_pro_chunk, 1.0)),
        "chunk_ids": [c.get("id", str(i)) for i, c in enumerate(chunks)],
    }


def lade_graph(chunks):
    """Speicher-Cache pro Prozess, Platten-Cache pro Inhalt + Parameter."""
    fp = _fingerabdruck(chunks)
    if fp not in _graph_cache:
        CACHE_VERZEICHNIS.mkdir(exist_ok=True)
        datei = CACHE_VERZEICHNIS / f"wissensgraph_{fp}.pkl"
        if datei.exists():
            with open(datei, "rb") as f:
                g = pickle.load(f)
        else:
            g = baue_graph(chunks)
            with open(datei, "wb") as f:
                pickle.dump(g, f, protocol=pickle.HIGHEST_PROTOCOL)
            print(f"  gespeichert: {datei}")
        g["fingerabdruck"] = fp
        _graph_cache[fp] = g
    return _graph_cache[fp]


# ---------------------------------------------------------------------------
# Abfrage
# ---------------------------------------------------------------------------
def start_knoten(frage, g, frage_embedding=None):
    """-> dict {begriffs_index: (gewicht, herkunft)} ; herkunft = exakt | wort | frage"""
    seeds = {}
    offen = []
    if not g["vokabular"]:
        return seeds
    for m in _NORM_RE.finditer(frage):
        s = re.sub(r"\s+", " ", m.group(0)).lower().replace("–", "-")
        if s in g["index"]:
            seeds[g["index"][s]] = (g["idf"][g["index"][s]], "exakt")
    for wort in _FRAGEWORT_RE.findall(frage):
        if len(wort) < 3 or _ist_stoppwort(wort):
            continue
        i = g["index"].get(begriffs_schluessel(wort))
        if i is not None:
            seeds[i] = (g["idf"][i], "exakt")
        elif len(wort) >= 4:
            offen.append(wort)

    if offen:  # z. B. Tippvarianten, Komposita-Varianten; gleiche Doppelbedingung wie Synonymie
        E = _embedde(offen)
        sims = E @ g["emb"].T
        for wort, zeile in zip(offen, sims):
            for j in np.argsort(-zeile)[:10]:
                j = int(j)
                if zeile[j] < KG_WORT_SCHWELLE:
                    break
                if trigramm_jaccard(wort, g["labels"][j]) >= KG_SYN_JACCARD and j not in seeds:
                    seeds[j] = (float(zeile[j]) * g["idf"][j], "wort")
                    break

    if KG_FRAGE_NACHBARN <= 0:
        return seeds
    if frage_embedding is None:
        frage_embedding = _embedde([frage])[0]
    sims = g["emb"] @ np.asarray(frage_embedding, dtype=np.float32)
    for j in np.argsort(-sims)[:KG_FRAGE_NACHBARN]:
        if sims[j] >= KG_FRAGE_SCHWELLE and int(j) not in seeds:
            seeds[int(j)] = (KG_FRAGE_GEWICHT * float(sims[j]) * g["idf"][j], "frage")
    return seeds


def personalisierter_pagerank(g, seeds):
    n = len(g["vokabular"])
    p = np.zeros(n)
    for i, (w, _) in seeds.items():
        p[i] = w
    if p.sum() <= 0:
        return p
    p /= p.sum()
    r = p.copy()
    for _ in range(KG_ITERATIONEN):
        haengend = r[g["haengend"]].sum()
        r = (1 - KG_DAEMPFUNG) * p + KG_DAEMPFUNG * (g["PT"] @ r + haengend * p)
    return r


def graph_scores(frage, chunks, frage_embedding=None, details=False):
    """Score je Chunk (gleiche Reihenfolge wie chunks). 0 = Chunk ohne Bezug zum Graphen."""
    g = lade_graph(chunks)
    seeds = start_knoten(frage, g, frage_embedding)
    r = personalisierter_pagerank(g, seeds)
    scores = (g["A"] @ (r * g["idf"])) / g["chunk_norm"]
    scores = np.asarray(scores, dtype=np.float64).ravel()
    if details:
        return scores, {"seeds": seeds, "ppr": r, "graph": g}
    return scores


# ---------------------------------------------------------------------------
# Diagnose & Visualisierung
# ---------------------------------------------------------------------------
def statistik(chunks):
    g = lade_graph(chunks)
    grad = np.asarray(((g["K"] + g["S"]) > 0).sum(axis=1)).ravel()
    ohne = int((np.asarray(g["A"].sum(axis=1)).ravel() == 0).sum())
    print(f"Begriffe: {len(g['vokabular'])}  Ko-Vorkommens-Kanten: {g['K'].nnz // 2}  "
          f"Synonymie-Kanten: {g['S'].nnz // 2}  isolierte Begriffe: {int((grad == 0).sum())}")
    print(f"Chunks ohne Begriff: {ohne}/{len(chunks)}  Fingerabdruck: {g['fingerabdruck']}")
    print("\nHäufigste Begriffe (df):")
    for i in np.argsort(-g["df"])[:25]:
        print(f"  {g['labels'][i]:<35} df={int(g['df'][i]):>4}  Grad={grad[i]}")
    print(f"\nGrad: Median {np.median(grad):.0f}, 99%-Perzentil {np.percentile(grad, 99):.0f}, Max {grad.max()}")
    # Zufallsstichprobe je Kosinus-Band (die Top-Kanten sind fast immer triviale
    # Schreibvarianten mit 1.00 und sagen wenig über die Schwelle aus)
    S = g["S"].tocoo()
    paare = [(i, j, w) for i, j, w in zip(S.row, S.col, S.data) if i < j]
    rng = np.random.default_rng(0)
    for lo, hi in ((KG_SYN_SCHWELLE, 0.90), (0.90, 0.95), (0.95, 1.01)):
        band = [p for p in paare if lo <= p[2] < hi]
        print(f"\nSynonymie-Kanten {lo:.2f}–{min(hi, 1):.2f}: {len(band)} — Zufallsstichprobe:")
        for k in rng.permutation(len(band))[:10]:
            i, j, w = band[k]
            print(f"  {g['labels'][i]:<30} ~ {g['labels'][j]:<30} {w:.2f}")


def exportiere_teilgraph(frage, chunks, pfad, n_knoten=40, top_k=4):
    """Interaktive HTML-Ansicht (vis-network) der Begriffe, die für diese Frage
    die meiste PPR-Masse tragen, plus der Top-k-Chunks des Graphen."""
    scores, d = graph_scores(frage, chunks, details=True)
    g, r, seeds = d["graph"], d["ppr"], d["seeds"]
    knoten = [int(i) for i in np.argsort(-r)[:n_knoten] if r[i] > 0]
    menge = set(knoten)
    farbe = {"exakt": "#eb6834", "wort": "#f0a35e", "frage": "#e8c25a"}
    nodes = []
    for i in knoten:
        herkunft = seeds.get(i, (0, None))[1]
        nodes.append({"id": f"b{i}", "label": g["labels"][i], "value": float(r[i]),
                      "color": farbe.get(herkunft, "#2a78d6"),
                      "title": f"{g['labels'][i]} | PPR={r[i]:.4f} | df={int(g['df'][i])}"
                               + (f" | Start ({herkunft})" if herkunft else "")})
    edges = []
    for M, gestrichelt in ((g["K"], False), (g["S"], True)):
        sub = M[knoten][:, knoten].tocoo()
        for a, b, w in zip(sub.row, sub.col, sub.data):
            if a < b:
                edges.append({"from": f"b{knoten[a]}", "to": f"b{knoten[b]}", "dashes": gestrichelt,
                              "width": 1 + 4 * float(min(w, 1.0)), "title": f"{w:.2f}"})
    for rang, ci in enumerate(np.argsort(-scores)[:top_k], start=1):
        if scores[ci] <= 0:
            break
        cid = g["chunk_ids"][ci]
        text = chunks[ci]["text"][:300]
        nodes.append({"id": f"c{ci}", "label": f"#{rang} {cid}", "shape": "box", "color": "#9aa4b2",
                      "title": html.escape(text)})
        for i in g["A"][ci].indices:
            if int(i) in menge:
                edges.append({"from": f"c{ci}", "to": f"b{int(i)}", "color": {"color": "#9aa4b2"}})

    seite = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Wissensgraph – {html.escape(frage)}</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>body{{margin:0;font-family:system-ui,sans-serif;background:#fff;color:#1d2433}}
header{{padding:10px 16px;border-bottom:1px solid #ddd}}#g{{height:calc(100vh - 70px)}}
.l span{{display:inline-block;width:10px;height:10px;border-radius:50%;margin:0 4px 0 12px}}</style></head>
<body><header><b>Frage:</b> {html.escape(frage)}<div class="l">
<span style="background:#eb6834"></span>Start (exakt)<span style="background:#f0a35e"></span>Start (Wort-Embedding)
<span style="background:#e8c25a"></span>Start (Frage-Embedding)<span style="background:#2a78d6"></span>über PageRank erreicht
<span style="background:#9aa4b2;border-radius:0"></span>Top-Chunks &nbsp;· durchgezogen = Ko-Vorkommen, gestrichelt = Synonymie</div></header>
<div id="g"></div><script>
new vis.Network(document.getElementById("g"),
 {{nodes:new vis.DataSet({json.dumps(nodes, ensure_ascii=False)}),edges:new vis.DataSet({json.dumps(edges, ensure_ascii=False)})}},
 {{nodes:{{shape:"dot",scaling:{{min:8,max:40}},font:{{size:14}}}},physics:{{stabilization:true,barnesHut:{{springLength:140}}}},interaction:{{hover:true}}}});
</script></body></html>"""
    Path(pfad).write_text(seite, encoding="utf-8")
    print("Start-Begriffe:", ", ".join(f"{g['labels'][i]} ({h})" for i, (_, h) in
                                       sorted(seeds.items(), key=lambda t: -t[1][0])))
    print("Top-Chunks Graph:", ", ".join(g["chunk_ids"][ci] for ci in np.argsort(-scores)[:top_k]
                                         if scores[ci] > 0) or "— (keine Start-Begriffe gefunden)")
    print(f"Visualisierung: {pfad}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_boege.json")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--frage")
    ap.add_argument("--knoten", type=int, default=40)
    args = ap.parse_args()
    chunks = rag_pipeline.lade_wissensbasis(args.kb)
    if args.stats or not args.frage:
        statistik(chunks)
    if args.frage:
        slug = re.sub(r"[^a-z0-9äöüß]+", "_", args.frage.lower())[:40].strip("_")
        exportiere_teilgraph(args.frage, chunks, rag_pipeline.LOG_VERZEICHNIS / f"graph_{slug}.html",
                             n_knoten=args.knoten)


if __name__ == "__main__":
    main()