#!/usr/bin/env python3
"""
teste_hinweis_stabilitaet.py  –  Reproduzierbarkeit und Rauschen der Hinweis-Erzeugung (unbeaufsichtigt, ein Befehl)
-------------------------------------------------------------------------------------------------------------------
Anlass: Im Lauf HO-V1 stimmten neu erzeugte Basis-Hinweise nur in 0 von 8 Fällen mit den gespeicherten überein (T=0,
Seed 42), und der Wächter V1 sah nur "8 besser / 3 schlechter" gegenüber der Basis (p = 0.23). Offen ist, (a) warum die
Hinweise trotz T=0 nicht reproduzierbar sind und (b) wie groß das Rauschen der Erzeugung gegenüber dem beobachteten
Unterschied ist. Dieses Skript ändert nichts an der Pipeline (V11B bleibt eingefroren) und führt keine neue Variante ein.

  Teil A  Reproduzierbarkeit (kurz)
    A1  8 gespeicherte Basis-Hinweise werden unter vier Bedingungen neu erzeugt: dreimal direkt hintereinander (D),
        dreimal mit einer anderen Situation dazwischen (Z), zweimal mit einem Modellwechsel dazwischen (M, wie im
        Dialogtest, wo Simulator und Richter zwischen den Hinweisen liefen). Verglichen wird mit dem gespeicherten Hinweis.
    A2  Stabilität der Leck-Prüfer: alle Basis-Hinweise werden von den beiden Prüfern erneut beurteilt und mit den
        gespeicherten Urteilen aus HO-V1 verglichen; ein Teil wird ein drittes Mal geprüft.
  Teil B  Rauschen der Erzeugung (lang)
    Runden mit allen Situationen aus HD-V2, jeweils Basis (B') und Basis + Wächter (V1') aus demselben Entwurf, in
    zufälliger Reihenfolge je Runde. Zwei Einstellungen im Wechsel:
      T0   Temperatur 0, Seed 42 (wie in der App); Unterschiede zwischen Runden entstehen nur durch den Aufrufzustand
      T03  Temperatur 0.3, je Runde anderer Seed (echte Stichprobenschwankung der Erzeugung)
    Beurteilung durch den unabhängigen Leck-Prüfer (granite4.1:8b / C2); Wächter qwen3.5:9b / C2 (beste Prüfer aus HO-V1).
    Ausgewertet: Leck-Rate je Runde, gepaarter Vergleich V1' gegen B', Bootstrap-Intervall über Situationen, Rauschen
    zwischen den Runden (B' gegen B'), Anteil identischer Hinweise, objektive Kennzahlen.
    Die Rundenzahl richtet sich nach --max-stunden (Standard 9): neue Runden starten nur, wenn sie ins Budget passen. Sind T0-1 und T0-2
    praktisch identisch (>= 98 %), entfallen weitere T0-Runden; das Budget geht dann an T03.

Grenzen (stehen auch in der Zusammenfassung): Die Leck-Prüfer erreichten gegen Referenzurteile nur kappa 0.28-0.34; die
Leck-Raten sind Orientierung, kein Beleg. Teil B misst Stabilität und Rauschen, nicht den wahren Leck-Anteil. Entwicklungsdaten
(N100 ist kein Held-out-Satz). Verbindlich bleibt der Bewertungsbogen (zwei Menschen).

Start (aus ~/RAG, Umgebung pilot_rag aktiv, Ollama läuft, Vordergrund, Rechner nicht in den Ruhezustand gehen lassen):
    python skripte/evaluation/teste_hinweis_stabilitaet.py 2>&1 | tee evaluationsdaten/hinweis_stab_HS-V1_log.txt
Laufzeit: Rauchtest ca. 10 min, Teil A ca. 40-60 min, Teil B je Runde grob 45-90 min (Schätzung wird nach dem Rauchtest
ausgegeben), insgesamt höchstens --max-stunden. Bricht man ab, setzt derselbe Befehl fort.
Voraussetzung: evaluationsdaten/hinweis_dialog_HD-V2_zustand.json; optional hinweis_opt_HO-V1_zustand.json (Vergleich der
Prüferurteile); Modelle qwen3.5:9b, granite4.1:8b (fehlt er, mistral-nemo als Prüfer und Modellwechsel).
Ergebnisse: evaluationsdaten/hinweis_stab_<LABEL>_zusammenfassung.txt, _hinweise.csv, _teilA.csv, _zustand.json
"""
import sys as _sys
import pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import optimiere_hinweise as oh  # noqa: E402
import teste_hinweis_dialog as hd  # noqa: E402

import argparse  # noqa: E402
import datetime  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import random  # noqa: E402
import statistics  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

