"""
diagnose_fehlerfaelle.py
------------------------
Zwei Diagnosen aus dem Vergleich mit/ohne RAG (RAGVGL-FISCHER, 14 Oct 2026). Ändert nichts, gibt nur aus.

T1  Einheitenfehler: Lösung "0,02857 Ω·m" statt Ω·mm²/m. Geprüft wird,
    (a) ob die MinerU-Extraktion (content_list) die Einheit im Tabellenkopf enthält,
    (b) in welchem Tabellen-Chunk die Aluminium-Zeile landet und ob DIESER Chunk die Einheit / den Kopf hat
        (lange Tabellen werden in Teile zu je max. 300 Wörtern zerlegt, der Kopf steht nur im ersten Teil),
    (c) ob der Chunk unter den Top 4 des Retrievals ist.
Q5  Falsche Verweigerung ("Föhn ohne Schutzleiter"): Rang der Chunks zur doppelten/verstärkten Isolierung in
    jeder Retrieval-Stufe (dense, BM25, Graph, RRF, Reranker) und ob einer davon unter den Top 4 ist.
    Danach EIN Generierungsaufruf mit der aktuellen Prompt-Version (Status + Lösung).

Ausgabe enthält Buchtext -> nur lokal ansehen bzw. in den Chat kopieren, nicht ins Git.

Start (Umgebung pilot_rag, Ollama läuft):
  python skripte/diagnose/diagnose_fehlerfaelle.py --kb daten/wissensbasen/knowledge_base_fischer_v7b.json \
      | tee protokolle/diagnose_fehlerfaelle.txt
"""
import sys as _sys, pathlib as _pl  # Projektpfade (lernassistent/pfadsetup.py)
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401

import argparse
import json
import re
from pathlib import Path

import numpy as np

import rag_pipeline as rp

FRAGE_T1 = "Wie groß ist der spezifische elektrische Widerstand von Aluminium bei 20 °C?"
FRAGE_Q5 = "Mein Föhn hat keinen Schutzleiter. Wieso ist das trotzdem sicher?"
EINHEIT = re.compile(r"mm\s*(?:²|2|\^\s*2|\^\s*\{\s*2\s*\})\s*/\s*m|mm²|Ω\s*·?\s*m\b|Ω\s*·?\s*mm|\\Omega[^$]{0,60}|Ohm")


def flach(x):
    """content_list kann verschachtelte Listen enthalten (je Seite); liefert nur die Einträge (dicts)."""
    if isinstance(x, dict):
        yield x
    elif isinstance(x, list):
        for y in x:
            yield from flach(y)
GOLD_Q5 = re.compile(r"doppelt\w*\s+oder\s+verstärkt\w*|verstärkt\w*\s+oder\s+doppelt\w*|schutzisolier\w*|"
                     r"schutzklasse\s*(?:ii|2)\b", re.I)


def kurz(t, n=700):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t if len(t) <= n else t[:n] + " …"


def um(text, muster, breite=350):
    m = re.search(muster, text or "", re.I)
    if not m:
        return kurz(text, 2 * breite)
    a, b = max(0, m.start() - breite), min(len(text), m.end() + breite)
    return ("… " if a else "") + re.sub(r"\s+", " ", text[a:b]) + (" …" if b < len(text) else "")


def raenge(werte):
    """Rang 1 = bester Wert."""
    ordnung = np.argsort(-np.asarray(werte, dtype=float), kind="stable")
    r = np.empty(len(werte), dtype=int)
    r[ordnung] = np.arange(1, len(werte) + 1)
    return r


def stufenraenge(frage, chunks, methode):
    """Ränge je Stufe für alle Chunks (gleiche Funktionen wie rp.retrieval)."""
    modell = rp._lade_embedding_modell()
    emb = rp._embeddings_fuer_chunks(chunks)
    q = modell.encode([frage], convert_to_numpy=True, normalize_embeddings=True)
    dense = np.asarray(rp.cosine_similarity(q, emb)[0], dtype=float)
    bm25 = np.asarray(rp._bm25_index(chunks).get_scores(rp.tokenisiere(frage)), dtype=float)
    try:
        import wissensgraph
        graph = np.asarray(wissensgraph.graph_scores(frage, chunks, frage_embedding=q[0]), dtype=float)
    except Exception as e:  # Graph fehlt -> nur Hinweis
        print(f"(Graph nicht verfügbar: {e})")
        graph = np.zeros(len(chunks))
    top, alle = rp.retrieval(frage, chunks, top_k=4, methode=methode)
    final = {c["id"]: i + 1 for i, c in enumerate(alle)}
    return {"dense": raenge(dense), "bm25": raenge(bm25),
            "graph": np.where(graph > 0, raenge(graph), 0)}, final, alle, top


def zeige_raenge(ids, chunks, stufen, final, alle):
    pos = {c["id"]: i for i, c in enumerate(chunks)}
    vorstufe = {c["id"]: c.get("rang_vorstufe") for c in alle}
    print(f"  {'Chunk':<10} {'dense':>6} {'bm25':>6} {'graph':>6} {'RRF':>6} {'final':>6}   (Top 4 = final ≤ 4; RRF-Rang > 50 = nicht beim Reranker)")
    for cid in ids:
        i = pos[cid]
        g = stufen["graph"][i]
        print(f"  {cid:<10} {stufen['dense'][i]:>6} {stufen['bm25'][i]:>6} {(g if g else '-'):>6} "
              f"{(vorstufe.get(cid) or '>50'):>6} {final[cid]:>6}")


