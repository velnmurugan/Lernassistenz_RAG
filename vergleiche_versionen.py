"""
vergleiche_versionen.py
-----------------------
Vergleicht alle archivierten Versionen (evaluationsdaten/archiv/<VERSION>/)
in einer Tabelle und einem Diagramm-Bericht.

Liest pro Version:
  - archiv/<VERSION>/ragas_ergebnisse.csv              (Pflicht)
  - testlauf_retrieval_<SITZUNGS_ID>.csv                (Recall, Antwortzeit; optional)
  - lauf_<SITZUNGS_ID>.json                             (Konfiguration; optional)
  gesucht jeweils in archiv/<VERSION>/, archiv/ und evaluationsdaten/
und ordnet über testfragen_v1.csv jeder Frage ihren Typ zu.

Ausgabe:
  - Tabelle im Terminal
  - evaluationsdaten/versionsvergleich.csv
  - evaluationsdaten/versionsvergleich.html  (Diagramme, im Browser öffnen)

Kennzahlen:
  Recall@4 (+Nachbar)   Quell-Chunk unter den Top-4 (bzw. Nachbar-Chunk), von 25
  Verw. korrekt         verweigert bei 'ausserhalb'/'teilrelevant' (von 8)
  Verw. falsch          verweigert, obwohl die Frage beantwortbar war (von 22)
  Saubere Antworten     beantwortet, Faithfulness >= 0.75, nicht ausweichend
  Kritische Antworten   beantwortet, Faithfulness < 0.5 (Grounding-Fehler)
  Faithfulness / AR / CR  Mittelwerte wie in ragas_auswertung.py
  Antwortzeit           Median in s (ohne erste Frage = Modell-Ladezeit)

Start:
  python vergleiche_versionen.py
  python vergleiche_versionen.py --versionen V0-DENSE-T0,V1-BM25-T0,V1-HYBRID-T0a,V1-HYBRID-T0b
  python vergleiche_versionen.py --richter mistral-nemo   # nur Versionen mit diesem Richter
"""
import argparse
import csv
import html
import json
import statistics
from pathlib import Path

EVAL = Path("evaluationsdaten")
ARCHIV = EVAL / "archiv"
TESTFRAGEN = Path("testfragen_v1.csv")
NICHT_BEANTWORTBAR = {"ausserhalb", "teilrelevant"}


