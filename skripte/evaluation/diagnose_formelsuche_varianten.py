"""V19a-Vorversuch: Welche Art von Suchanfrage findet die Formel, die eine Rechenfrage braucht?
Vergleicht vier Wege, aus der Frage Suchanfragen zu bilden (alle vorher festgelegt, NICHT an den Testfragen abgestimmt):
  V0 aktuell   FS-v3-Prompt: Fachbegriffe der nötigen Beziehungen (formelsuche.baue_prompt)
  V1 weg       Lösungsweg in Worten (welche Größe zuerst, welche danach), dann je Schritt ein Fachbegriff
  V2 gleichung nötige Gleichungen mit Formelzeichen, ohne Zahlen, eine je Zeile; die Gleichung selbst ist die Suchanfrage
  V3 beides    Fachbegriffe aus V1 und Gleichungen aus V2 zusammen (höchstens 6 Anfragen)
  F  frage     Hauptsuche mit der ganzen Frage (Bezug)
Gemessen wird, ob ein Chunk mit der gesuchten Formel (Zielmuster je Aufgabe, ZIELE) unter den obersten Treffern einer Anfrage steht
(hybrid_kg_rr wie in der App). Fragen, bei denen das Muster keinen oder zu viele Chunks (> 30) findet, zählen nicht
(Muster dort nicht verlässlich); die Anzahl wird ausgegeben. R07 und R12 sind die Anlassfälle, alle anderen sind Prüffälle.
Ollama nötig, ca. 10-15 Minuten. Antworten des Modells werden in evaluationsdaten/fs_varianten_roh.json zwischengespeichert
(zweiter Lauf: Modell wird nicht erneut gefragt, außer mit --neu).
Start (aus ~/RAG): python skripte/evaluation/diagnose_formelsuche_varianten.py [--nur R07,R12] [--neu] [--zeige]
Ergebnis: Konsole + evaluationsdaten/fs_varianten.csv"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import argparse, csv, glob, json, os, re, time
import diagnose_formel_retrieval as dfr

ROH = "evaluationsdaten/fs_varianten_roh.json"
AUS = "evaluationsdaten/fs_varianten.csv"
MAX_ZIELE = 30
LLM_OPTIONEN = {"temperature": 0, "seed": 42, "num_predict": 260}
ZIELE = {**dfr.ZIELE,
         "R04": [r"P\s*=\s*2\s*π\s*n\s*M", r"M\s*=\s*P\s*/\s*\(?2\s*π"],
         "R08": [r"μ_?0\s*I\s*/?\s*\(?2\s*π\s*r", r"H\s*=\s*I\s*/\s*\(?2\s*π\s*r"],
         "R09": [r"F\s*=\s*\(?B\s*²?\s*A", r"B²\s*A\s*/\s*\(?2\s*μ"],
         "R10": [r"W_?m?\s*=\s*\(?1\s*/\s*2\)?\s*L\s*I", r"½\s*L\s*I", r"u\s*=\s*L\s*d?i\s*/\s*d?t"],
         "R11": [r"X_?L\s*=\s*ω\s*L"],
         "R13": [r"I_?w\s*=\s*I\s*cos", r"I_?b\s*=\s*I\s*sin"],
         "R14": [r"P_?Fe\s*=", r"P_?Fe\s*~"],
         "R15": [r"R_?th\s*=\s*\(?Δ?ϑ", r"Δϑ\s*=\s*P_?v?\s*R_?th", r"P_?v\s*=\s*\(?ϑ"],
         "R17": [r"s\s*=\s*\(?v_?s\s*[-−]\s*v", r"v_?s\s*=\s*2\s*τ"],
         "R18": [r"Anpassung", r"R_?V\s*=\s*R_?i"],
         "R20": [r"s_?K\s*=\s*R_?r", r"M\s*/\s*M_?K\s*=\s*2"],
         "R21": [r"n_?0\s*=", r"n\s*=\s*n_?0\s*[-−]"],
         "R22": [r"η_?max", r"P_?Cu\s*=\s*P_?Fe"]}

P_WEG = """Eine Rechenaufgabe aus der Technik soll gelöst werden. Beschreibe zuerst in 2 bis 4 kurzen Zeilen den Lösungsweg in Worten: welche Größe berechnet man nacheinander (z. B. "Strom aus Leistung und Spannung"). Keine Zahlen.
Schreibe danach eine Zeile "### Suchbegriffe" und darunter je Schritt einen Fachbegriff (2 bis 6 Wörter), unter dem die dafür nötige Beziehung in einem Lehrbuch steht (Gesetz, Größe, Bauteil, Schaltung). Keine Zahlen, keine Formeln.