rp = hd.rag_pipeline
VERSION = "HS-v1"
OBJ_FELDER = ("zahlleck", "zu_lang", "endet_frage", "ja_nein", "material", "erfunden", "wiederholung", "bezug_antwort")


def h6(text):
    return oh.md5(text)


def erzeuge2(prompt, s, opt):
    """Wie oh.erzeuge, aber mit frei wählbaren Optionen (Temperatur/Seed)."""
    roh = rp.frage_llm(prompt, options=opt)
    h, _ = rp.parse_hinweis(roh)
    if not h:
        return "", "format_fehler"
    st = {"hinweis": h, "loesung": s["loesung"], "status": s["status"]}
    rp.hinweis_pruefen(s["frage"], st)
    return st["hinweis"], st.get("hinweis_pruefung", "")


def modellwechsel(modell):
    hd.llm(modell, "Antworte nur mit: ok", {"temperature": 0, "seed": 1, "num_predict": 4})


def pruefer_frisch(cfg, sz, hinweis):
    modell, pid = cfg
    roh = hd.llm(modell, oh.pruefer_prompt(pid, sz, hinweis), {"temperature": 0, "seed": 42, "num_predict": 450 if pid == "C1" else 160})
    return oh.parse_pruefer(roh)["urteil"]


def ollama_info(modelle):
    info = {}
    try:
        import requests
        base = rp.OLLAMA_URL.replace("/api/generate", "")
        info["version"] = requests.get(base + "/api/version", timeout=20).json().get("version", "?")
        tags = requests.get(base + "/api/tags", timeout=20).json().get("models", [])
        info["modelle"] = {m["name"]: m.get("digest", "")[:12] for m in tags if any(m["name"].startswith(x.split(":")[0]) for x in modelle)}
    except Exception as e:  # noqa: BLE001
        info["fehler"] = str(e)
    info["optionen"] = dict(rp.GENERIERUNGS_OPTIONEN)
    return info