# =============================================================================
# Daten laden
# =============================================================================
def lies_csv(pfad):
    with open(pfad, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def finde(dateiname, ordner):
    for p in (ordner / dateiname, ARCHIV / dateiname, EVAL / dateiname):
        if p.exists():
            return p
    return None


def zahl(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def mittel(werte):
    werte = [w for w in werte if w is not None]
    return statistics.mean(werte) if werte else None


def werte_version(ordner, typ_von_frage):
    ragas = lies_csv(ordner / "ragas_ergebnisse.csv")
    sid = ragas[0].get("sitzungs_id", ordner.name) if ragas else ordner.name
    richter = ragas[0].get("richter", "") if ragas else ""

    bericht_pfad = finde(f"testlauf_retrieval_{sid}.csv", ordner) or finde("testlauf_retrieval.csv", ordner)
    bericht = lies_csv(bericht_pfad) if bericht_pfad else []
    konfig_pfad = finde(f"lauf_{sid}.json", ordner)
    konfig = json.load(open(konfig_pfad, encoding="utf-8")) if konfig_pfad else {}

    verw = [r for r in ragas if r.get("modell_verweigerung") == "True"]
    beantw = [r for r in ragas if r.get("modell_verweigerung") != "True"]
    typ = lambda r: typ_von_frage.get(r["frage"], "?")
    verw_korrekt = sum(typ(r) in NICHT_BEANTWORTBAR for r in verw)
    verw_falsch = sum(typ(r) not in NICHT_BEANTWORTBAR and typ(r) != "?" for r in verw)

    def ist_sauber(r):
        f = zahl(r.get("faithfulness"))
        return f is not None and f >= 0.75 and r.get("ausweichend") != "True" and r.get("answer_relevance", "") != ""

    faith = [zahl(r.get("faithfulness")) for r in beantw]
    ausweichend = sum(r.get("ausweichend") == "True" for r in beantw)
    ar_roh_ok = [zahl(r.get("ar_roh")) for r in beantw if r.get("ausweichend") == "False"]

    mit_chunk = [b for b in bericht if b.get("erwarteter_chunk")]
    sek = [zahl(b.get("sekunden")) for b in sorted(bericht, key=lambda b: int(b["nr"]))[1:]]

    return {
        "version": ordner.name,
        "sitzungs_id": sid,
        "richter": richter,
        "retrieval": konfig.get("retrieval_methode", ""),
        "rrf_k": konfig.get("rrf_k", ""),
        "temperatur": (konfig.get("generierungs_optionen") or {}).get("temperature", ""),
        "kb_hash": konfig.get("kb_hash", ""),
        "faelle": len(ragas),
        "recall4": sum(b.get("treffer_exakt") == "True" for b in mit_chunk) if mit_chunk else None,
        "recall4_nachbar": sum(b.get("treffer_inkl_nachbar") == "True" for b in mit_chunk) if mit_chunk else None,
        "n_mit_chunk": len(mit_chunk) or None,
        "verw_korrekt": verw_korrekt,
        "n_nicht_beantwortbar": sum(t in NICHT_BEANTWORTBAR for t in (typ(r) for r in ragas)),
        "verw_falsch": verw_falsch,
        "n_beantwortbar": sum(t not in NICHT_BEANTWORTBAR and t != "?" for t in (typ(r) for r in ragas)),
        "beantwortet": len(beantw),
        "sauber": sum(ist_sauber(r) for r in beantw),
        "kritisch": sum(f is not None and f < 0.5 for f in faith),
        "faithfulness": mittel(faith),
        "answer_relevance": mittel([zahl(r.get("answer_relevance")) for r in beantw]),
        "ausweichend": ausweichend,
        "ar_roh_nicht_ausweichend": mittel(ar_roh_ok),
        "context_relevance": mittel([zahl(r.get("context_relevance")) for r in ragas]),
        "context_relevance_beantwortet": mittel([zahl(r.get("context_relevance")) for r in beantw]),
        "antwortzeit_median_s": statistics.median([s for s in sek if s is not None]) if any(sek) else None,
    }


# =============================================================================
# HTML-Bericht (inline SVG, ohne externe Bibliotheken)
# =============================================================================
CSS = """
.viz-root{color-scheme:light;--surface-1:#fcfcfb;--surface-2:#f3f2ef;--text-primary:#0b0b0b;
--text-secondary:#52514e;--text-muted:#77766f;--grid:#e4e3df;--series-1:#2a78d6;--series-2:#eb6834}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])) .viz-root{color-scheme:dark;
--surface-1:#1a1a19;--surface-2:#242422;--text-primary:#ffffff;--text-secondary:#c3c2b7;--text-muted:#9a998f;
--grid:#33332f;--series-1:#3987e5;--series-2:#d95926}}
:root[data-theme="dark"] .viz-root{color-scheme:dark;--surface-1:#1a1a19;--surface-2:#242422;
--text-primary:#ffffff;--text-secondary:#c3c2b7;--text-muted:#9a998f;--grid:#33332f;--series-1:#3987e5;--series-2:#d95926}
html,body{margin:0}
body.viz-root{background:var(--surface-1);color:var(--text-primary);
font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;padding:24px 16px}
main{max-width:1100px;margin:0 auto}
h1{font-size:20px;margin:0 0 4px}
p.sub{color:var(--text-secondary);margin:0 0 20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px}
.card{background:var(--surface-2);border-radius:10px;padding:14px 14px 6px}
.card h2{font-size:14px;margin:0}
.card p{font-size:12px;color:var(--text-secondary);margin:2px 0 6px}
.legend{display:flex;gap:14px;font-size:12px;color:var(--text-secondary);margin-bottom:4px}
.legend span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:2px;
margin-right:5px;vertical-align:-1px;background:var(--c)}
svg{width:100%;height:auto;display:block}
svg text{fill:var(--text-secondary);font-size:11px}
svg .val{fill:var(--text-primary);font-size:11px}
svg .grid{stroke:var(--grid);stroke-width:1}
svg rect.bar:hover,svg path.bar:hover{opacity:.8}
.tablewrap{overflow-x:auto;margin-top:24px}
table{border-collapse:collapse;font-size:12.5px;white-space:nowrap}
th,td{padding:6px 10px;border-bottom:1px solid var(--grid);text-align:right}
th:first-child,td:first-child{text-align:left}
th{color:var(--text-secondary);font-weight:600}
.note{font-size:12px;color:var(--text-muted);margin-top:14px}
"""


def balken(x, y, w, h):
    """Balken mit 4px abgerundeter Oberkante, an der Grundlinie eckig."""
    r = min(4, w / 2, h)
    if h <= 0:
        return f"M{x},{y} h{w}"
    return (f"M{x},{y + h} V{y + r} Q{x},{y} {x + r},{y} H{x + w - r} "
            f"Q{x + w},{y} {x + w},{y + r} V{y + h} Z")


def diagramm(titel, untertitel, versionen, reihen, ymax, fmt):
    """reihen: Liste von (name, werte, css_var). Ein Diagramm = eine Achse."""
    # Achse auf "runde" Werte aufrunden: ganzzahlige Schritte bzw. 0.05er-Schritte
    if fmt(1.0) == "1":
        schritt = max(1, -(-int(round(ymax)) // 4))
        ymax = schritt * 4
    else:
        ymax = next(v for v in (0.2, 0.4, 0.6, 0.8, 1.0, 2.0, 4.0, 10.0, 20.0, 40.0, 100.0, 1e9) if v >= ymax)
    B, H, L, R, O, U = 360, 230, 34, 8, 18, 74
    pw, ph = B - L - R, H - O - U
    n, m = len(versionen), len(reihen)
    gruppe = pw / max(n, 1)
    bw = max(6, min(34, (gruppe - 10) / m - 2))
    teile = [f'<svg viewBox="0 0 {B} {H}" role="img" aria-label="{html.escape(titel)}">']
    for i in range(5):
        v = ymax * i / 4
        y = O + ph - ph * i / 4
        teile.append(f'<line class="grid" x1="{L}" x2="{B - R}" y1="{y:.1f}" y2="{y:.1f}"/>')
        teile.append(f'<text x="{L - 4}" y="{y + 3.5:.1f}" text-anchor="end">{fmt(v)}</text>')
    for gi, ver in enumerate(versionen):
        x0 = L + gi * gruppe + (gruppe - (m * bw + (m - 1) * 2)) / 2
        for ri, (name, werte, var) in enumerate(reihen):
            v = werte[gi]
            if v is None:
                continue
            h = ph * min(v, ymax) / ymax
            x, y = x0 + ri * (bw + 2), O + ph - h
            tip = html.escape(f"{ver} — {name}: {fmt(v)}")
            teile.append(f'<path class="bar" d="{balken(x, y, bw, h)}" fill="var({var})"><title>{tip}</title></path>')
            teile.append(f'<text class="val" x="{x + bw / 2:.1f}" y="{y - 3:.1f}" text-anchor="middle">{fmt(v)}</text>')
        cx = L + gi * gruppe + gruppe / 2
        teile.append(f'<text x="{cx:.1f}" y="{O + ph + 12}" text-anchor="end" '
                     f'transform="rotate(-35 {cx:.1f} {O + ph + 12})">{html.escape(ver)}</text>')
    teile.append("</svg>")
    legende = ""
    if m >= 2:
        legende = '<div class="legend">' + "".join(
            f'<span style="--c:var({var})">{html.escape(name)}</span>' for name, _, var in reihen) + "</div>"
    return (f'<div class="card"><h2>{html.escape(titel)}</h2><p>{html.escape(untertitel)}</p>'
            f'{legende}{"".join(teile)}</div>')


def schreibe_html(daten, pfad):
    vs = [d["version"] for d in daten]
    ganz = lambda v: f"{v:.0f}"
    dez = lambda v: f"{v:.2f}"
    col = lambda k: [d[k] for d in daten]
    n25 = max([d["n_mit_chunk"] or 0 for d in daten] + [1])
    karten = [
        diagramm("Retrieval: Recall@4", f"Quell-Chunk unter den Top-4 (von {n25})", vs,
                 [("exakt", col("recall4"), "--series-1"), ("inkl. Nachbar", col("recall4_nachbar"), "--series-2")],
                 n25, ganz),
        diagramm("Verweigerungen", "korrekt (von 8 nicht beantwortbaren) vs. falsch (von 22 beantwortbaren)", vs,
                 [("korrekt", col("verw_korrekt"), "--series-1"), ("falsch", col("verw_falsch"), "--series-2")],
                 max([d["verw_falsch"] or 0 for d in daten] + [8]), ganz),
        diagramm("Saubere vs. kritische Antworten", "Faithfulness ≥ 0.75 & nicht ausweichend / Faithfulness < 0.5", vs,
                 [("sauber", col("sauber"), "--series-1"), ("kritisch", col("kritisch"), "--series-2")],
                 max([d["sauber"] for d in daten] + [d["kritisch"] for d in daten] + [1]), ganz),
        diagramm("Faithfulness", "Mittelwert über beantwortete Fragen (0–1)", vs,
                 [("Faithfulness", col("faithfulness"), "--series-1")], 1.0, dez),
        diagramm("Answer Relevance", "Rohwert der nicht ausweichenden Antworten (0–1)", vs,
                 [("AR roh", col("ar_roh_nicht_ausweichend"), "--series-1")], 1.0, dez),
        diagramm("Ausweichende Antworten", "beantwortet, aber Gefragtes nicht geliefert (Anzahl)", vs,
                 [("ausweichend", col("ausweichend"), "--series-1")],
                 max([d["ausweichend"] for d in daten] + [1]), ganz),
        diagramm("Context Relevance", "Anteil benötigter Sätze im Kontext, beantwortete Fragen (0–1)", vs,
                 [("CR", col("context_relevance_beantwortet"), "--series-1")],
                 max([0.3] + [d["context_relevance_beantwortet"] or 0 for d in daten]), dez),
        diagramm("Antwortzeit", "Median pro Frage in Sekunden (ohne Modell-Ladezeit)", vs,
                 [("Sekunden", col("antwortzeit_median_s"), "--series-1")],
                 max([10] + [d["antwortzeit_median_s"] or 0 for d in daten]), lambda v: f"{v:.1f}"),
    ]
    spalten = ["version", "richter", "retrieval", "rrf_k", "temperatur", "recall4", "recall4_nachbar",
               "verw_korrekt", "verw_falsch", "beantwortet", "sauber", "kritisch", "faithfulness",
               "ausweichend", "ar_roh_nicht_ausweichend", "context_relevance_beantwortet", "antwortzeit_median_s"]
    f = lambda v: "–" if v is None or v == "" else (f"{v:.3f}" if isinstance(v, float) else html.escape(str(v)))
    tabelle = ("<table><thead><tr>" + "".join(f"<th>{s}</th>" for s in spalten) + "</tr></thead><tbody>"
               + "".join("<tr>" + "".join(f"<td>{f(d[s])}</td>" for s in spalten) + "</tr>" for d in daten)
               + "</tbody></table>")
    richter = sorted({d["richter"] for d in daten if d["richter"]})
    warnung = (f'<p class="note">⚠ Unterschiedliche Richter-Modelle im Vergleich: {", ".join(richter)} — '
               f'Werte nur bei gleichem Richter direkt vergleichbar.</p>') if len(richter) > 1 else ""
    seite = f"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Versionsvergleich</title>
<style>{CSS}</style></head><body class="viz-root"><main>
<h1>Lernassistent — Versionsvergleich</h1>
<p class="sub">{len(daten)} Versionen · Testfragen: {TESTFRAGEN} · Mauszeiger über Balken zeigt Werte</p>
{warnung}<div class="grid">{''.join(karten)}</div>
<div class="tablewrap">{tabelle}</div>
<p class="note">Einzelläufe mit 25–30 Fragen: Unterschiede von ±1–2 Fragen bzw. ±0.05 in Mittelwerten
liegen im Bereich der Lauf-zu-Lauf-Streuung.</p>
</main></body></html>"""
    pfad.write_text(seite, encoding="utf-8")


# =============================================================================
# main
# =============================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versionen", default=None, help="Kommagetrennte Archivordner in gewünschter Reihenfolge")
    ap.add_argument("--richter", default=None, help="nur Versionen mit diesem Richter-Modell")
    args = ap.parse_args()

    typ_von_frage = {q["frage"]: q["typ"] for q in lies_csv(TESTFRAGEN)}
    if args.versionen:
        ordner = [ARCHIV / v.strip() for v in args.versionen.split(",") if v.strip()]
    else:
        ordner = sorted(p for p in ARCHIV.iterdir() if (p / "ragas_ergebnisse.csv").exists())
    fehlend = [o.name for o in ordner if not (o / "ragas_ergebnisse.csv").exists()]
    if fehlend:
        print(f"Übersprungen (keine ragas_ergebnisse.csv): {', '.join(fehlend)}")
    daten = [werte_version(o, typ_von_frage) for o in ordner if (o / "ragas_ergebnisse.csv").exists()]
    if args.richter:
        daten = [d for d in daten if d["richter"] == args.richter]
    if not daten:
        print("Keine Versionen gefunden.")
        return

    fmt = lambda v: "–" if v is None or v == "" else (f"{v:.3f}" if isinstance(v, float) else str(v))
    kopf = ["version", "richter", "R@4", "R@4+Nb", "Verw.ok", "Verw.falsch", "sauber", "kritisch",
            "Faith", "ausw.", "AR roh", "CR beantw.", "Zeit s"]
    schl = ["version", "richter", "recall4", "recall4_nachbar", "verw_korrekt", "verw_falsch", "sauber", "kritisch",
            "faithfulness", "ausweichend", "ar_roh_nicht_ausweichend", "context_relevance_beantwortet",
            "antwortzeit_median_s"]
    breite = [max(len(k), *(len(fmt(d[s])) for d in daten)) for k, s in zip(kopf, schl)]
    print("  ".join(k.ljust(b) for k, b in zip(kopf, breite)))
    print("  ".join("-" * b for b in breite))
    for d in daten:
        print("  ".join(fmt(d[s]).ljust(b) for s, b in zip(schl, breite)))
    if len({d["richter"] for d in daten if d["richter"]}) > 1:
        print("\nWARNUNG: unterschiedliche Richter-Modelle — nur Versionen mit gleichem Richter vergleichen "
              "(--richter mistral-nemo).")

    csv_pfad = EVAL / "versionsvergleich.csv"
    with open(csv_pfad, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(daten[0].keys()))
        w.writeheader()
        w.writerows(daten)
    html_pfad = EVAL / "versionsvergleich.html"
    schreibe_html(daten, html_pfad)
    print(f"\nTabelle: {csv_pfad}\nDiagramme: {html_pfad}  (im Browser öffnen)")


if __name__ == "__main__":
    main()