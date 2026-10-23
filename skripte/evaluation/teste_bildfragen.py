"""Bildfragen-Testlauf BF-v1 (24 Oct 2026): Aufgaben-Screenshots und reine Abbildungen durch die echte Pipeline (RAG, hybrid_kg_rr, RP-v5),
in getrennten Durchgängen je Variante (nicht abwechselnd: Ollama antwortet beim ersten Mal anders als bei Wiederholung).
Fragt: Hilft die Abbildungsbeschreibung? Hilft das Bild selbst im Antwortaufruf? Wie viel bringt eine Themenangabe?

Ordner (aus ~/RAG):
  testbilder/                 Aufgaben-Screenshots (Text + evtl. Abbildung), wie beim Bildtest T-v1
  testbilder/abbildungen/     reine Abbildungen ohne Aufgabentext (z. B. die vierpolige Gleichstrommaschine)
  testbilder/themen.csv       Spalten datei;thema;erwartet   (nur für Abbildungen: Thema in Stichwörtern; erwartet = Stichwörter, die eine
                              richtige Erklärung enthalten muss, mit | getrennt, z. B. Joch|Polschuh|Erregerwicklung|Anker)
                              Fehlt die Datei, wird eine Vorlage angelegt (danach ausfüllen und neu starten).
Start:
  python skripte/evaluation/teste_bildfragen.py BF-01 | tee evaluationsdaten/BF-01.log
  (--schnell: nur 3 Aufgaben-Bilder und alle Abbildungen; --nur-abb: nur Abbildungen)
Ausgabe: evaluationsdaten/bildfragen_<SITZUNG>.csv (+ .md zum Lesen); abgebrochene Läufe werden fortgesetzt.
Automatische Prüfung (nur Abbildungen mit 'erwartet'): Anteil der erwarteten Stichwörter in der Antwort. Der Rest wird von Hand/Vorbewertung beurteilt."""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
import argparse, base64, csv, re, time
from pathlib import Path
import rag_pipeline as rp
import bildeingabe as be

ENDUNGEN = (".png", ".jpg", ".jpeg", ".webp")
FELDER = ["variante", "art", "datei", "frage", "suchanfrage", "bild_an_antwort", "quellen", "status", "hinweis", "loesung", "sekunden",
          "stichwoerter_gefunden", "stichwoerter_erwartet", "bewertung", "bemerkung"]

# (Name, Art, Beschreibung)
VARIANTEN = [
    ("A0_nur_text", "aufgabe", "Aufgabentext allein (Grundlinie, wie V12.4 ohne Abbildung)"),
    ("A1_text_beschr", "aufgabe", "Text + Abbildungsbeschreibung (V12.5/12.7)"),
    ("A2_text_beschr_bild", "aufgabe", "Text + Beschreibung + Bild im Antwortaufruf (V12.6)"),
    ("A3_text_bild", "aufgabe", "Text + Bild im Antwortaufruf, ohne Beschreibung"),
    ("F0_ohne_thema_beschr", "abb", "Nur Bild, ohne Themenangabe, Standardfrage + Beschreibung"),
    ("F1_ohne_thema_beschr_bild", "abb", "wie F0, zusätzlich Bild im Antwortaufruf"),
    ("F2_thema_beschr_bild", "abb", "Themenangabe + Beschreibung + Bild (V12.7 mit Thema)"),
    ("F3_thema_nur_text", "abb", "Nur Themenangabe als Text (Grundlinie: Suche + Antwort ohne Bild und Beschreibung)"),
    ("F4_thema_bild", "abb", "Themenangabe + Bild, ohne Beschreibung"),
]


def lade_themen(pfad, abbildungen):
    if not pfad.exists():
        with open(pfad, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter=";"); w.writerow(["datei", "thema", "erwartet"])
            for p in abbildungen:
                w.writerow([p.name, "", ""])
        print(f"Vorlage angelegt: {pfad} – Spalte 'thema' (und 'erwartet') ausfüllen, dann neu starten.")
        return {}
    with open(pfad, encoding="utf-8", newline="") as f:
        return {r["datei"]: r for r in csv.DictReader(f, delimiter=";")}


