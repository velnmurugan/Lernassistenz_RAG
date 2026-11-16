"""
gpt_rag300.py  (Studie 1, Bedingung D: Cloud-Modell MIT RAG)
Gleiche Suche wie V20 (rp.retrieval, hybrid_kg_rr, Wissensbasis v7r, Gate 0,35, die ersten 4 Abschnitte) und gleicher
Antwortprompt wie V20 (G-v6); EIN Aufruf des OpenAI-Modells statt qwen3.5:9b. Ohne Formelsuche, Rechenprüfung und
Hinweisprüfung (diese sind auf qwen abgestimmt) – verglichen wird also Suche + Prompt, nicht das ganze V20-System.
Der bewertete Text ist wie in V20 das Feld LÖSUNG (bei NICHT_IM_MATERIAL / Gate: der Ablehnungstext).

Datenschutz/Urheberrecht: anders als Bedingung C (nur Fragen) gehen hier Buchabschnitte an die API.
Vor einem Lauf die Freigabe für das Material klären. Keine Daten von Lernenden.

Schlüssel nur als Umgebungsvariable:   export OPENAI_API_KEY='sk-...'
Start (Ollama wird NICHT gebraucht; die Suche braucht Embedding + Reranker lokal):
  python skripte/evaluation/gpt_rag300.py --nur-prompt --limit 5   # ohne Schlüssel: zeigt Prompts + Größe, schätzt Kosten
  python skripte/evaluation/gpt_rag300.py --limit 10               # Probelauf
  python skripte/evaluation/gpt_rag300.py --bis 100                # Q1–Q100
  python skripte/evaluation/gpt_rag300.py                          # alle (setzt nach Abbruch fort)
Ausgabe: evaluationsdaten/gptrag300_<LABEL>.csv (+ _konfig.txt)
"""
import os

os.environ.setdefault("LERNASSISTENT_G", "G-v6")  # vor dem Import von rag_pipeline (liest die Version beim Import)
os.environ.setdefault("LERNASSISTENT_RP", "RP-v13")
os.environ.setdefault("LERNASSISTENT_FS", "FS-v3")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import argparse
import csv
import datetime as dt
import sys
import time
from pathlib import Path

import requests

try:  # Pfad zu lernassistent/ setzen
    import pathlib as _pl
    _sys_root = next((p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()), None)
    if _sys_root:
        sys.path.insert(0, str(_sys_root / "lernassistent"))
        import pfadsetup  # noqa: F401
except Exception:
    pass

ANBIETER = {  # OpenAI-kompatible chat/completions-Endpunkte
    "openai":  ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY"),
}
API = ANBIETER["openai"][0]
PREISE = {"gpt-6.1-sol": (2.0, 10.0), "gpt-6-sol": (2.0, 10.0), "gpt-6-luna": (0.10, 0.50)}  # USD/1 Mio. Tokens, nur Schätzung
FELDER = ["id", "buch", "typ", "frage", "status_gpt_rag", "antwort_gpt_rag", "hinweis_gpt_rag", "quellen", "bester_score",
          "prompt_zeichen", "sek", "modell", "tokens_ein", "tokens_aus", "tokens_denken", "zeitpunkt", "fehler", "roh"]
VERWEIGERUNG = ("Dazu habe ich in den Lernmaterialien keine ausreichend passende Quelle gefunden und möchte deshalb keine "
                "geratene Antwort geben. Bitte wende dich an deine Lehrkraft oder formuliere die Frage genauer.")


def inhalt(j):
    """Antworttext; Reasoning-Modelle (z. B. Mistral) liefern teils eine Liste aus Denk- und Textteilen."""
    c = j["choices"][0]["message"]["content"]
    if isinstance(c, list):
        c = "".join(t.get("text", "") for t in c if isinstance(t, dict) and t.get("type") == "text")
    return (c or "").strip()


def frage_gpt(modell, prompt, schluessel, versuche=4):
    fehler = ""
    for i in range(1, versuche + 1):
        try:
            r = requests.post(API, timeout=300, headers={"Authorization": f"Bearer {schluessel}"},
                              json={"model": modell, "messages": [{"role": "user", "content": prompt}]})
            if r.status_code == 200:
                return r.json(), ""
            fehler = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 401, 403, 404):
                return None, fehler
        except requests.RequestException as e:
            fehler = f"{type(e).__name__}: {str(e)[:200]}"
        print(f"   WARNUNG Versuch {i}/{versuche}: {fehler}", flush=True)
        time.sleep(10 * i)
    return None, fehler