def t1(chunks, methode):
    print("=" * 100 + "\nT1  Einheit Aluminium\n" + "=" * 100)
    print("\n(a) MinerU-Extraktion (content_list), Tabellen mit '2857':")
    gefunden = False
    for pfad in sorted(Path("daten/extraktion").rglob("*content_list*.json")):
        try:
            eintraege = json.loads(pfad.read_text(encoding="utf-8"))
        except Exception:
            continue
        for e in flach(eintraege):
            roh = json.dumps(e, ensure_ascii=False)
            if "2857" not in roh or e.get("type") != "table":
                continue
            gefunden = True
            body = e.get("table_body", "") or e.get("text", "")
            zeilen = re.split(r"(?i)</tr\s*>", body)
            print(f"  Datei {pfad}  Seite {e.get('page_idx')}  Typ {e.get('type')}  Caption {e.get('table_caption')}")
            print(f"  Tabellenkopf (erste 2 Zeilen, roh): {kurz(' || '.join(zeilen[:2]), 900)}")
            alu = [z for z in zeilen if "2857" in z or "lumin" in z]
            print(f"  Zeile(n) mit Aluminium/2857: {kurz(' || '.join(alu), 600)}")
            print(f"  Einheit im ganzen Eintrag: {sorted(set(m.group(0) for m in EINHEIT.finditer(body)))}")
            try:  # so wird der Kopf beim Chunking umgewandelt
                import pdf_struktur
                kopf = pdf_struktur.tabelle_als_text(zeilen[0] + "</tr>")
                print(f"  Kopf nach Umwandlung (pdf_struktur.tabelle_als_text): {kopf!r}\n")
            except Exception as ex:
                print(f"  (Umwandlung nicht prüfbar: {ex})\n")
    if not gefunden:
        print("  keine content_list mit '2857' unter daten/extraktion gefunden")

    print("(b) Chunks in der Wissensbasis mit '2857' oder 'Aluminium' + Zahl:")
    treffer = [c for c in chunks if "2857" in c["text"] or (re.search(r"alumin", c["text"], re.I)
                                                             and c.get("typ") == "tabelle")]
    for c in treffer:
        tabellenkopf = c["text"].splitlines()[:2]
        print(f"\n  {c['id']}  Typ {c.get('typ')}  Seite {c.get('seite')}  {len(c['text'].split())} Wörter")
        print(f"  erste Zeilen: {kurz(' / '.join(tabellenkopf), 400)}")
        print(f"  Einheiten im Chunk: {sorted(set(m.group(0) for m in EINHEIT.finditer(c['text'])))}")
        print(f"  um Aluminium: {um(c['text'], r'alumin|2857')}")
    if not treffer:
        print("  keine")

    print("\n(c) Retrieval-Ränge für die T1-Frage:")
    stufen, final, alle, top = stufenraenge(FRAGE_T1, chunks, methode)
    zeige_raenge([c["id"] for c in treffer], chunks, stufen, final, alle)
    print(f"  Top 4: {[c['id'] for c in top]}")


def q5(chunks, methode):
    print("\n" + "=" * 100 + "\nQ5  Falsche Verweigerung (Föhn ohne Schutzleiter)\n" + "=" * 100)
    gold = [c for c in chunks if GOLD_Q5.search(c["text"])]
    print(f"\nChunks mit doppelter/verstärkter Isolierung bzw. Schutzisolierung: {len(gold)}")
    for c in gold:
        print(f"\n  {c['id']}  Typ {c.get('typ')}  Seite {c.get('seite')}  Thema {kurz(c.get('thema'), 80)}")
        print(f"  {um(c['text'], GOLD_Q5.pattern, 250)}")
    stufen, final, alle, top = stufenraenge(FRAGE_Q5, chunks, methode)
    print("\nRänge je Stufe:")
    zeige_raenge([c["id"] for c in gold], chunks, stufen, final, alle)
    print("\nTop 4 (das sieht das Modell):")
    for c in top:
        print(f"  {c['id']}  Seite {c.get('seite')}  Reranker {c.get('rerank_score', float('nan')):.3f}  "
              f"{'GOLD ' if GOLD_Q5.search(c['text']) else ''}{kurz(c['text'], 200)}")
    roh = rp.frage_llm(rp.baue_scaffolding_prompt(FRAGE_Q5, top), options=rp.GENERIERUNGS_OPTIONEN)
    st = rp.parse_g_v1(roh) if rp.ist_g_version() else rp.parse_scaffolding_antwort(roh)
    print(f"\nGenerierung ({rp.SCAFFOLDING_VERSION}): STATUS {st.get('status')}\nLÖSUNG: {kurz(st.get('loesung'), 600)}")
    gold_top = any(GOLD_Q5.search(c["text"]) for c in top)
    print("\nBEFUND Q5: " + ("Gold-Chunk unter den Top 4 -> Modellfehler (Verweigerung trotz Beleg)" if gold_top
                            else "kein Gold-Chunk unter den Top 4 -> Retrievalfehler"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_v7c.json")
    ap.add_argument("--retrieval", default="hybrid_kg_rr")
    ap.add_argument("--nur", choices=["t1", "q5"], default=None)
    args = ap.parse_args()
    chunks = rp.lade_wissensbasis(args.kb)
    print(f"KB {args.kb} ({rp.berechne_kb_hash(args.kb)}), {len(chunks)} Chunks, Retrieval {args.retrieval}\n")
    if args.nur in (None, "t1"):
        t1(chunks, args.retrieval)
    if args.nur in (None, "q5"):
        q5(chunks, args.retrieval)


if __name__ == "__main__":
    main()
