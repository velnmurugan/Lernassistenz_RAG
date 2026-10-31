#!/usr/bin/env python3
"""
diagnose_hinweis_erster.py  –  Warum stimmen nachgebaute erste Hinweise nicht mit den gespeicherten überein?
-----------------------------------------------------------------------------------------------------------
Anlass (HS-V1, 31 Okt 2026): Bei T=0/Seed 42 sind Hinweise innerhalb einer Sitzung deterministisch (8/8), aber 0 von 8 (A1) nachgebauten
ersten Hinweisen gleicht dem im Dialogtest (HD-V2) gespeicherten. Ein Folgehinweis (Versuch 3) wurde dagegen exakt reproduziert.
Dieses Skript trennt die möglichen Ursachen, ohne die Pipeline zu ändern (V11B bleibt eingefroren):

  Teil 1  Echte Pipeline (beantworte_frage) auf N Fragen aus HD-V2. Ein Fänger an _hinweis_separat hält fest, was die Pipeline dem
          Hinweis-Aufruf WIRKLICH übergibt (Lösung zum Hinweiszeitpunkt, Kontext, fertiger Prompt). Verglichen wird mit
          (a) dem gespeicherten hinweis0, (b) der gespeicherten Lösung und dem gespeicherten Kontext, (c) dem Prompt, den das Replay
          (optimiere_hinweise.prompt_basis) aus den gespeicherten Feldern baut, (d) einer direkten Neuerzeugung aus dem gefangenen Prompt.
          Auswertung je Frage (Ursachen-Entscheidung):
            Kontext weicht ab        -> Retrieval/Formelsuche liefert heute andere Chunks als im Dialogtest (oder Reihenfolge)
            Lösung weicht ab         -> Lösung zum Hinweiszeitpunkt != gespeicherte Lösung (Rechenprüfung, Nachbearbeitung)
            Prompt gleich, Hinweis verschieden -> Umgebung/Software/Ollama-Zustand (nicht Eingabe)
            Pipeline-Hinweis != direkte Neuerzeugung -> Pfad innerhalb der Pipeline (Optionen, Zustand) unterscheidet sich
  Teil 1b Die ersten 2 Fragen werden ein zweites Mal durch die Pipeline geschickt (Selbstkonsistenz der echten Pipeline).
  Teil 2  M Folgehinweise (Versuch 2/3) werden aus dem gespeicherten Verlauf nachgebaut und mit den gespeicherten verglichen.

Start (aus ~/RAG, Umgebung pilot_rag aktiv, Ollama läuft, Vordergrund):
    python skripte/evaluation/diagnose_hinweis_erster.py 2>&1 | tee evaluationsdaten/hinweis_diag_HX-V1_log.txt
Laufzeit grob 20-35 min (Pipeline-Aufruf je Frage 1-3 min). Optionen: --n 8 --m 12 --ohne-wdh
Ergebnisse: evaluationsdaten/hinweis_diag_HX-V1_ergebnis.txt, _fragen.csv, _folge.csv, _prompts.json
"""
import sys as _sys
import pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))
import argparse  # noqa: E402
import csv  # noqa: E402
import difflib  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import optimiere_hinweise as oh  # noqa: E402
import teste_hinweis_dialog as hd  # noqa: E402
import teste_hinweis_stabilitaet as hs  # noqa: E402

rp = hd.rag_pipeline
LABEL = "HX-V1"


def md(t):
    return hashlib.md5((t or "").encode("utf-8")).hexdigest()[:8]