def baue(rp, frage, chunks, methode):
    """Suche + Gate + Prompt wie V20. Rückgabe: (prompt | None, quellen, bester_score)."""
    top, alle = rp.retrieval(frage, chunks, top_k=4, methode=methode)
    bester = max((c["score"] for c in alle), default=0.0)
    if bester < rp.RELEVANZ_SCHWELLE:
        return None, [], bester
    try:
        top_prompt = rp.ohne_buchergebnisse(frage, top)  # RP-v10-Regel; bei RP-v13 unverändert
    except Exception:
        top_prompt = top
    return rp.baue_scaffolding_prompt(frage, top_prompt), [c["id"] for c in top], bester


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="F300-GPT61SOL-RAG")
    ap.add_argument("--modell", default="gpt-6.1-sol")
    ap.add_argument("--anbieter", default="openai", choices=list(ANBIETER), help="openai | mistral (gleicher Prompt, gleicher Ablauf)")
    ap.add_argument("--preis-ein", type=float, help="USD je 1 Mio. Eingabe-Tokens (für die Kostenschätzung)")
    ap.add_argument("--preis-aus", type=float, help="USD je 1 Mio. Ausgabe-Tokens")
    ap.add_argument("--fragen", default="daten/testfragen/fragen300.csv")
    ap.add_argument("--kb", default="daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
    ap.add_argument("--retrieval", default="hybrid_kg_rr")
    ap.add_argument("--limit", type=int, help="nur so viele (noch offene) Fragen beantworten")
    ap.add_argument("--bis", type=int, help="nur Q1 bis Q<bis>")
    ap.add_argument("--nur-prompt", action="store_true", help="kein API-Aufruf: Prompts erzeugen, Größe zählen, Kosten schätzen")
    a = ap.parse_args()
    global API
    API, _env = ANBIETER[a.anbieter]
    if a.preis_ein is not None and a.preis_aus is not None:
        PREISE[a.modell] = (a.preis_ein, a.preis_aus)
    schluessel = os.environ.get(_env, "").strip()
    if not schluessel and not a.nur_prompt:
        sys.exit(f"FEHLER: export {_env}='...' fehlt")
    import rag_pipeline as rp
    if not rp.ist_g_version() or rp.SCAFFOLDING_VERSION != "G-v6":
        sys.exit(f"FEHLER: Antwortprompt ist {rp.SCAFFOLDING_VERSION}, erwartet G-v6 (LERNASSISTENT_G=G-v6 setzen)")
    with open(a.fragen, encoding="utf-8") as f:
        fragen = list(csv.DictReader(f))
    if a.bis:
        fragen = [q for q in fragen if int(q["id"].lstrip("Qq")) <= a.bis]
    chunks = rp.lade_wissensbasis(a.kb)
    out = Path(f"evaluationsdaten/gptrag300_{a.label}.csv")
    out.parent.mkdir(exist_ok=True)
    alt = {}
    if out.exists() and not a.nur_prompt:
        with open(out, encoding="utf-8") as f:
            alt = {z["id"]: z for z in csv.DictReader(f)}
    konfig = (f"Arm D mit RAG | Modell {a.modell} ({a.anbieter} API, chat/completions, Standardparameter, 1 Aufruf je Frage) | "
              f"Prompt G={rp.SCAFFOLDING_VERSION} | Retrieval {a.retrieval} Gate {rp.RELEVANZ_SCHWELLE} | KB {a.kb} "
              f"({rp.berechne_kb_hash(a.kb)}) | ohne Formelsuche/Rechenprüfung/Hinweisprüfung | Fragen {a.fragen} | "
              f"Start {dt.datetime.now().isoformat(timespec='seconds')}")
    if not a.nur_prompt:
        with open(out.with_name(out.stem + "_konfig.txt"), "a", encoding="utf-8") as f:
            f.write(konfig + "\n")
    print(konfig, flush=True)

    zeilen, neu, zeichen_summe, gezaehlt = [], 0, 0, 0
    for q in fragen:
        z = alt.get(q["id"]) or {"id": q["id"], "buch": q["buch"], "typ": q["typ"], "frage": q["frage"]}
        fertig = z.get("antwort_gpt_rag") and not z.get("fehler")
        if fertig or (a.limit is not None and neu >= a.limit):
            zeilen.append(z)
            continue
        t0 = time.time()
        prompt, quellen, bester = baue(rp, q["frage"], chunks, a.retrieval)
        z.update(quellen="; ".join(quellen), bester_score=round(bester, 4), prompt_zeichen=len(prompt or ""))
        if a.nur_prompt:
            print(f"[{q['id']:>4}] Quellen {z['quellen'] or '– (Gate)'} | Prompt {len(prompt or '')} Zeichen")
            if prompt and neu == 0:
                print("-" * 70 + "\n" + prompt + "\n" + "-" * 70)
            if prompt:
                zeichen_summe += len(prompt)
                gezaehlt += 1
            neu += 1
            zeilen.append(z)
            continue
        if prompt is None:  # Gate wie V20: keine API-Anfrage, Ablehnungstext
            z.update(status_gpt_rag="GATE", antwort_gpt_rag=VERWEIGERUNG, hinweis_gpt_rag="", sek=round(time.time() - t0, 1),
                     modell="(kein Aufruf)", fehler="", zeitpunkt=dt.datetime.now().isoformat(timespec="seconds"))
            print(f"[{q['id']:>4}] GATE (bester Wert {bester:.2f}) – keine Anfrage an OpenAI", flush=True)
            neu += 1
            zeilen.append(z)
            continue
        j, fehler = frage_gpt(a.modell, prompt, schluessel)
        z.update(sek=round(time.time() - t0, 1), zeitpunkt=dt.datetime.now().isoformat(timespec="seconds"), fehler=fehler)
        if j:
            roh = inhalt(j)
            st = rp.parse_g_v1(roh)
            u = j.get("usage", {})
            z.update(status_gpt_rag=st["status"], antwort_gpt_rag=st["loesung"], hinweis_gpt_rag=st["hinweis"], roh=roh,
                     modell=j.get("model", a.modell), tokens_ein=u.get("prompt_tokens", ""), tokens_aus=u.get("completion_tokens", ""),
                     tokens_denken=(u.get("completion_tokens_details") or {}).get("reasoning_tokens", ""))
        neu += 1
        print(f"[{q['id']:>4}] {z['sek']:>5} s | {z.get('status_gpt_rag', ''):<17} | {(z.get('antwort_gpt_rag') or fehler)[:70].replace(chr(10), ' ')}", flush=True)
        zeilen.append(z)
        if fehler and fehler.startswith(("HTTP 401", "HTTP 403", "HTTP 404", "HTTP 400")):
            print("Abbruch: Schlüssel oder Modellname prüfen.", flush=True)
            break
        with open(out, "w", encoding="utf-8", newline="") as f:  # nach jeder Frage sichern
            w = csv.DictWriter(f, fieldnames=FELDER, extrasaction="ignore")
            w.writeheader()
            w.writerows(zeilen + [alt[i] for i in alt if i not in {x["id"] for x in zeilen}])

    if a.nur_prompt:
        if gezaehlt:
            mittel = zeichen_summe / gezaehlt
            tok = mittel / 3.5  # grobe Schätzung: ca. 3,5 Zeichen je Token (Deutsch, Formeln)
            p_ein, p_aus = PREISE.get(a.modell, (2.0, 10.0))
            print(f"\nØ Prompt {mittel:.0f} Zeichen ≈ {tok:.0f} Token. Für 300 Fragen ca. ${300 * (tok * p_ein + 600 * p_aus) / 1e6:.2f} "
                  f"(Annahme: 600 Ausgabe-/Denk-Token je Frage; nur Schätzung, Preise {p_ein}/{p_aus} USD je 1 Mio.)")
        return
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, extrasaction="ignore")
        w.writeheader()
        w.writerows(zeilen + [alt[i] for i in alt if i not in {x["id"] for x in zeilen}])
    fertig = [z for z in zeilen if z.get("antwort_gpt_rag") and not z.get("fehler")]
    ein = sum(int(z.get("tokens_ein") or 0) for z in fertig)
    aus = sum(int(z.get("tokens_aus") or 0) for z in fertig)
    print(f"\nFertig: {len(fertig)}/{len(fragen)} Fragen -> {out}")
    if fertig and a.modell in PREISE and ein:
        p_ein, p_aus = PREISE[a.modell]
        k = ein / 1e6 * p_ein + aus / 1e6 * p_aus
        print(f"Tokens: ein {ein}, aus {aus} (davon Denken {sum(int(z.get('tokens_denken') or 0) for z in fertig)})")
        print(f"Kosten bisher ca. ${k:.4f}; hochgerechnet auf {len(fragen)} Fragen ca. ${k / len(fertig) * len(fragen):.2f}")


if __name__ == "__main__":
    main()