### Aufgabe
{frage}

### Lösungsweg"""

P_GLEICHUNG = """Eine Rechenaufgabe aus der Technik soll gelöst werden. Schreibe die Gleichungen auf, die man dafür braucht, mit Formelzeichen und ohne Zahlen, eine Gleichung pro Zeile, höchstens 4 Zeilen (z. B. "P = U · I"). Auch Hilfsgleichungen nennen. Keine Erklärung, keine Nummerierung.

### Aufgabe
{frage}

### Gleichungen"""


def parse_begriffe(roh):
    import formelsuche
    teil = roh.split("### Suchbegriffe", 1)[1] if "### Suchbegriffe" in roh else ""
    return formelsuche.parse(teil)


def parse_gleichungen(roh):
    out = []
    for z in (roh or "").splitlines():
        z = re.sub(r"^[\s\-–—*•\d.)(:]+", "", z).strip().strip("`$ ")
        if "=" in z and 5 <= len(z) <= 80 and not re.search(r"\d{2,}", z) and z not in out:
            out.append(z)
    return out[:4]


def anfragen(roh_v0, roh_v1, roh_v2, frage):
    import formelsuche
    v0 = formelsuche.parse(roh_v0)
    v1 = parse_begriffe(roh_v1)
    v2 = parse_gleichungen(roh_v2)
    return {"V0 aktuell": v0, "V1 weg": v1, "V2 gleichung": v2, "V3 beides": (v1 + v2)[:6], "F frage": [frage]}


RANG_DATEI = "evaluationsdaten/fs_varianten_ranglisten.json"
_RANG = {}
_RANG_SCHMUTZIG = [False]


ZEIT = {}


def rangliste(phrase, retrieval_fn, methode="hybrid_kg_rr"):
    """IDs der obersten 300 Treffer für eine Anfrage; wird zwischengespeichert (Datei + Speicher). Schlüssel ohne Präfix = mit Reranker."""
    key = phrase if methode == "hybrid_kg_rr" else f"{methode}|{phrase}"
    if key not in _RANG:
        t0 = time.perf_counter()
        _, voll = retrieval_fn(phrase, CHUNKS, top_k=6, methode=methode)
        z = ZEIT.setdefault(methode, [0.0, 0]); z[0] += time.perf_counter() - t0; z[1] += 1
        _RANG[key] = [c["id"] for c in voll[:300]]
        _RANG_SCHMUTZIG[0] = True
    return _RANG[key]


def speichere_raenge():
    if _RANG_SCHMUTZIG[0]:
        json.dump(_RANG, open(RANG_DATEI, "w", encoding="utf-8"), ensure_ascii=False)
        _RANG_SCHMUTZIG[0] = False


def bewerte(phrasen, ids, retrieval_fn):
    """(bester Rang über alle Anfragen oder None, Treffer in den obersten 3 irgendeiner Anfrage)."""
    best, top3 = None, False
    for p in phrasen:
        pos = {i: n + 1 for n, i in enumerate(rangliste(p, retrieval_fn))}
        r = min((pos[i] for i in ids if i in pos), default=None)
        if r:
            best = r if best is None else min(best, r)
            top3 = top3 or r <= 3
    return best, top3