def erste_abweichung(a, b, breite=70):
    """Position und Umgebung der ersten Abweichung zweier Texte."""
    a, b = a or "", b or ""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i, a[max(0, i - breite // 2): i + breite // 2], b[max(0, i - breite // 2): i + breite // 2]
    if len(a) != len(b):
        i = min(len(a), len(b))
        return i, a[max(0, i - breite // 2): i + breite // 2], b[max(0, i - breite // 2): i + breite // 2]
    return -1, "", ""


def waehle_fragen(z, n):
    q = [s for s in z["q"].values() if s.get("ok") and s.get("hinweis0")]
    q.sort(key=lambda s: (s["id"][0], int(re.sub(r"\D", "", s["id"]) or 0)))
    if len(q) <= n:
        return q
    rechen = [s for s in q if re.search(r"\d", s["frage"])]
    wahl = []
    for s in rechen[:: max(1, len(rechen) // max(1, n // 3))][: max(1, n // 3)]:
        wahl.append(s)
    rest = [s for s in q if s not in wahl]
    schritt = max(1, len(rest) // (n - len(wahl)))
    wahl += rest[::schritt][: n - len(wahl)]
    return wahl[:n]


def pipeline_lauf(s, chunks, opt):
    """Echte Pipeline; fängt die Eingaben des Hinweis-Aufrufs ab."""
    fang = {}
    orig = rp._hinweis_separat

    def wrapper(frage, top_chunks, stufen):
        fang["loesung"] = stufen.get("loesung", "")
        fang["kontext"] = rp._kontext_text(top_chunks)
        fang["prompt"] = rp.baue_hinweis_prompt(frage, top_chunks, stufen.get("loesung", ""))
        fang["geparst"] = bool(stufen.get("vollstaendig_geparst"))
        z = orig(frage, top_chunks, stufen)
        fang["quelle"] = z.get("hinweis_quelle", "")
        fang["hinweis_roh"] = z.get("hinweis", "")
        return z

    rp._hinweis_separat = wrapper
    try:
        erg = rp.beantworte_frage(s["frage"], chunks, top_k=4, methode=hd.RETRIEVAL)
    finally:
        rp._hinweis_separat = orig
    return erg, fang


def teil1(args, z, chunks, opt, out):
    fragen = waehle_fragen(z, args.n)
    print(f"Teil 1: {len(fragen)} Fragen: {[s['id'] for s in fragen]}", flush=True)
    zeilen, prompts = [], {}
    live1 = {}
    for i, s in enumerate(fragen, 1):
        t0 = time.time()
        erg, fang = pipeline_lauf(s, chunks, opt)
        live1[s["id"]] = erg.get("hinweis", "")
        replay_prompt = oh.prompt_basis({"s": s, "n": 1})
        live_prompt = fang.get("prompt", "")
        # direkte Neuerzeugung aus dem gefangenen Prompt (mit der Lösung zum Hinweiszeitpunkt)
        direkt = ""
        if live_prompt:
            direkt = hs.erzeuge2(live_prompt, {"frage": s["frage"], "loesung": fang["loesung"], "status": erg.get("status", "")}, opt)[0].strip()
        # Replay-Hinweis aus den gespeicherten Feldern
        replay = hs.erzeuge2(replay_prompt, s, opt)[0].strip()
        ctx_gl = fang.get("kontext") == s.get("kontext")
        los_hz_gl = fang.get("loesung") == s.get("loesung")
        los_end_gl = erg.get("loesung") == s.get("loesung")
        prompt_gl = live_prompt == replay_prompt
        live = (erg.get("hinweis") or "").strip()
        gesp = s["hinweis0"].strip()
        if not fang:
            ursache = f"kein separater Hinweis (Quelle: {erg.get('hinweis_quelle', '?')})"
        elif live == gesp:
            ursache = "Pipeline heute = gespeichert"
        elif not ctx_gl:
            ursache = "Kontext weicht ab (Retrieval/Formelsuche liefert andere Chunks)"
        elif not los_hz_gl:
            ursache = "Lösung zum Hinweiszeitpunkt weicht von gespeicherter ab"
        elif prompt_gl and live != gesp and direkt == live:
            ursache = "Prompt gleich, Hinweis verschieden: Umgebung/Software/Zustand"
        elif prompt_gl and direkt != live:
            ursache = "Prompt gleich, aber Pipeline-Pfad != direkter Aufruf (Optionen/Zustand)"
        else:
            ursache = "Prompt weicht ab (Text), Ursache siehe Diff"
        pos, ta, tb = erste_abweichung(live_prompt, replay_prompt)
        zeilen.append({
            "id": s["id"], "quelle_live": fang.get("quelle", erg.get("hinweis_quelle", "")),
            "live=gespeichert": live == gesp, "replay=gespeichert": replay == gesp, "live=replay": live == replay,
            "direkt=live": direkt == live, "kontext_gleich": ctx_gl, "loesung_hinweiszeit_gleich": los_hz_gl,
            "loesung_ende_gleich": los_end_gl, "prompt_gleich": prompt_gl, "prompt_abw_pos": pos,
            "ursache": ursache, "sek": round(time.time() - t0),
            "h_gesp": md(gesp), "h_live": md(live), "h_replay": md(replay), "h_direkt": md(direkt)})
        prompts[s["id"]] = {"live_prompt": live_prompt, "replay_prompt": replay_prompt,
                            "gespeichert": gesp, "live": live, "replay": replay, "direkt": direkt,
                            "loesung_live": fang.get("loesung", ""), "loesung_gesp": s.get("loesung", ""),
                            "kontext_live": fang.get("kontext", ""), "kontext_gesp": s.get("kontext", "")}
        print(f"  [{i}/{len(fragen)}] {s['id']:<5} live=gesp {live == gesp!s:<5} replay=gesp {replay == gesp!s:<5} "
              f"live=replay {live == replay!s:<5} direkt=live {direkt == live!s:<5} kontext {ctx_gl!s:<5} "
              f"lösung(hz) {los_hz_gl!s:<5} prompt {prompt_gl!s:<5} -> {ursache}  ({time.time() - t0:.0f}s)", flush=True)
        if not prompt_gl and pos >= 0:
            print(f"        Prompt-Abweichung ab Zeichen {pos}:\n          live  : …{ta}…\n          replay: …{tb}…", flush=True)
    # Teil 1b: Selbstkonsistenz
    if not args.ohne_wdh:
        print("Teil 1b: erste Fragen ein zweites Mal durch die Pipeline", flush=True)
        for s in fragen[:2]:
            erg, _ = pipeline_lauf(s, chunks, opt)
            gl = (erg.get("hinweis") or "").strip() == live1[s["id"]].strip()
            print(f"  {s['id']}: zweiter Pipeline-Lauf = erster Pipeline-Lauf: {gl}", flush=True)
            out.setdefault("wdh", []).append((s["id"], gl))
    return zeilen, prompts


def teil2(args, opt):
    sz = [x for x in oh.lade_szenarien("HD-V2") if x["n"] > 1]
    if not sz:
        return []
    schritt = max(1, len(sz) // args.m)
    wahl = sz[::schritt][: args.m]
    print(f"Teil 2: {len(wahl)} Folgehinweise nachbauen", flush=True)
    res = []
    for i, x in enumerate(wahl, 1):
        neu = hs.erzeuge2(oh.prompt_basis(x), x["s"], opt)[0].strip()
        gesp = x["hinweis_b"].strip()
        res.append({"key": x["key"], "n": x["n"], "gleich": neu == gesp, "h_gesp": md(gesp), "h_neu": md(neu)})
        print(f"  [{i}/{len(wahl)}] {x['key']:<7} Versuch {x['n']}  gleich dem gespeicherten: {neu == gesp}", flush=True)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8, help="Fragen für Teil 1")
    ap.add_argument("--m", type=int, default=12, help="Folgehinweise für Teil 2")
    ap.add_argument("--ohne-wdh", action="store_true", help="Teil 1b überspringen")
    args = ap.parse_args()
    t0 = time.time()
    if not Path(hd.KB).exists():
        raise SystemExit(f"Wissensbasis nicht gefunden: {hd.KB} (aus ~/RAG starten)")
    pfad = Path("evaluationsdaten/hinweis_dialog_HD-V2_zustand.json")
    if not pfad.exists():
        raise SystemExit(f"FEHLT: {pfad} (aus ~/RAG starten)")
    z = json.loads(pfad.read_text(encoding="utf-8"))
    rp.RRF_K = 5
    opt = dict(rp.GENERIERUNGS_OPTIONEN)
    chunks = rp.lade_wissensbasis(hd.KB)
    pipe_datei = Path(rp.__file__)
    umg = hs.ollama_info([rp.MODEL_NAME])
    kopf = (f"Diagnose erster Hinweis {LABEL}  {time.strftime('%d.%m.%Y %H:%M')}\n"
            f"Pipeline-Datei: {pipe_datei} (md5 {hashlib.md5(pipe_datei.read_bytes()).hexdigest()[:10]}, "
            f"{pipe_datei.stat().st_size} Byte, geändert {time.strftime('%d.%m.%Y %H:%M', time.localtime(pipe_datei.stat().st_mtime))})\n"
            f"Umgebung: {json.dumps(umg, ensure_ascii=False)}\n"
            f"Konfiguration: SCAFFOLDING_VERSION={getattr(rp, 'SCAFFOLDING_VERSION', '?')}, RRF_K={rp.RRF_K}, "
            f"KONTEXT_TOKENS={getattr(rp, 'KONTEXT_TOKENS', '?')}, Optionen={opt}, kb_hash={rp.berechne_kb_hash(hd.KB)}")
    print(kopf, flush=True)
    out = {}
    zeilen, prompts = teil1(args, z, chunks, opt, out)
    folge = teil2(args, opt)

    from collections import Counter
    ur = Counter(r["ursache"] for r in zeilen)
    n = len(zeilen)
    s_lines = [kopf, "", f"=== Teil 1: echte Pipeline auf {n} Fragen (erster Hinweis, T=0 Seed 42)",
               f"  Pipeline heute = gespeichert hinweis0 : {sum(r['live=gespeichert'] for r in zeilen)}/{n}",
               f"  Replay (prompt_basis) = gespeichert    : {sum(r['replay=gespeichert'] for r in zeilen)}/{n}",
               f"  Pipeline heute = Replay                : {sum(r['live=replay'] for r in zeilen)}/{n}",
               f"  Pipeline heute = direkte Neuerzeugung  : {sum(r['direkt=live'] for r in zeilen)}/{n}",
               f"  Kontext gleich dem gespeicherten       : {sum(r['kontext_gleich'] for r in zeilen)}/{n}",
               f"  Lösung zum Hinweiszeitpunkt gleich     : {sum(r['loesung_hinweiszeit_gleich'] for r in zeilen)}/{n}",
               f"  Lösung am Ende gleich                  : {sum(r['loesung_ende_gleich'] for r in zeilen)}/{n}",
               f"  Prompt (Pipeline) = Prompt (Replay)    : {sum(r['prompt_gleich'] for r in zeilen)}/{n}",
               "  Ursachen:"]
    s_lines += [f"    {v}x {k}" for k, v in ur.most_common()]
    if out.get("wdh"):
        s_lines.append(f"  Teil 1b (Pipeline zweimal): gleich {sum(g for _, g in out['wdh'])}/{len(out['wdh'])}")
    if folge:
        s_lines += ["", f"=== Teil 2: {len(folge)} Folgehinweise nachgebaut",
                    f"  gleich dem gespeicherten: {sum(r['gleich'] for r in folge)}/{len(folge)}"]
    s_lines += ["", "Lesehilfe: Ist der Prompt gleich und der Hinweis trotzdem verschieden, liegt es an Umgebung/Software (Ollama-Version,",
                "Modell-Digest, Pipeline-Stand seit HD-V2), nicht an der Eingabe. Weicht Kontext oder Lösung ab, ist das Replay kein",
                "getreuer Nachbau; dann bleibt für Vergleiche nur die Pipeline selbst (oder gespeicherte Hinweise) maßgeblich.",
                f"Gesamtdauer: {(time.time() - t0) / 60:.0f} min"]
    Path("evaluationsdaten").mkdir(exist_ok=True)
    base = f"evaluationsdaten/hinweis_diag_{LABEL}"
    Path(base + "_ergebnis.txt").write_text("\n".join(s_lines), encoding="utf-8")
    if zeilen:
        with open(base + "_fragen.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(zeilen[0].keys()))
            w.writeheader()
            w.writerows(zeilen)
    if folge:
        with open(base + "_folge.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(folge[0].keys()))
            w.writeheader()
            w.writerows(folge)
    Path(base + "_prompts.json").write_text(json.dumps(prompts, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n" + "\n".join(s_lines), flush=True)
    print(f"\nDateien: {base}_ergebnis.txt, _fragen.csv, _folge.csv, _prompts.json", flush=True)


if __name__ == "__main__":
    main()
