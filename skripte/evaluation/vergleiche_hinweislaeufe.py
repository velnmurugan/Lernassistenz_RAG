#!/usr/bin/env python3
"""
vergleiche_hinweislaeufe.py  –  Vergleich zweier Hinweis-Dialogläufe (z. B. HD-V2 = V11B, HD-V3 = V11B + Wächter HG-v1)
------------------------------------------------------------------------------------------------------------------------
Aus ~/RAG:   python skripte/evaluation/vergleiche_hinweislaeufe.py HD-V2 HD-V3 [--seed 2028]
             python skripte/evaluation/vergleiche_hinweislaeufe.py HD-V3N          (ein Lauf: Hinweis vor gegen nach dem Wächter)

Liest evaluationsdaten/hinweis_dialog_<LABEL>_zustand.json. Ausgabe (evaluationsdaten/hinweis_vergleich_<A>_<B>_*):
  _zusammenfassung.txt   Wächter-Statistik, erste Hinweise gepaart (gleiche Frage), Rubrik P1-P6 je Lauf (Richter mistral-nemo)
  _paare_bogen.csv       BLIND: je Frage mit unterschiedlichem erstem Hinweis ein Paar (Text 1 / Text 2 in zufälliger Reihenfolge)
                         für die Handbewertung: Welcher Hinweis verrät weniger? (1 / 2 / gleich) + Welcher ist als Hilfe besser?
  _paare_schluessel.csv  Schlüssel (welcher Lauf = Text 1); erst nach der Bewertung öffnen
Lesehilfe: Der Richter (mistral-nemo, P1) ist ungeprüft; der Leck-Prüfer des Wächters hatte kappa <= 0.34. Verbindlich ist die
Handbewertung des Paarbogens (Vel, Prof. Zinn unabhängig). Verlauf der Dialoge unterscheidet sich ab Versuch 2 (andere simulierte
Antworten), deshalb werden nur ERSTE Hinweise gepaart; Rubrikanteile über alle Hinweise sind Orientierung.
"""
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ED = Path("evaluationsdaten")