def baue(variante, vis, thema):
    """-> (frage, suchanfrage oder None, Bild verwenden)"""
    text, abb, vthema = vis["text"], vis["abbildung"], vis.get("thema", "")
    if variante == "A0_nur_text":
        return text, None, False
    if variante in ("A1_text_beschr", "A2_text_beschr_bild"):
        return be.kombiniere(text, abb), " ".join(x for x in (text, vthema) if x), variante.endswith("bild")
    if variante == "A3_text_bild":
        return text, None, True
    standard = be.STANDARD_FRAGE
    if variante in ("F0_ohne_thema_beschr", "F1_ohne_thema_beschr_bild"):
        suche = " ".join(x for x in (text, vthema) if x) or None
        return be.kombiniere((text + "\n" + standard).strip(), abb), suche, variante.endswith("bild")
    frage_thema = f"Erkläre diese Abbildung der {thema}: Aufbau, Bauteile und Funktionsweise."
    if variante == "F2_thema_beschr_bild":
        return be.kombiniere(frage_thema, abb), " ".join(x for x in (frage_thema, vthema) if x), True
    if variante == "F3_thema_nur_text":
        return frage_thema, None, False
    if variante == "F4_thema_bild":
        return frage_thema, None, True
    raise ValueError(variante)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sitzung")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--ordner", default="testbilder")
    ap.add_argument("--schnell", action="store_true")
    ap.add_argument("--nur-abb", action="store_true")
    a = ap.parse_args()
    ordner = Path(a.ordner)
    aufgaben = sorted(p for p in ordner.iterdir() if p.suffix.lower() in ENDUNGEN) if ordner.exists() else []
    abb_ordner = ordner / "abbildungen"
    abbildungen = sorted(p for p in abb_ordner.iterdir() if p.suffix.lower() in ENDUNGEN) if abb_ordner.exists() else []
    if a.schnell:
        aufgaben = aufgaben[:3]
    if a.nur_abb:
        aufgaben = []
    themen = lade_themen(ordner / "themen.csv", abbildungen) if abbildungen else {}
    if not aufgaben and not abbildungen:
        raise SystemExit(f"Keine Bilder in {ordner} bzw. {abb_ordner}")
    chunks = rp.lade_wissensbasis(a.kb)
    kb_hash = rp.berechne_kb_hash(a.kb)
    rp.RETRIEVAL_METHODE = "hybrid_kg_rr"
    out = Path("evaluationsdaten") / f"bildfragen_{a.sitzung}.csv"
    out.parent.mkdir(exist_ok=True)
    zeilen = []
    if out.exists():
        with open(out, encoding="utf-8", newline="") as f:
            zeilen = list(csv.DictReader(f))
    fertig = {(z["variante"], z["datei"]) for z in zeilen}
    print(f"{len(aufgaben)} Aufgaben-Bilder, {len(abbildungen)} Abbildungen | KB {kb_hash} | {rp.SCAFFOLDING_VERSION} | {len(fertig)} Läufe schon vorhanden\n", flush=True)

    # 1) Bild lesen (einmal je Bild, qwen3.5:9b, gleiche Funktion wie die App)
    vision, vlog = {}, Path("evaluationsdaten") / f"bildfragen_{a.sitzung}_vision.csv"
    with open(vlog, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["datei", "sekunden", "fehler", "text", "thema", "abbildung", "roh"])
        for p in aufgaben + abbildungen:
            v = be.lies_aufgabe(p.read_bytes())
            vision[p] = v
            w.writerow([p.name, v["sekunden"], v["fehler"], v["text"], v.get("thema", ""), v["abbildung"], v["roh"]]); f.flush()
            print(f"gelesen {p.name}: {v['sekunden']} s, Text {len(v['text'])} Z., Thema '{v.get('thema','')[:50]}', Abbildung {'ja' if v['abbildung'] else 'nein'} {v['fehler']}", flush=True)

    def speichere():
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FELDER); w.writeheader()
            for z in zeilen: w.writerow({k: z.get(k, "") for k in FELDER})
        md = out.with_suffix(".md")
        with open(md, "w", encoding="utf-8") as f:
            for z in zeilen:
                f.write(f"## {z['datei']} · {z['variante']}\n\n**Frage:** {z['frage']}\n\n**Suche:** {z['suchanfrage'] or '(= Frage)'} · Bild an Antwort: {z['bild_an_antwort']} · {z['sekunden']} s · {z['status']}\n\n"
                        f"**Quellen:** {z['quellen']}\n\n**Hinweis:** {z['hinweis']}\n\n**Lösung:** {z['loesung']}\n\n"
                        f"Stichwörter: {z['stichwoerter_gefunden'] or '-'} / {z['stichwoerter_erwartet'] or '-'}\n\n---\n\n")

    # 2) Varianten als getrennte Durchgänge
    for variante, art, beschr in VARIANTEN:
        bilder = aufgaben if art == "aufgabe" else abbildungen
        if not bilder:
            continue
        print(f"\n--- {variante}: {beschr} ---", flush=True)
        for p in bilder:
            if (variante, p.name) in fertig:
                continue
            v = vision[p]
            thema = (themen.get(p.name) or {}).get("thema", "")
            erwartet = [x for x in ((themen.get(p.name) or {}).get("erwartet", "")).split("|") if x]
            if art == "abb" and variante.startswith(("F2", "F3", "F4")) and not thema:
                print(f"[{p.name}] übersprungen (kein Thema in themen.csv)", flush=True); continue
            if v["fehler"] or (art == "aufgabe" and not v["text"]):
                print(f"[{p.name}] übersprungen (Bild nicht lesbar: {v['fehler']})", flush=True); continue
            frage, suche, mit_bild = baue(variante, v, thema)
            rp.RETRIEVAL_FRAGE = suche
            rp.BILD_ANHANG = base64.b64encode(be.verkleinere(p.read_bytes())).decode() if mit_bild else None
            t0 = time.time()
            try:
                erg = rp.beantworte_frage(frage, chunks, methode="hybrid_kg_rr")
            except Exception as e:
                erg = {"status": "FEHLER", "loesung": str(e)[:300]}
            finally:
                rp.RETRIEVAL_FRAGE = None; rp.BILD_ANHANG = None
            sek = round(time.time() - t0, 1)
            antwort = f"{erg.get('hinweis','')} {erg.get('loesung','')}".lower()
            gef = [k for k in erwartet if k.lower() in antwort]
            zeilen.append({"variante": variante, "art": art, "datei": p.name, "frage": frage, "suchanfrage": suche or "", "bild_an_antwort": mit_bild,
                           "quellen": "; ".join(str(q) for q in (erg.get("quellen") or []))[:400], "status": erg.get("status", ""),
                           "hinweis": erg.get("hinweis", ""), "loesung": erg.get("loesung", ""), "sekunden": sek,
                           "stichwoerter_gefunden": "|".join(gef), "stichwoerter_erwartet": "|".join(erwartet)})
            print(f"[{p.name[:30]:<30}] {erg.get('status','')} {sek} s" + (f" Stichwörter {len(gef)}/{len(erwartet)}" if erwartet else ""), flush=True)
            speichere()
    print("\nFertig:", out)
    # Kurzübersicht Stichwörter je Variante
    for variante, art, _ in VARIANTEN:
        zs = [z for z in zeilen if z["variante"] == variante and z.get("stichwoerter_erwartet")]
        if zs:
            n = sum(len(z["stichwoerter_gefunden"].split("|")) if z["stichwoerter_gefunden"] else 0 for z in zs)
            m = sum(len(z["stichwoerter_erwartet"].split("|")) for z in zs)
            print(f"{variante:<28} Stichwörter {n}/{m}")


if __name__ == "__main__":
    main()
