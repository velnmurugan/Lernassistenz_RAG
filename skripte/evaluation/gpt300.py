"""
gpt300.py  (Studie 1, Bedingung C: Cloud-Modell OHNE RAG)
Beantwortet die Fragen aus fragen300.csv mit einem OpenAI-Modell über die API, mit genau demselben Prompt O-v1
wie die Bedingung "ohne RAG" mit qwen3.5:9b (eval300_antworten.prompt_ohne_rag). Es gehen NUR die Fragen an die API,
keine Buchinhalte, keine Daten von Lernenden.

Schlüssel nur als Umgebungsvariable (nie in Dateien/Git):   export OPENAI_API_KEY='sk-...'
Start (beliebige Umgebung mit python + requests):
  python skripte/evaluation/gpt300.py --limit 10          # Probelauf: 10 Fragen + Kostenschätzung für alle 300
  python skripte/evaluation/gpt300.py --bis 100           # Q1–Q100
  python skripte/evaluation/gpt300.py                     # alle (setzt nach Abbruch fort, fertige werden übersprungen)
Ausgabe: evaluationsdaten/gpt300_<LABEL>.csv (+ _konfig.txt)
"""
import argparse
import csv
import datetime as dt
import os
import sys
import time
from pathlib import Path

import requests

OHNE_RAG_PROMPT_VERSION = "O-v1"
ANBIETER = {  # OpenAI-kompatible chat/completions-Endpunkte
    "openai":  ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY"),
    "mistral": ("https://api.mistral.ai/v1/chat/completions", "MISTRAL_API_KEY"),
}
API = ANBIETER["openai"][0]
PREISE = {  # USD je 1 Mio. Tokens (Eingabe, Ausgabe), nur für die Kostenschätzung
    "gpt-6.1-sol": (2.0, 10.0), "gpt-6-sol": (2.0, 10.0), "gpt-6-luna": (0.10, 0.50),
}
FELDER = ["id", "buch", "typ", "frage", "antwort_gpt", "sek_gpt", "modell_gpt", "tokens_ein", "tokens_aus",
          "tokens_denken", "zeitpunkt", "fehler"]


def prompt_ohne_rag(frage):
    # wortgleich mit O-v1 in eval300_antworten.py (nicht ändern)
    return (
        "Du bist Fachlehrkraft für Elektrotechnik in der beruflichen Ausbildung. "
        "Beantworte die Frage einer oder eines Auszubildenden fachlich korrekt und knapp "
        "(höchstens 6 Sätze). Bei Rechenaufgaben: Formel, eingesetzte Werte, Ergebnis mit Einheit. "
        "Wenn du etwas nicht sicher weißt, sage das ausdrücklich, statt zu raten.\n\n"
        f"Frage: {frage}\n\nAntwort:"
    )


def pruefe_prompt_gleich():
    """Sicherheitsnetz: Prompt muss wortgleich mit dem qwen-Arm sein (falls eval300_antworten.py vorhanden)."""
    q = Path(__file__).with_name("eval300_antworten.py")
    if not q.exists():
        return "nicht geprüft (eval300_antworten.py fehlt)"
    text = q.read_text(encoding="utf-8")
    for teil in ["Du bist Fachlehrkraft für Elektrotechnik in der beruflichen Ausbildung. ",
                 "(höchstens 6 Sätze). Bei Rechenaufgaben: Formel, eingesetzte Werte, Ergebnis mit Einheit. ",
                 "Wenn du etwas nicht sicher weißt, sage das ausdrücklich, statt zu raten.\\n\\n"]:
        if teil not in text:
            sys.exit("FEHLER: Prompt weicht von eval300_antworten.py ab – abgebrochen")
    return "wortgleich mit eval300_antworten.py"


def inhalt(j):
    """Antworttext; Reasoning-Modelle (z. B. Mistral) liefern teils eine Liste aus Denk- und Textteilen."""
    c = j["choices"][0]["message"]["content"]
    if isinstance(c, list):
        c = "".join(t.get("text", "") for t in c if isinstance(t, dict) and t.get("type") == "text")
    return (c or "").strip()