def lade(label):
    p = ED / f"hinweis_dialog_{label}_zustand.json"
    if not p.exists():
        sys.exit(f"FEHLT: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def anteil(xs, wert):
    xs = [x for x in xs if x]
    return (sum(x == wert for x in xs) / len(xs)) if xs else float("nan"), len(xs)


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if not a:
        sys.exit(__doc__)
    seed = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else 2028
    if len(a) == 1:  # Innerhalb eines Laufs mit Wächter: Hinweis vor dem Wächter (A) gegen Hinweis nach dem Wächter (B)
        zb = lade(a[0])
        za = json.loads(json.dumps(zb))
        for s in za["q"].values():
            s["hinweis0"] = s.get("hinweis0_vor_waechter") or s.get("hinweis0", "")
        za["urteile"] = {}
        la, lb = a[0] + "_vor_Waechter", a[0]
    else:
        la, lb = a[0], a[1]
        za, zb = lade(la), lade(lb)
    L = [f"Vergleich der Hinweisläufe {la} (A) gegen {lb} (B)", ""]

    # --- Wächter-Statistik in B
    erste = [s for s in zb["q"].values() if s.get("ok")]
    w0 = [s.get("hinweis0_waechter", "") for s in erste]
    c0 = Counter(("kein Wächterlauf" if not w else w.split(" ")[1].split("->")[0]) for w in w0)
    L.append(f"Wächter bei ersten Hinweisen in {lb}: Urteil des Prüfers vor Eingriff: {dict(c0)}")
    L.append(f"  neu geschrieben: {sum(('neu=1' in w or 'neu=2' in w) for w in w0)}   Ersatz: {sum('ersatz=ja' in w for w in w0)}   von {len(w0)}")
    folge = [t for s in zb["q"].values() for t in s["turns"] if t.get("folgehinweis_waechter")]
    if folge:
        L.append(f"Wächter bei Folgehinweisen: {len(folge)}   neu geschrieben: {sum(('neu=1' in t['folgehinweis_waechter'] or 'neu=2' in t['folgehinweis_waechter']) for t in folge)}"
                 f"   Ersatz: {sum('ersatz=ja' in t['folgehinweis_waechter'] for t in folge)}")
    L.append("")

    # --- erste Hinweise gepaart
    gem = sorted(set(za["q"]) & set(zb["q"]))
    paare, gleich = [], 0
    for i in gem:
        sa, sb = za["q"][i], zb["q"][i]
        if not (sa.get("ok") and sb.get("ok")):
            continue
        ha, hb = (sa.get("hinweis0") or "").strip(), (sb.get("hinweis0") or "").strip()
        if ha == hb:
            gleich += 1
        else:
            paare.append((i, sa, sb, ha, hb))
    L.append(f"Erste Hinweise, gleiche Frage in beiden Läufen: {gleich + len(paare)}; identisch: {gleich}; verschieden: {len(paare)}")
    vor = [(i, sb) for i, sa, sb, ha, hb in paare if sb.get("hinweis0_vor_waechter")]
    if vor:
        ident_vor = sum((sb["hinweis0_vor_waechter"].strip() == ha) for i, sa, sb, ha, hb in paare if sb.get("hinweis0_vor_waechter"))
        L.append(f"  davon vor dem Wächter schon gleich dem Hinweis von {la}: {ident_vor} von {len(vor)} "
                 f"(zeigt, ob die Pipeline reproduzierbar ist; Rest: Wächter hat eingegriffen)")
    L.append("")

    # --- Rubrik
    def rubrik(z, nur_erste):
        res = {}
        for k, u in z.get("urteile", {}).items():
            if u.get("art") != "hinweis":
                continue
            if nur_erste and not k.endswith("-H1"):
                continue
            for p in ("P1", "P2", "P3", "P4", "P5", "P6"):
                res.setdefault(p, []).append(u.get(p, ""))
        return res
    for titel, nur in (("Alle Hinweise", False), ("Nur erste Hinweise", True)):
        L.append(f"Rubrik (Richter mistral-nemo), {titel}: Anteil 'ja'")
        ra, rb = rubrik(za, nur), rubrik(zb, nur)
        for p in ("P1", "P2", "P3", "P4", "P5", "P6"):
            (xa, na), (xb, nb) = anteil(ra.get(p, []), "ja"), anteil(rb.get(p, []), "ja")
            L.append(f"  {p}: {la} {xa:.0%} (n={na})   {lb} {xb:.0%} (n={nb})")
        L.append("")

    # --- Paarbogen
    rnd = random.Random(seed)
    bogen, schl = [], []
    for k, (i, sa, sb, ha, hb) in enumerate(paare, 1):
        tauschen = rnd.random() < 0.5
        t1, t2 = (hb, ha) if tauschen else (ha, hb)
        bogen.append({"nr": k, "frage": sa["frage"], "loesung_referenz": sa.get("loesung", ""), "text_1": t1, "text_2": t2,
                      "verraet_weniger (1/2/gleich)": "", "bessere_hilfe (1/2/gleich)": "", "bemerkung": ""})
        schl.append({"nr": k, "id": i, "text_1": lb if tauschen else la, "text_2": la if tauschen else lb})
    base = ED / f"hinweis_vergleich_{la}_{lb}"
    for name, felder, zeilen in (("_paare_bogen.csv", list(bogen[0].keys()) if bogen else ["nr"], bogen),
                                 ("_paare_schluessel.csv", ["nr", "id", "text_1", "text_2"], schl)):
        with open(str(base) + name, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=felder)
            w.writeheader()
            w.writerows(zeilen)
    Path(str(base) + "_zusammenfassung.txt").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\nDateien: {base}_zusammenfassung.txt, _paare_bogen.csv ({len(paare)} Paare, blind), _paare_schluessel.csv")


if __name__ == "__main__":
    main()