def fuse(listen, k=10):
    """Reciprocal Rank Fusion über mehrere Ranglisten (Cormack et al. 2009)."""
    score = {}
    for liste in listen:
        for n, i in enumerate(liste, 1):
            score[i] = score.get(i, 0.0) + 1.0 / (k + n)
    return [i for i, _ in sorted(score.items(), key=lambda x: -x[1])]


def zusatz(fused, schon, hat_formel, n=2):
    """Wie FS: die ersten n Chunks der fusionierten Liste mit Formel, die noch nicht im Kontext sind."""
    out = []
    for i in fused:
        if i in schon or i in out or not hat_formel(BYID[i].get("text", "")):
            continue
        out.append(i)
        if len(out) >= n:
            break
    return out


BYID = {}

_MINILM = [None]
MINILM = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"


def bewerte_minilm(query, texte):
    import reranker
    if _MINILM[0] is None:
        from sentence_transformers import CrossEncoder
        _MINILM[0] = CrossEncoder(MINILM, max_length=512, device="cpu")
    return [float(w) for w in _MINILM[0].predict([(query, reranker._bereinige(t)) for t in texte], batch_size=16, show_progress_bar=False)]


def rerank_wahl(query, ids, bewerte_fn, tag, n=2):
    """Die n besten IDs nach Cross-Encoder-Wert; Zeit wird unter tag gesammelt."""
    if not ids:
        return []
    t0 = time.perf_counter()
    w = bewerte_fn(query, [BYID[i]["text"] for i in ids])
    z = ZEIT.setdefault(tag, [0.0, 0]); z[0] += time.perf_counter() - t0; z[1] += 1
    return [i for i, _ in sorted(zip(ids, w), key=lambda x: -x[1])][:n]

CHUNKS = None