# ------------------------------------------------------------------------------------------------ Teil A
def teil_a1(args, zustand, alle, pfad, t0, wechsel_modell):
    if "A1" in zustand:
        return
    n = 2 if args.limit else 8
    schritt = max(1, len(alle) // n)
    auswahl = alle[::schritt][:n]
    hd.stunde(t0, f"Teil A1: Reproduzierbarkeit an {len(auswahl)} Hinweisen (D, Z, M)")
    opt = dict(rp.GENERIERUNGS_OPTIONEN)
    A1 = []
    for i, sz in enumerate(auswahl, 1):
        andere = alle[(alle.index(sz) + 17) % len(alle)]

        def gen(x):
            return erzeuge2(oh.prompt_basis(x), x["s"], opt)[0].strip()

        gesp = sz["hinweis_b"].strip()
        rec = {"key": sz["key"], "n": sz["n"], "gespeichert": gesp, "D": [], "Z": [], "M": []}
        for _ in range(3):
            rec["D"].append(gen(sz))
        for _ in range(3):
            rec["Z"].append(gen(sz))
            gen(andere)
        for _ in range(2):
            rec["M"].append(gen(sz))
            modellwechsel(wechsel_modell)
        A1.append(rec)
        print(f"  [{i}/{len(auswahl)}] {sz['key']:<8} D={[h6(x) for x in rec['D']]} Z={[h6(x) for x in rec['Z']]} "
              f"M={[h6(x) for x in rec['M']]} gespeichert={h6(gesp)}", flush=True)
    zustand["A1"] = A1
    hd.speichere(zustand, pfad)


def teil_a2(args, zustand, alle, pfad, t0, eval_cfg, waechter_cfg):
    if "A2" in zustand:
        return
    hd.stunde(t0, "Teil A2: Stabilität der Leck-Prüfer (Basis-Hinweise erneut beurteilt)")
    alt = {}
    ho = Path("evaluationsdaten/hinweis_opt_HO-V1_zustand.json")
    if ho.exists():
        alt = json.loads(ho.read_text(encoding="utf-8")).get("leck", {})
    sz_liste = alle[:3] if args.limit else alle
    drittel = sz_liste[:3] if args.limit else sz_liste[:40]
    A2 = {}
    for cfg in (eval_cfg, waechter_cfg):
        name = f"{cfg[0]}|{cfg[1]}"
        r = {"zweiter": {}, "dritter": {}, "gespeichert": {}}
        A2[name] = r
    for cfg in (eval_cfg, waechter_cfg):
        name = f"{cfg[0]}|{cfg[1]}"
        for sz in sz_liste:
            k = f"{sz['key']}|{h6(sz['hinweis_b'])}"
            A2[name]["zweiter"][k] = pruefer_frisch(cfg, sz, sz["hinweis_b"])
            g = alt.get(name, {}).get(k, {}).get("urteil")
            if g:
                A2[name]["gespeichert"][k] = g
        hd.stunde(t0, f"  {name}: {len(sz_liste)} Urteile erneut erzeugt")
    for cfg in (eval_cfg, waechter_cfg):  # dritter Durchgang nach Modellwechsel
        name = f"{cfg[0]}|{cfg[1]}"
        for sz in drittel:
            k = f"{sz['key']}|{h6(sz['hinweis_b'])}"
            A2[name]["dritter"][k] = pruefer_frisch(cfg, sz, sz["hinweis_b"])
    zustand["A2"] = A2
    hd.speichere(zustand, pfad)


def a2_kennzahlen(r):
    def vergleich(a, b):
        ks = [k for k in a if k in b and a[k] in oh.LECK_STUFE and b[k] in oh.LECK_STUFE]
        if not ks:
            return None
        gleich = sum(a[k] == b[k] for k in ks) / len(ks)
        bin_gleich = sum((a[k] == "leck") == (b[k] == "leck") for k in ks) / len(ks)
        kw = oh.kappa([oh.LECK_STUFE[a[k]] for k in ks], [oh.LECK_STUFE[b[k]] for k in ks], True)
        return {"n": len(ks), "gleich": gleich, "bin_gleich": bin_gleich, "kappa_w": kw}
    return {"gespeichert_vs_neu": vergleich(r["gespeichert"], r["zweiter"]),
            "neu_vs_dritter": vergleich(r["zweiter"], r["dritter"])}


# ------------------------------------------------------------------------------------------------ Teil B
def waechter(sz, entwurf, opt, waechter_cfg, zustand, max_neu):
    hinweis = entwurf
    retries = 0
    urt = oh.leck_pruefung(waechter_cfg, sz, hinweis, zustand)
    while urt["urteil"] == "leck" and retries < max_neu:
        retries += 1
        zusatz = (f"\n\nACHTUNG: Dein letzter Entwurf war:\n\"{hinweis}\"\nEr verrät laut Prüfung: {urt['genannt'] or 'einen Baustein der Lösung'}. "
                  f"Schreibe einen neuen Hinweis als engere Frage, die das weder nennt noch umschreibt noch als Auswahl anbietet.")
        neu, _ = erzeuge2(oh.prompt_basis(sz) + zusatz, sz["s"], opt)
        if not neu:
            break
        hinweis = neu
        urt = oh.leck_pruefung(waechter_cfg, sz, hinweis, zustand)
    ersatz = urt["urteil"] == "leck"
    if ersatz:
        hinweis = oh.ERSATZ_HINWEIS
    return hinweis, retries, ersatz


def runden_optionen(setting, r):
    opt = dict(rp.GENERIERUNGS_OPTIONEN)
    if setting == "T03":
        opt["temperature"] = 0.3
        opt["seed"] = 1000 + r
    return opt


def runde(args, zustand, alle, name, pfad, t0, eval_cfg, waechter_cfg):
    setting, r = name.split("-")
    r = int(r)
    R = zustand["runden"].setdefault(name, {"gen": {}, "eval": {}, "fertig": False, "dauer": 0.0})
    if R["fertig"]:
        return
    z0 = time.time()
    opt = runden_optionen(setting, r)
    reihenfolge = list(alle)
    random.Random(args.seed + r * (1 if setting == "T0" else 97)).shuffle(reihenfolge)
    hd.stunde(t0, f"Runde {name}: Erzeugung B' und V1' ({len(alle)} Situationen, Optionen {opt})")
    for i, sz in enumerate(reihenfolge, 1):
        k = sz["key"]
        if k in R["gen"]:
            continue
        b, hp = erzeuge2(oh.prompt_basis(sz), sz["s"], opt)
        fehler = not b
        if fehler:
            b = sz["hinweis_b"]
        v1, retries, ersatz = waechter(sz, b, opt, waechter_cfg, zustand, args.max_neu)
        R["gen"][k] = {"B": b, "V1": v1, "retries": retries, "ersatz": ersatz, "format_fehler": fehler}
        if i % 10 == 0 or i == len(reihenfolge):
            hd.speichere(zustand, pfad)
            print(f"  [{i}/{len(reihenfolge)}] {k:<8} neu={retries} ersatz={ersatz} ({(time.time() - z0) / 60:.0f} min)", flush=True)
    hd.stunde(t0, f"Runde {name}: Beurteilung durch {eval_cfg[0]}/{eval_cfg[1]}")
    for i, sz in enumerate(alle, 1):
        k = sz["key"]
        if k in R["eval"]:
            continue
        g = R["gen"][k]
        e = {}
        for v in ("B", "V1"):
            u = oh.leck_pruefung(eval_cfg, sz, g[v], zustand)["urteil"]
            o = oh.objektiv(sz, g[v])
            e[v] = {"urteil": u, **{f: (None if o.get(f) == "" else bool(o.get(f))) for f in OBJ_FELDER}}
        R["eval"][k] = e
        if i % 20 == 0 or i == len(alle):
            hd.speichere(zustand, pfad)
    if "B0" not in zustand:  # gespeicherte Basis-Hinweise, einmal beurteilt
        zustand["B0"] = {}
    for sz in alle:
        if sz["key"] not in zustand["B0"]:
            zustand["B0"][sz["key"]] = oh.leck_pruefung(eval_cfg, sz, sz["hinweis_b"], zustand)["urteil"]
    R["dauer"] = time.time() - z0
    R["fertig"] = True
    hd.speichere(zustand, pfad)
    hd.stunde(t0, f"Runde {name} fertig in {R['dauer'] / 60:.0f} min")


# ---------------------------------------------------------------------------------------- Auswertung
def anteil(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def bootstrap(werte, seed=7, n=2000):
    if not werte:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    m = len(werte)
    ms = sorted(sum(werte[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return sum(werte) / m, ms[int(0.025 * n)], ms[int(0.975 * n)]


def auswertung(zustand, alle, label, args, t0, eval_cfg, waechter_cfg, rauch):
    L = []
    P = L.append
    runden = {k: v for k, v in zustand["runden"].items() if v["fertig"]}
    P(f"Stabilität der Hinweis-Erzeugung {label} ({VERSION})  {datetime.datetime.now():%d.%m.%Y %H:%M}")
    P(f"Situationen: {len(alle)} aus HD-V2 (Versuch 1: {sum(1 for s in alle if s['n'] == 1)}, 2: {sum(1 for s in alle if s['n'] == 2)}, "
      f"3: {sum(1 for s in alle if s['n'] == 3)}); Generator {rp.MODEL_NAME}; Beurteilung {eval_cfg[0]}/{eval_cfg[1]}; Wächter {waechter_cfg[0]}/{waechter_cfg[1]}")
    P(f"Umgebung: {json.dumps(zustand.get('umgebung', {}), ensure_ascii=False)}")
    P("")
    P("HINWEIS: Die Leck-Prüfer erreichten in HO-V1 nur kappa 0.28-0.34 gegen Referenzurteile. Alle Leck-Raten unten sind Orientierung zur")
    P("Stabilität, kein Maß des wahren Leck-Anteils. Verbindlich ist der Bewertungsbogen (zwei Menschen).")
    P("")
    # ---- Teil A1
    A1 = zustand.get("A1", [])
    if A1:
        P("=== Teil A1: Reproduzierbarkeit (Basis-Hinweise, T=0, Seed 42)")
        tab = {"D": "direkt hintereinander (3x)", "Z": "andere Situation dazwischen (3x)", "M": "Modellwechsel dazwischen (2x)"}
        for c, text in tab.items():
            gleich_ges = sum(1 for rec in A1 for x in rec[c] if x == rec["gespeichert"])
            alle_ges = sum(len(rec[c]) for rec in A1)
            intern = sum(1 for rec in A1 if len(set(rec[c])) == 1)
            P(f"  {text:<40} gleich dem gespeicherten Hinweis: {gleich_ges}/{alle_ges}   Aufrufe untereinander identisch: {intern}/{len(A1)} Hinweise")
        zw = sum(1 for rec in A1 if rec["D"][0] == rec["Z"][0] == rec["M"][0])
        zw2 = sum(1 for rec in A1 if len({rec["D"][-1], rec["Z"][-1], rec["M"][-1]}) == 1)
        P(f"  erster Aufruf aller Bedingungen identisch: {zw}/{len(A1)}; letzter Aufruf aller Bedingungen identisch: {zw2}/{len(A1)}")
        beste = max(tab, key=lambda c: sum(1 for rec in A1 for x in rec[c] if x == rec["gespeichert"]))
        P(f"  Bedingung mit den meisten Treffern gegen den gespeicherten Hinweis: {beste}")
        if all(sum(1 for rec in A1 for x in rec[c] if x == rec["gespeichert"]) == 0 for c in tab):
            P("  -> Keine Bedingung reproduziert den gespeicherten Hinweis. Der Dialogtest lief mit anderem Aufrufzustand (Simulator, Richter, andere")
            P("     Hinweise zwischen den Aufrufen) oder anderer Software-Version; Reproduzierbarkeit nur für dieselbe Aufrufreihenfolge zusichern.")
        P("")
    # ---- Teil A2
    A2 = zustand.get("A2", {})
    if A2:
        P("=== Teil A2: Stabilität der Leck-Prüfer (T=0, Seed 42)")
        for name, r in A2.items():
            k = a2_kennzahlen(r)
            for titel, v in (("gespeicherte Urteile (HO-V1) gegen neu", k["gespeichert_vs_neu"]), ("neu gegen dritter Durchgang", k["neu_vs_dritter"])):
                if v:
                    P(f"  {name:<22} {titel:<40} n={v['n']:<4} identisch {v['gleich']:.0%}  Leck ja/nein identisch {v['bin_gleich']:.0%}  kappa_w {v['kappa_w']:.2f}")
                else:
                    P(f"  {name:<22} {titel:<40} nicht verfügbar")
        P("")
    # ---- Teil B
    if runden:
        P(f"=== Teil B: {len(runden)} Runden (fertig); Beurteilung durch {eval_cfg[0]}/{eval_cfg[1]}")
        P("Je Runde (Anteile über alle Situationen; Leck = Urteil 'leck', Leck+ = 'leck' oder 'teilweise'):")
        P(f"  {'Runde':<7}{'Min.':>6}{'B Leck':>9}{'B Leck+':>9}{'V1 Leck':>9}{'V1 Leck+':>10}{'Ersatz':>8}{'Neu/Hw':>8}{'V1=B':>7}   gepaart V1 gegen B (besser/schlechter, p)")
        pro_setting = {"T0": [], "T03": []}
        for name in sorted(runden, key=lambda x: (x.split('-')[0], int(x.split('-')[1]))):
            R = runden[name]
            ks = [sz["key"] for sz in alle]
            bL = [R["eval"][k]["B"]["urteil"] == "leck" for k in ks]
            bP = [R["eval"][k]["B"]["urteil"] in ("leck", "teilweise") for k in ks]
            vL = [R["eval"][k]["V1"]["urteil"] == "leck" for k in ks]
            vP = [R["eval"][k]["V1"]["urteil"] in ("leck", "teilweise") for k in ks]
            ers = anteil([R["gen"][k]["ersatz"] for k in ks])
            neu = anteil([R["gen"][k]["retries"] for k in ks])
            gleich = anteil([R["gen"][k]["B"] == R["gen"][k]["V1"] for k in ks])
            besser = sum(1 for a, b in zip(bL, vL) if a and not b)
            schlechter = sum(1 for a, b in zip(bL, vL) if b and not a)
            p = oh.vorzeichentest(besser, schlechter)
            P(f"  {name:<7}{R['dauer'] / 60:>6.0f}{anteil(bL):>9.0%}{anteil(bP):>9.0%}{anteil(vL):>9.0%}{anteil(vP):>10.0%}{ers:>8.0%}{neu:>8.2f}{gleich:>7.0%}   {besser}/{schlechter}  p={p:.2f}")
            pro_setting[name.split("-")[0]].append((name, bL, vL, bP, vP))
        B0 = zustand.get("B0", {})
        if B0:
            b0 = [B0[sz["key"]] == "leck" for sz in alle if sz["key"] in B0]
            P(f"  gespeicherte Basis (B0, gleiche Beurteilung): Leck {anteil(b0):.0%}")
        P("")
        P("Unterschied V1' gegen B' (Leck-Rate B minus V1, Prozentpunkte; positiv = Wächter besser), Bootstrap über Situationen (95 %):")
        for st, liste in pro_setting.items():
            if not liste:
                continue
            d = []
            for i in range(len(alle)):
                d.append(anteil([int(b[i]) - int(v[i]) for _, b, v, _, _ in liste]))
            m, lo, hi = bootstrap(d)
            dP = [anteil([int(bp[i]) - int(vp[i]) for _, _, _, bp, vp in liste]) for i in range(len(alle))]
            mp, lop, hip = bootstrap(dP)
            rundenwerte = [100 * (anteil(b) - anteil(v)) for _, b, v, _, _ in liste]
            P(f"  {st:<4} Leck: {100 * m:+.1f} pp [{100 * lo:+.1f}; {100 * hi:+.1f}]   Leck+: {100 * mp:+.1f} pp [{100 * lop:+.1f}; {100 * hip:+.1f}]   "
              f"je Runde Leck: {', '.join(f'{x:+.1f}' for x in rundenwerte)}   ({len(liste)} Runden)")
        P("")
        P("Rauschen der Erzeugung (B' gegen B' zwischen zwei Runden derselben Einstellung):")
        rausch = {}
        for st, liste in pro_setting.items():
            if len(liste) < 2:
                continue
            diffs, wechsel, ident = [], [], []
            for i in range(len(liste)):
                for j in range(i + 1, len(liste)):
                    (na, ba, _, _, _), (nb, bb, _, _, _) = liste[i], liste[j]
                    diffs.append(abs(anteil(ba) - anteil(bb)) * 100)
                    wechsel.append(sum(1 for x, y in zip(ba, bb) if x != y))
                    Ra, Rb = runden[na], runden[nb]
                    ident.append(anteil([Ra["gen"][sz["key"]]["B"] == Rb["gen"][sz["key"]]["B"] for sz in alle]))
            rausch[st] = (statistics.mean(diffs), max(diffs))
            P(f"  {st:<4} Leck-Rate zwischen Runden: im Mittel {statistics.mean(diffs):.1f} pp (max. {max(diffs):.1f} pp); Situationen mit anderem Urteil: im Mittel "
              f"{statistics.mean(wechsel):.0f} von {len(alle)}; identischer Hinweis in zwei Runden: {statistics.mean(ident):.0%}")
        P("")
        P("Objektive Kennzahlen (Mittel über Runden und Situationen):")
        P(f"  {'':<8}" + "".join(f"{f:>16}" for f in OBJ_FELDER))
        for v, bez in (("B", "B'"), ("V1", "V1'")):
            zeile = f"  {bez:<8}"
            for f in OBJ_FELDER:
                xs = [R["eval"][sz["key"]][v][f] for R in runden.values() for sz in alle if R["eval"][sz["key"]][v][f] is not None]
                zeile += f"{anteil([int(x) for x in xs]):>16.0%}"
            P(zeile)
        P("")
        P("Einordnung (Leck laut Prüfer):")
        for st, liste in pro_setting.items():
            if not liste:
                continue
            d = [anteil([int(b[i]) - int(v[i]) for _, b, v, _, _ in liste]) for i in range(len(alle))]
            m, lo, hi = bootstrap(d)
            rn = rausch.get(st)
            if lo > 0:
                bew = "Intervall liegt über 0: der Wächter senkt die Leck-Rate laut Prüfer"
            elif hi < 0:
                bew = "Intervall liegt unter 0: der Wächter erhöht die Leck-Rate laut Prüfer"
            else:
                bew = "Intervall schließt 0 ein: kein belastbarer Unterschied laut Prüfer"
            P(f"  {st}: {100 * m:+.1f} pp [{100 * lo:+.1f}; {100 * hi:+.1f}] -> {bew}"
              + (f"; Rauschen zwischen Runden im Mittel {rn[0]:.1f} pp" if rn else ""))
        P("  Auch ein belastbarer Unterschied laut Prüfer ist kein Beleg: der Prüfer ist schwach (kappa <= 0.34). Entscheidend ist der Vergleich der")
        P("  menschlichen Bewertungen (Bewertungsbogen HO-V1).")
    P("")
    P("Grenzen: Replay mit festen früheren Verläufen; Entwicklungsdaten; schwache Leck-Prüfer; T0-Runden messen nur den Einfluss des Aufrufzustands,")
    P("T03-Runden die Schwankung bei Temperatur 0.3 (nicht die Einstellung der App).")
    P(f"Gesamtdauer: {(time.time() - t0) / 60:.0f} min")
    text = "\n".join(L)
    Path(f"evaluationsdaten/hinweis_stab_{label}_zusammenfassung.txt").write_text(text, encoding="utf-8")
    # CSV
    felder = ["runde", "key", "versuch", "B_hinweis", "B_urteil", "V1_hinweis", "V1_urteil", "retries", "ersatz", "format_fehler"]
    zeilen = []
    for name, R in sorted(runden.items()):
        for sz in alle:
            g, e = R["gen"][sz["key"]], R["eval"][sz["key"]]
            zeilen.append({"runde": name, "key": sz["key"], "versuch": sz["n"], "B_hinweis": g["B"], "B_urteil": e["B"]["urteil"],
                           "V1_hinweis": g["V1"], "V1_urteil": e["V1"]["urteil"], "retries": g["retries"], "ersatz": g["ersatz"],
                           "format_fehler": g["format_fehler"]})
    hd.schreibe_csv(f"evaluationsdaten/hinweis_stab_{label}_hinweise.csv", felder, zeilen)
    zl = []
    for rec in zustand.get("A1", []):
        for c in ("D", "Z", "M"):
            for i, x in enumerate(rec[c], 1):
                zl.append({"key": rec["key"], "versuch": rec["n"], "bedingung": c, "aufruf": i, "gleich_gespeichert": x == rec["gespeichert"],
                           "hinweis": x, "gespeichert": rec["gespeichert"]})
    hd.schreibe_csv(f"evaluationsdaten/hinweis_stab_{label}_teilA.csv", ["key", "versuch", "bedingung", "aufruf", "gleich_gespeichert", "hinweis", "gespeichert"], zl)
    print("\n" + text)
    return [f"evaluationsdaten/hinweis_stab_{label}_zusammenfassung.txt", f"evaluationsdaten/hinweis_stab_{label}_hinweise.csv",
            f"evaluationsdaten/hinweis_stab_{label}_teilA.csv"]


def doku_und_git(label, dateien):
    text = (f"Stabilität der Hinweis-Erzeugung {label} ({datetime.date.today():%d %b %Y}): Teil A prüft, ob neu erzeugte Basis-Hinweise bei T=0/Seed 42 "
            f"den gespeicherten gleichen (direkt, mit anderer Situation, mit Modellwechsel dazwischen) und wie stabil die Leck-Prüfer sind; Teil B erzeugt "
            f"Basis und Basis+Wächter in mehreren Runden (T0 und Temperatur 0.3) und vergleicht den Unterschied mit dem Rauschen. "
            f"Skript skripte/evaluation/teste_hinweis_stabilitaet.py; Ergebnisse evaluationsdaten/hinweis_stab_{label}_*. Entwicklungsbefund, kein Beleg im Beitrag.")
    marke = f"## Stabilität Hinweise {label}"
    for f in ("README.md", *glob.glob("PROZESSABLAUF.md"), *glob.glob("doku/PROZESSABLAUF.md"), *glob.glob("docs/PROZESSABLAUF.md")):
        p = Path(f)
        if p.exists() and marke not in p.read_text(encoding="utf-8"):
            with open(p, "a", encoding="utf-8") as fh:
                fh.write(f"\n{marke}\n{text}\n")
            print(f"{f}: Abschnitt angehängt.")
    if Path(".git").is_dir():
        subprocess.run(["git", "add", "-A"], check=False)
        r = subprocess.run(["git", "commit", "-q", "-m", f"Stabilität der Hinweis-Erzeugung {label}: Skript und Ergebnisse"], check=False)
        print("Commit angelegt." if r.returncode == 0 else "Nichts zu committen.")
    print("Ergebnisse (WSL): ~/RAG/evaluationsdaten/ -> " + ", ".join(Path(d).name for d in dateien))


# ------------------------------------------------------------------------------------------------ Lauf
def lauf(args, label, alle, rauch, t0, eval_cfg, waechter_cfg, wechsel_modell):
    pfad = Path(f"evaluationsdaten/hinweis_stab_{label}_zustand.json")
    zustand = json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}
    if pfad.exists():
        print(f"Fortsetzung aus {pfad}")
    zustand.setdefault("leck", {})
    zustand.setdefault("runden", {})
    zustand["umgebung"] = ollama_info([rp.MODEL_NAME, eval_cfg[0], wechsel_modell])
    hd.speichere(zustand, pfad)
    print(f"Umgebung: {zustand['umgebung']}")
    teil_a1(args, zustand, alle, pfad, t0, wechsel_modell)
    teil_a2(args, zustand, alle, pfad, t0, eval_cfg, waechter_cfg)
    folge = []
    for r in range(1, (1 if rauch else args.max_runden) + 1):
        folge += [f"T0-{r}", f"T03-{r}"]
    budget = args.max_stunden * 3600
    for name in folge:
        if name.startswith("T0-") and int(name.split("-")[1]) >= 3 and not rauch:
            ra, rb = zustand["runden"].get("T0-1", {}), zustand["runden"].get("T0-2", {})
            if ra.get("fertig") and rb.get("fertig"):
                gl = anteil([ra["gen"][sz["key"]]["B"] == rb["gen"][sz["key"]]["B"] and ra["gen"][sz["key"]]["V1"] == rb["gen"][sz["key"]]["V1"] for sz in alle])
                if gl >= 0.98 and not zustand["runden"].get(name, {}).get("gen"):
                    print(f"Runde {name} entfällt: T0-1 und T0-2 sind zu {gl:.0%} identisch, weitere T0-Runden bringen nichts Neues.")
                    continue
        fertig = [v["dauer"] for v in zustand["runden"].values() if v["fertig"]]
        if not rauch and fertig and not zustand["runden"].get(name, {}).get("gen"):
            geschaetzt = max(fertig) * 1.15
            if time.time() - t0 + geschaetzt > budget:
                print(f"Budget von {args.max_stunden} h erreicht; Runde {name} würde ca. {geschaetzt / 60:.0f} min brauchen und startet nicht.")
                break
        runde(args, zustand, alle, name, pfad, t0, eval_cfg, waechter_cfg)
    if rauch:
        d = [v["dauer"] for v in zustand["runden"].values() if v["fertig"]]
        if d:
            pro = statistics.mean(d) / len(alle)
            zustand["pro_situation_s"] = pro
            hd.speichere(zustand, pfad)
    return auswertung(zustand, alle, label, args, t0, eval_cfg, waechter_cfg, rauch), zustand


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="HS-V1")
    ap.add_argument("--basis", default=oh.BASIS_LABEL)
    ap.add_argument("--eval-modell", default="granite4.1:8b", help="unabhängiger Leck-Prüfer (Prompt C2); fehlt er, mistral-nemo")
    ap.add_argument("--richter", default="mistral-nemo")
    ap.add_argument("--max-neu", type=int, default=2)
    ap.add_argument("--max-stunden", type=float, default=9.0, help="Zeitbudget; neue Runden starten nur, wenn sie hineinpassen")
    ap.add_argument("--max-runden", type=int, default=6, help="höchstens so viele Runden je Einstellung (T0, T03)")
    ap.add_argument("--limit", type=int, default=0, help="nur so viele Situationen (Test)")
    ap.add_argument("--ohne-rauchtest", action="store_true")
    ap.add_argument("--seed", type=int, default=2028)
    args = ap.parse_args()
    t0 = time.time()
    hd.pruefe_modelle(rp.MODEL_NAME, args.richter)
    try:
        import requests
        tags = requests.get(rp.OLLAMA_URL.replace("/api/generate", "/api/tags"), timeout=20).json().get("models", [])
        namen = [m["name"] for m in tags]
    except Exception:
        namen = []

    def da(n):
        return any(v == n or v.split(":")[0] == n or v.startswith(n + ":") for v in namen)
    eval_modell = args.eval_modell if da(args.eval_modell) else args.richter
    if eval_modell != args.eval_modell:
        print(f"HINWEIS: {args.eval_modell} nicht installiert; Beurteilung mit {eval_modell}.")
    if eval_modell == rp.MODEL_NAME:
        raise SystemExit("ABBRUCH: Der Prüfer für die Beurteilung darf nicht das Generatormodell sein.")
    eval_cfg = (eval_modell, "C2")
    waechter_cfg = (rp.MODEL_NAME, "C2")
    wechsel_modell = eval_modell
    rp.RRF_K = 5
    Path("evaluationsdaten").mkdir(exist_ok=True)
    alle = oh.lade_szenarien(args.basis)
    print(f"{len(alle)} Hinweis-Situationen aus {args.basis}; Beurteilung {eval_cfg}, Wächter {waechter_cfg}, Budget {args.max_stunden} h")
    if args.limit:
        alle = alle[:args.limit]
    if Path(".git").is_dir() and not Path(f"evaluationsdaten/hinweis_stab_{args.label}_zustand.json").exists():
        subprocess.run(["git", "add", "-A"], check=False)
        subprocess.run(["git", "commit", "-q", "-m", "Stand vor Stabilitätstest der Hinweise"], check=False)
    pro_sz = None
    if not args.ohne_rauchtest and not args.limit:
        auswahl = alle[::max(1, len(alle) // 3)][:3]
        hd.stunde(t0, f"Rauchtest mit {len(auswahl)} Situationen (Teil A klein, je eine Runde T0 und T03, Label {args.label}-RAUCH)")
        a_alt = args.limit
        args.limit = 3
        try:
            _, z = lauf(args, args.label + "-RAUCH", auswahl, True, t0, eval_cfg, waechter_cfg, wechsel_modell)
            pro_sz = z.get("pro_situation_s")
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"ABBRUCH im Rauchtest: {type(e).__name__}: {e}\nNichts weiter gelaufen. Meldung weitergeben.")
        args.limit = a_alt
        if pro_sz:
            runde_min = pro_sz * len(alle) / 60
            hd.stunde(t0, f"Rauchtest bestanden. Geschätzt {runde_min:.0f} min je Runde (grob); im Budget von {args.max_stunden} h "
                      f"ca. {int(max(0, args.max_stunden * 60 - 60) // max(runde_min, 1))} Runden nach Teil A")
    label = args.label + ("-TEST" if args.limit else "")
    dateien, _ = lauf(args, label, alle, bool(args.limit), t0, eval_cfg, waechter_cfg, wechsel_modell)
    if not args.limit:
        doku_und_git(label, dateien)
    hd.stunde(t0, "Fertig")


if __name__ == "__main__":
    main()
