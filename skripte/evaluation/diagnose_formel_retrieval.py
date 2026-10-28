"""V18-C: Wird die Formel, die eine Rechenfrage braucht, gefunden – und wenn nicht, in welcher Stufe geht sie verloren?
Für jede Frage: (1) Chunks der Wissensbasis suchen, die die Formel enthalten (Zielmuster, siehe ZIELE oder --ziel);
(2) Rang dieser Chunks in jeder Stufe: dense, bm25, hybrid, hybrid_kg (vor Reranker), hybrid_kg_rr (final, wie die App);
(3) optional (--fs) die Formelsuche FS-v3: welche Suchbegriffe, welche Zusatz-Chunks, ob das Ziel dabei ist (braucht Ollama).
Urteil je Frage:
  gefunden        Ziel im Top-4 der Hauptsuche -> das Problem liegt NICHT im Retrieval (Prompt/Nutzung prüfen)
  reranker        Ziel unter den Kandidaten vor dem Reranker (Rang <= 50), aber nicht im Top-4 -> Reranker verdrängt es
  fenster         Ziel in Stufe hybrid_kg auf Rang 51-200 -> Kandidatenfenster zu klein
  verfehlt        Ziel weiter hinten -> Anfrage trifft die Formel nicht (Suchbegriffe / Umformulierung nötig)
  kein_ziel       kein Chunk passt auf das Zielmuster -> Muster prüfen (--zeige zeigt Treffer) oder Formel steht nicht im Buch
Ohne Ollama (ohne --fs) ca. 1-2 Minuten. Start (aus ~/RAG):
  python skripte/evaluation/diagnose_formel_retrieval.py [--fragen csv] [--nur R05,R07,R12] [--fs] [--zeige]
Ergebnis: Konsole + evaluationsdaten/diagnose_formel_retrieval.csv"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse, csv, re

KB = "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json"
FRAGEN = "daten/testfragen/rechen_varianten*.csv"
AUS = "evaluationsdaten/diagnose_formel_retrieval.csv"
RERANK_N = 50
FENSTER = 200
# Zielmuster je Frage: mindestens eines muss im Chunk stehen UND der Chunk muss eine Formel enthalten (formelsuche.hat_formel).
# Bewusst locker; mit --zeige prüfen, ob die gefundenen Chunks wirklich die gesuchte Formel enthalten.
ZIELE = {
    "R05": [r"Wirkungsgrad[^.]{0,80}=", r"η\s*=\s*P", r"P_?v\s*=", r"Verlustleistung[^.]{0,60}="],
    "R07": [r"τ\s*=\s*R\s*[·*⋅]?\s*C", r"Zeitkonstante[^.]{0,80}=", r"e\s*[-−–]\s*t\s*/\s*τ", r"e\s*[-−–]\s*t\s*/\s*\(?R\s*[·*⋅]?\s*C"],
    "R12": [r"Z\s*=\s*√", r"Scheinwiderstand[^.]{0,80}=", r"Z\s*=\s*sqrt", r"√\s*\(?R\s*2?\s*²?\s*\+\s*\(?ω\s*L"],
}


def finde_ziele(chunks, muster, hat_formel):
    reg = [re.compile(m, re.I) for m in muster]
    return [c for c in chunks if any(r.search(c.get("text", "")) for r in reg) and hat_formel(c.get("text", ""))]


def raenge(liste, ids):
    """Rang (1-basiert) jeder Ziel-ID in der Ergebnisliste; None, wenn nicht enthalten."""
    pos = {c["id"]: i + 1 for i, c in enumerate(liste)}
    return {i: pos.get(i) for i in ids}


def vorstufen_rang(liste, ids):
    """Rang vor dem Reranker: Kandidaten tragen rang_vorstufe, der Rest steht danach in Vorstufen-Reihenfolge."""
    out = {}
    for i, c in enumerate(liste):
        if c["id"] in ids:
            out[c["id"]] = c.get("rang_vorstufe", i + 1)
    return {i: out.get(i) for i in ids}


def bester(r):
    werte = [v for v in r.values() if v]
    return min(werte) if werte else None


def urteil(ids, final, vor, hkg):
    if not ids:
        return "kein_ziel"
    f, v, h = bester(final), bester(vor), bester(hkg)
    if f and f <= 4:
        return "gefunden"
    if v and v <= RERANK_N:
        return "reranker"
    if h and h <= FENSTER:
        return "fenster"
    return "verfehlt"


def analysiere(frage, chunks, ziel_chunks, retrieval_fn, top_k=4):
    ids = [c["id"] for c in ziel_chunks]
    stufen = {}
    for name in ("dense", "bm25", "hybrid", "hybrid_kg"):
        stufen[name] = raenge(retrieval_fn(frage, chunks, top_k=top_k, methode=name)[1], ids)
    top, voll = retrieval_fn(frage, chunks, top_k=top_k, methode="hybrid_kg_rr")
    final = raenge(voll, ids)
    vor = vorstufen_rang(voll, ids)
    return {"ids": ids, "stufen": stufen, "final": final, "vor": vor, "top_ids": [c["id"] for c in top],
            "urteil": urteil(ids, final, vor, stufen["hybrid_kg"])}


def main():
    import rag_pipeline as rp
    import formelsuche
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragen", default=FRAGEN)
    ap.add_argument("--nur", default="R05,R07,R12")
    ap.add_argument("--ziel", default="", help="eigenes Zielmuster (Regex) für alle gewählten Fragen")
    ap.add_argument("--fs", action="store_true", help="Formelsuche FS-v3 zusätzlich ausführen (Ollama nötig)")
    ap.add_argument("--zeige", action="store_true", help="Anfang der gefundenen Ziel-Chunks ausgeben")
    ap.add_argument("--kb", default=KB)
    a = ap.parse_args()
    chunks = rp.lade_wissensbasis(a.kb)
    import glob
    fragen = []
    for datei in sorted(glob.glob(a.fragen)):
        for f in csv.DictReader(open(datei, encoding="utf-8")):
            if f["nr"] in a.nur.split(","):
                fragen.append({**f, "datei": _pl.Path(datei).name})
    if not fragen:
        raise SystemExit(f"Keine Fragen gefunden in {a.fragen} (Pfad/Glob mit --fragen angeben)")
    print(f"{len(chunks)} Chunks, {len(fragen)} Fragen")
    zeilen = []
    for f in fragen:
        muster = [a.ziel] if a.ziel else ZIELE.get(f["nr"], [])
        ziele = finde_ziele(chunks, muster, formelsuche.hat_formel) if muster else []
        r = analysiere(f["frage"], chunks, ziele, rp.retrieval)
        print(f"\n=== {f['nr']} [{f['datei']}] ({f['vorlage']}) {f['frage'][:90]}…")
        print(f"Ziel-Chunks (Formel im Text): {len(ziele)} {r['ids'][:8]}")
        if a.zeige:
            for c in ziele[:4]:
                t = c["text"]
                m = next((re.search(x, t, re.I) for x in muster if re.search(x, t, re.I)), None)
                p = m.start() if m else 0
                print(f"   {c['id']} (S. {c.get('seite', '?')}): …{t[max(0, p - 60):p + 200]!r}")
        if r["ids"]:
            print("Bester Rang je Stufe (1 = oben; - = nicht in der Liste):")
            for name in ("dense", "bm25", "hybrid", "hybrid_kg"):
                print(f"   {name:10s} {bester(r['stufen'][name]) or '-'}")
            print(f"   vor Reranker (Platz in hybrid_kg, Kandidaten 1-{RERANK_N}): {bester(r['vor']) or '-'}")
            print(f"   final (hybrid_kg_rr): {bester(r['final']) or '-'}   Top-4: {r['top_ids']}")
            einzeln = sorted(r["ids"], key=lambda i: r["final"].get(i) or 10**9)[:6]
            print("   Einzelrang (final / vor Reranker / hybrid_kg) der besten Ziel-Chunks:")
            for i in einzeln:
                print(f"      {i}: {r['final'].get(i) or '-'} / {r['vor'].get(i) or '-'} / {r['stufen']['hybrid_kg'].get(i) or '-'}")
        info = {}
        if a.fs:
            zusatz, info = formelsuche.suche(f["frage"], chunks, [c for c in rp.retrieval(f["frage"], chunks, top_k=4, methode="hybrid_kg_rr")[0]],
                                             rp.retrieval, rp.frage_llm, "hybrid_kg_rr")
            ziel_ids = set(r["ids"])
            print(f"FS-v3 Suchbegriffe: {info.get('phrasen')} -> ergänzt {info.get('ids')} "
                  f"{'(Ziel dabei)' if ziel_ids & set(info.get('ids', [])) else '(Ziel NICHT dabei)'}")
        print(f"URTEIL: {r['urteil']}")
        zeilen.append({"nr": f["nr"], "datei": f["datei"], "ziele": len(r["ids"]), "dense": bester(r["stufen"]["dense"]) or "", "bm25": bester(r["stufen"]["bm25"]) or "",
                       "hybrid": bester(r["stufen"]["hybrid"]) or "", "hybrid_kg": bester(r["stufen"]["hybrid_kg"]) or "",
                       "final": bester(r["final"]) or "", "top4": " ".join(r["top_ids"]), "fs_phrasen": "; ".join(info.get("phrasen", [])),
                       "fs_ergaenzt": " ".join(info.get("ids", [])), "fs_ziel": ("ja" if set(r["ids"]) & set(info.get("ids", [])) else "nein") if a.fs else "",
                       "urteil": r["urteil"]})
    _pl.Path(AUS).parent.mkdir(parents=True, exist_ok=True)
    with open(AUS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0])) if zeilen else None
        if w:
            w.writeheader(); w.writerows(zeilen)
    print(f"\nDatei: {AUS}")


if __name__ == "__main__":
    main()