def frage_gpt(modell, prompt, schluessel, versuche=4):
    for i in range(1, versuche + 1):
        try:
            r = requests.post(API, timeout=180, headers={"Authorization": f"Bearer {schluessel}"},
                              json={"model": modell, "messages": [{"role": "user", "content": prompt}]})
            if r.status_code == 200:
                return r.json(), ""
            fehler = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (400, 401, 403, 404):
                return None, fehler  # Schlüssel/Modellname falsch: Wiederholen hilft nicht
        except requests.RequestException as e:
            fehler = f"{type(e).__name__}: {str(e)[:200]}"
        print(f"   WARNUNG Versuch {i}/{versuche}: {fehler}", flush=True)
        time.sleep(10 * i)
    return None, fehler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="F300-GPT61SOL")
    ap.add_argument("--modell", default="gpt-6.1-sol")
    ap.add_argument("--anbieter", default="openai", choices=list(ANBIETER), help="openai | mistral (gleicher Prompt, gleicher Ablauf)")
    ap.add_argument("--preis-ein", type=float, help="USD je 1 Mio. Eingabe-Tokens (für die Kostenschätzung)")
    ap.add_argument("--preis-aus", type=float, help="USD je 1 Mio. Ausgabe-Tokens")
    ap.add_argument("--fragen", default="daten/testfragen/fragen300.csv")
    ap.add_argument("--limit", type=int, help="nur so viele (noch offene) Fragen beantworten")
    ap.add_argument("--bis", type=int, help="nur Q1 bis Q<bis>")
    a = ap.parse_args()
    global API
    API, _env = ANBIETER[a.anbieter]
    if a.preis_ein is not None and a.preis_aus is not None:
        PREISE[a.modell] = (a.preis_ein, a.preis_aus)
    schluessel = os.environ.get(_env, "").strip()
    if not schluessel:
        sys.exit(f"FEHLER: export {_env}='...' fehlt")
    with open(a.fragen, encoding="utf-8") as f:
        fragen = list(csv.DictReader(f))
    if a.bis:
        fragen = [q for q in fragen if int(q["id"].lstrip("Qq")) <= a.bis]
    out = Path(f"evaluationsdaten/gpt300_{a.label}.csv")
    out.parent.mkdir(exist_ok=True)
    alt = {}
    if out.exists():
        with open(out, encoding="utf-8") as f:
            alt = {z["id"]: z for z in csv.DictReader(f)}
    pruefung = pruefe_prompt_gleich()
    konfig = (f"Arm C ohne RAG | Modell {a.modell} ({a.anbieter} API, chat/completions, Standardparameter) | "
              f"Prompt {OHNE_RAG_PROMPT_VERSION} ({pruefung}) | Fragen {a.fragen} | Start {dt.datetime.now().isoformat(timespec='seconds')}")
    with open(out.with_name(out.stem + "_konfig.txt"), "a", encoding="utf-8") as f:
        f.write(konfig + "\n")
    print(konfig, flush=True)

    zeilen, neu = [], 0
    for q in fragen:
        z = alt.get(q["id"]) or {"id": q["id"], "buch": q["buch"], "typ": q["typ"], "frage": q["frage"]}
        if not (z.get("antwort_gpt") and not z.get("fehler")) and (a.limit is None or neu < a.limit):
            t0 = time.time()
            j, fehler = frage_gpt(a.modell, prompt_ohne_rag(q["frage"]), schluessel)
            z.update(sek_gpt=round(time.time() - t0, 1), zeitpunkt=dt.datetime.now().isoformat(timespec="seconds"),
                     fehler=fehler)
            if j:
                u = j.get("usage", {})
                z.update(antwort_gpt=inhalt(j), modell_gpt=j.get("model", a.modell),
                         tokens_ein=u.get("prompt_tokens", ""), tokens_aus=u.get("completion_tokens", ""),
                         tokens_denken=(u.get("completion_tokens_details") or {}).get("reasoning_tokens", ""))
            neu += 1
            print(f"[{q['id']:>4}] {z['sek_gpt']:>5} s | {str(z.get('tokens_aus', '')):>5} Tok | "
                  f"{(z.get('antwort_gpt') or fehler)[:70].replace(chr(10), ' ')}", flush=True)
            if fehler and fehler.startswith(("HTTP 401", "HTTP 403", "HTTP 404", "HTTP 400")):
                zeilen.append(z)
                print("Abbruch: Schlüssel oder Modellname prüfen.", flush=True)
                zeilen += [alt.get(r["id"]) or {"id": r["id"], "buch": r["buch"], "typ": r["typ"], "frage": r["frage"]}
                           for r in fragen[len(zeilen):]]
                break
        zeilen.append(z)
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, extrasaction="ignore")
        w.writeheader()
        w.writerows(zeilen)

    fertig = [z for z in zeilen if z.get("antwort_gpt") and not z.get("fehler")]
    ein = sum(int(z.get("tokens_ein") or 0) for z in fertig)
    aus = sum(int(z.get("tokens_aus") or 0) for z in fertig)
    print(f"\nFertig: {len(fertig)}/{len(fragen)} Fragen -> {out}")
    if fertig and a.modell in PREISE:
        p_ein, p_aus = PREISE[a.modell]
        kosten = ein / 1e6 * p_ein + aus / 1e6 * p_aus
        print(f"Tokens: ein {ein}, aus {aus} (davon Denken {sum(int(z.get('tokens_denken') or 0) for z in fertig)})")
        print(f"Kosten bisher ca. ${kosten:.4f}; hochgerechnet auf {len(fragen)} Fragen ca. ${kosten / len(fertig) * len(fragen):.2f}")


if __name__ == "__main__":
    main()