def main():
    global CHUNKS
    import rag_pipeline as rp
    import formelsuche
    ap = argparse.ArgumentParser()
    ap.add_argument("--fragen", default="daten/testfragen/rechen_varianten*.csv")
    ap.add_argument("--nur", default="")
    ap.add_argument("--neu", action="store_true", help="Modellantworten neu erzeugen statt aus dem Zwischenspeicher")
    ap.add_argument("--zeige", action="store_true", help="Anfragen je Variante ausgeben")
    ap.add_argument("--kb", default=dfr.KB)
    a = ap.parse_args()
    CHUNKS = rp.lade_wissensbasis(a.kb)
    BYID.update({c["id"]: c for c in CHUNKS})
    if os.path.exists(RANG_DATEI) and not a.neu:
        _RANG.update(json.load(open(RANG_DATEI, encoding="utf-8")))
    fragen, gesehen = [], set()
    for datei in sorted(glob.glob(a.fragen)):
        for f in csv.DictReader(open(datei, encoding="utf-8")):
            if f["vorlage"] in gesehen or f["nr"] not in ZIELE or (a.nur and f["nr"] not in a.nur.split(",")):
                continue
            gesehen.add(f["vorlage"]); fragen.append(f)
    roh = {} if (a.neu or not os.path.exists(ROH)) else json.load(open(ROH, encoding="utf-8"))
    print(f"{len(CHUNKS)} Chunks, {len(fragen)} Fragen (je Aufgabe einmal)")
    zeilen, summe, pool_summe = [], {}, {}
    for f in fragen:
        ziele = dfr.finde_ziele(CHUNKS, ZIELE[f["nr"]], formelsuche.hat_formel)
        ids = [c["id"] for c in ziele]
        gueltig = 1 <= len(ids) <= MAX_ZIELE
        key = f["nr"] + "|" + f["frage"]
        if key not in roh:
            roh[key] = {"v0": rp.frage_llm(formelsuche.baue_prompt(f["frage"]), options=formelsuche.FS_OPTIONEN),
                        "v1": rp.frage_llm(P_WEG.format(frage=f["frage"]), options=LLM_OPTIONEN),
                        "v2": rp.frage_llm(P_GLEICHUNG.format(frage=f["frage"]), options=LLM_OPTIONEN)}
            _pl.Path(ROH).parent.mkdir(parents=True, exist_ok=True)
            json.dump(roh, open(ROH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        q = anfragen(roh[key]["v0"], roh[key]["v1"], roh[key]["v2"], f["frage"])
        print(f"\n=== {f['nr']} ({f['vorlage']}) Ziel-Chunks: {len(ids)}{'' if gueltig else '  -> zählt nicht (Muster unzuverlässig)'}")
        for name, phrasen in q.items():
            if a.zeige and name != "F frage":
                print(f"   {name:13s} {phrasen}")
            best, top3 = bewerte(phrasen, ids, rp.retrieval) if ids else (None, False)
            print(f"   {name:13s} bester Rang {best or '-':>4}  Top-3: {'ja' if top3 else 'nein'}")
            zeilen.append({"nr": f["nr"], "vorlage": f["vorlage"], "ziele": len(ids), "gueltig": int(gueltig), "variante": name,
                           "anfragen": " | ".join(phrasen) if name != "F frage" else "", "bester_rang": best or "", "top3": int(top3)})
            if gueltig:
                s = summe.setdefault(name, [0, 0, 0])
                s[0] += 1; s[1] += int(top3); s[2] += int(bool(best and best <= 6))
        # Pipeline-realistisch: Kontext = Hauptsuche (Top-4 / Top-6) + höchstens 2 Zusatz-Chunks aus den fusionierten Anfragen
        F = rangliste(f["frage"], rp.retrieval)
        pools = {"P0 Hauptsuche Top-4 (heute ohne FS)": F[:4], "P1 Hauptsuche Top-6": F[:6]}
        for name in ("V0 aktuell", "V1 weg", "V3 beides"):
            fu = fuse([rangliste(x, rp.retrieval) for x in q[name]])
            pools[f"P2 Top-4 + 2 aus {name}"] = F[:4] + zusatz(fu, set(F[:4]), formelsuche.hat_formel)
            pools[f"P3 Top-6 + 2 aus {name}"] = F[:6] + zusatz(fu, set(F[:6]), formelsuche.hat_formel)
        # Billigere Wege (V1-Begriffe): ohne Reranker, als eine Anfrage, nur die ersten 2 Begriffe
        v1 = q["V1 weg"]
        rr = lambda x, m="hybrid_kg_rr": rangliste(x, rp.retrieval, m)
        F4 = set(F[:4])
        pools["C0 Top-4 + 2 aus V1, ohne Reranker (je Begriff)"] = F[:4] + zusatz(fuse([rr(x, "hybrid_kg") for x in v1]), F4, formelsuche.hat_formel)
        pools["C1 Top-4 + 2 aus V1, alle Begriffe als EINE Anfrage (mit Reranker)"] = F[:4] + zusatz(rr(" ".join(v1)), F4, formelsuche.hat_formel)
        pools["C2 Top-4 + 2 aus V1, alle Begriffe als EINE Anfrage (ohne Reranker)"] = F[:4] + zusatz(rr(" ".join(v1), "hybrid_kg"), F4, formelsuche.hat_formel)
        pools["C3 Top-4 + 2 aus V1, nur die ersten 2 Begriffe (mit Reranker)"] = F[:4] + zusatz(fuse([rr(x) for x in v1[:2]]), F4, formelsuche.hat_formel)
        pools["C4 Top-4 + 2 aus V1, nur die ersten 2 Begriffe (ohne Reranker)"] = F[:4] + zusatz(fuse([rr(x, "hybrid_kg") for x in v1[:2]]), F4, formelsuche.hat_formel)
        # Reranker nur EINMAL: Kandidaten billig (ohne Reranker, je Begriff), Auswahl der 2 besten Formel-Chunks durch den Cross-Encoder
        import reranker
        kand_alle = [i for i in fuse([rr(x, "hybrid_kg") for x in v1]) if i not in F4 and formelsuche.hat_formel(BYID[i].get("text", ""))]
        kand = kand_alle[:20]
        if ids:
            pos = [n + 1 for n, i in enumerate(kand_alle) if i in set(ids)]
            print(f"   Ziel im Kandidatenpool (Formel-Chunks, ohne Reranker, fusioniert): Platz {min(pos) if pos else '-'} von {len(kand_alle)}")
        anfr = " ".join(v1)
        pools["C5 Top-4 + 2: Kandidaten ohne Reranker, Auswahl 1x bge (20 Kand.)"] = F[:4] + rerank_wahl(anfr, kand, reranker.bewerte, "bge 20 Kandidaten")
        try:
            pools["C6 Top-4 + 2: Kandidaten ohne Reranker, Auswahl 1x MiniLM (20 Kand.)"] = F[:4] + rerank_wahl(anfr, kand, bewerte_minilm, "MiniLM 20 Kandidaten")
        except Exception as ex:  # Modell nicht ladbar: Variante überspringen
            print(f"   (C6 übersprungen: {type(ex).__name__}: {str(ex)[:80]})")
        for n_k in (50, 100):
            try:
                pools[f"C{7 if n_k == 50 else 8} Top-4 + 2: Kandidaten ohne Reranker, Auswahl 1x MiniLM ({n_k} Kand.)"] = \
                    F[:4] + rerank_wahl(anfr, kand_alle[:n_k], bewerte_minilm, f"MiniLM {n_k} Kandidaten")
            except Exception as ex:
                print(f"   (C{7 if n_k == 50 else 8} übersprungen: {type(ex).__name__})")
        # Billiger Reranker je BEGRIFF (MiniLM): jeder Begriff ordnet seine eigenen Kandidaten, dann Fusion der neu geordneten Listen
        for n_k, cname in ((20, "C9"), (50, "C10")):
            try:
                listen = []
                for x in v1:
                    cand = [i for i in rr(x, "hybrid_kg") if i not in F4 and formelsuche.hat_formel(BYID[i].get("text", ""))][:n_k]
                    if cand:
                        listen.append(rerank_wahl(x, cand, bewerte_minilm, f"MiniLM {n_k} Kandidaten je Begriff (1 Begriff)", n=len(cand)))
                pools[f"{cname} Top-4 + 2: je Begriff MiniLM-Auswahl ({n_k} Kand. je Begriff), fusioniert"] = \
                    F[:4] + zusatz(fuse(listen), F4, formelsuche.hat_formel)
            except Exception as ex:
                print(f"   ({cname} übersprungen: {type(ex).__name__})")
        for name, pool in pools.items():
            hit = bool(set(ids) & set(pool)) if ids else False
            print(f"   {name:40s} Ziel im Kontext: {'ja' if hit else 'nein'}")
            zeilen.append({"nr": f["nr"], "vorlage": f["vorlage"], "ziele": len(ids), "gueltig": int(gueltig), "variante": name,
                           "anfragen": "", "bester_rang": "", "top3": int(hit)})
            if gueltig:
                sp = pool_summe.setdefault(name, [0, 0]); sp[0] += 1; sp[1] += int(hit)
        speichere_raenge()
    print("\n=== Summe über gültige Fragen (Top-3 / Top-6 irgendeiner Anfrage)")
    for name, (n, t3, t6) in summe.items():
        print(f"   {name:13s} {t3}/{n} in Top-3   {t6}/{n} in Top-6")
    print("\n=== Summe über gültige Fragen: Ziel-Chunk im Kontext (so wie die App ihn bauen würde)")
    for name, (n, t) in pool_summe.items():
        print(f"   {name:40s} {t}/{n}")
    for m, (sek, n) in ZEIT.items():
        print(f"   Zeit je neuer Aufruf ({m}): {sek / max(n, 1):.1f} s (n={n})")
    with open(AUS, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(zeilen[0])); w.writeheader(); w.writerows(zeilen)
    print(f"\nDatei: {AUS}  (Modellantworten: {ROH})")


if __name__ == "__main__":
    main()
