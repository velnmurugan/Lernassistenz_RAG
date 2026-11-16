#!/usr/bin/env python3
"""
Blind LLM judge for the V20 hints (Studie 2, 269 book questions; rubric with 4 check points).

The judge sees question, reference answer, book passage, protected core, allowed details and the hint
(no system name, no other ratings). It returns per check point:
  p1 fachlich korrekt  ja | nein | –
  p2 Lösung bleibt offen  ja | nein
  p3 nächster Schritt  ja | teilweise | nein   (+ p3b  zu vage | zu viel Hilfe  when teilweise)
  p4 verständlich & nutzbar  ja | nein
plus a short reason. "Akzeptabel"/"Stark" are computed here (same rule as in the Excel).
Results: hint_judge_<provider>.jsonl (one line per question) -> safe to stop and resume.

  export GEMINI_API_KEY=...   /   export MISTRAL_API_KEY=...
  python -u hint_judge.py --provider gemini --limit 3            # test
  python -u hint_judge.py --provider gemini  | tee -a log_hint_gemini.txt
  python -u hint_judge.py --provider mistral --model mistral-large-4 | tee -a log_hint_mistral.txt
  python hint_judge.py --provider gemini --summary
"""
import argparse, json, os, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = {"gemini": "gemini-4-argon", "mistral": "mistral-large-4"}
SYSTEM = ("Du bist ein strenger, unabhängiger Prüfer für Lernhinweise in der beruflichen Bildung "
          "(Elektrotechnik, Maschinenbau). Du bewertest ausschließlich nach der Rubrik.")
ALLOWED = {"p1": {"ja", "nein", "–"}, "p2": {"ja", "nein"}, "p3": {"ja", "teilweise", "nein"},
           "p4": {"ja", "nein"}, "p3b": {"", "zu vage", "zu viel Hilfe"}}
SCHEMA = {"type": "object",
          "properties": {"begruendung": {"type": "string"},
                         "p1": {"type": "string", "enum": ["ja", "nein", "–"]},
                         "p2": {"type": "string", "enum": ["ja", "nein"]},
                         "p3": {"type": "string", "enum": ["ja", "teilweise", "nein"]},
                         "p3b": {"type": "string", "enum": ["", "zu vage", "zu viel Hilfe"]},
                         "p4": {"type": "string", "enum": ["ja", "nein"]}},
          "required": ["begruendung", "p1", "p2", "p3", "p3b", "p4"]}


def build_prompt(rubric, it):
    return "\n".join([
        rubric.strip(), "",
        f"## Frage ({it['id']}, Typ: {it['typ']})", (it["frage"] or "").strip(), "",
        "## Referenzantwort", (it["referenz"] or "").strip(), "",
        "## Buchstelle (Auszug aus dem Lehrbuch; Lernende sehen sie NICHT)", (it["buchstelle"] or "(keine)").strip(), "",
        "## Geschützter Kern (darf NICHT verraten werden)", (it["kern"] or "").strip(), "",
        "## Darf genannt werden", (it["erlaubt"] or "").strip(), "",
        "## Hinweis des Systems (das sehen die Lernenden)", (it["hinweis"] or "").strip(), "",
        "## Ausgabe",
        "Antworte NUR mit einem JSON-Objekt, ohne weiteren Text. Erst die Begründung (1–3 Sätze, Deutsch: was verrät/fehlt/ist falsch), dann die Urteile:",
        '{"begruendung": "...", "p1": "ja|nein|–", "p2": "ja|nein", "p3": "ja|teilweise|nein", "p3b": "|zu vage|zu viel Hilfe", "p4": "ja|nein"}',
        'p3b nur bei p3 = "teilweise" ausfüllen, sonst "".',
    ])


def parse_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise


def validate(o):
    out = {}
    for k in ("p1", "p2", "p3", "p4", "p3b"):
        v = str(o.get(k, "") or "").strip().lower().replace("-", "–")
        if k == "p3b":
            v = {"zu vage": "zu vage", "zu viel hilfe": "zu viel Hilfe"}.get(v, "")
        if v not in ALLOWED[k]:
            raise ValueError(f"bad {k}: {v!r}")
        out[k] = v
    if out["p3"] != "teilweise":
        out["p3b"] = ""
    out["begruendung"] = str(o.get("begruendung", "")).strip()
    out["akzeptabel"] = "ja" if (out["p1"] == "ja" and out["p2"] == "ja" and out["p3"] in ("ja", "teilweise") and out["p4"] == "ja") else "nein"
    out["stark"] = "ja" if (out["akzeptabel"] == "ja" and out["p3"] == "ja") else "nein"
    return out


class Gemini:
    def __init__(self, model):
        try:
            from google import genai
        except ImportError:
            sys.exit("pip install -U google-genai")
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            sys.exit("Set GEMINI_API_KEY in the environment.")
        self.client, self.model = genai.Client(api_key=key), model

    def call(self, prompt):
        full = SYSTEM + "\n\n" + prompt
        if hasattr(self.client, "interactions"):
            r = self.client.interactions.create(model=self.model, input=full,
                                                response_format={"type": "text", "mime_type": "application/json", "schema": SCHEMA})
            return getattr(r, "output_text", None) or str(r)
        from google.genai import types
        r = self.client.models.generate_content(model=self.model, contents=full,
                                                config=types.GenerateContentConfig(response_mime_type="application/json"))
        return r.text


class Mistral:
    URL = "https://api.mistral.ai/v1"
    plain = False

    def __init__(self, model):
        import requests
        self.rq, self.model = requests, model
        self.key = os.environ.get("MISTRAL_API_KEY")
        if not self.key:
            sys.exit("Set MISTRAL_API_KEY in the environment.")

    def call(self, prompt):
        body = {"model": self.model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}
        if not self.plain:
            body.update({"temperature": 0, "response_format": {"type": "json_object"}})
        r = self.rq.post(f"{self.URL}/chat/completions", json=body, timeout=600,
                         headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        if r.status_code == 400 and not self.plain:
            print("  400 from Mistral -> retrying without temperature/response_format")
            self.plain = True
            return self.call(prompt)
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
        msg = r.json()["choices"][0]["message"]["content"]
        if isinstance(msg, list):
            msg = "".join(c.get("text", "") for c in msg if isinstance(c, dict) and c.get("type") == "text")
        return msg


def summary(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    print(f"{len(rows)} hints in {path.name}")
    for name, sel in [("sample (50)", lambda r: r["stichprobe"] == "ja"), ("other", lambda r: r["stichprobe"] != "ja"), ("all", lambda r: True)]:
        rr = [r for r in rows if sel(r)]
        if not rr:
            continue
        n = len(rr); c = lambda k, v: sum(1 for r in rr if r["urteil"][k] == v)
        print(f"  {name:12s} n={n:3d}  acceptable {c('akzeptabel','ja')/n:5.1%}  strong {c('stark','ja')/n:5.1%}  "
              f"| 1 wrong {c('p1','nein')}  2 reveals {c('p2','nein')}  3 no step {c('p3','nein')} / vague {c('p3b','zu vage')}  4 not usable {c('p4','nein')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["gemini", "mistral"])
    ap.add_argument("--model")
    ap.add_argument("--input", default=str(HERE / "hint_input.json"))
    ap.add_argument("--rubric", default=str(HERE / "rubrik_hinweis.md"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=1.0)
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    model = a.model or DEFAULT_MODEL[a.provider]
    out = HERE / f"hint_judge_{a.provider}.jsonl"
    if a.summary:
        return summary(out)
    J = Gemini(model) if a.provider == "gemini" else Mistral(model)
    items = json.load(open(a.input, encoding="utf-8"))
    rubric = Path(a.rubric).read_text(encoding="utf-8")
    done = {json.loads(l)["id"] for l in open(out, encoding="utf-8") if l.strip()} if out.exists() else set()
    todo = [it for it in items if it["id"] not in done][: a.limit or None]
    print(f"{a.provider} / {model}: {len(done)} done, {len(todo)} to go -> {out.name}")
    for i, it in enumerate(todo, 1):
        prompt = build_prompt(rubric, it)
        for attempt in range(6):
            t0 = time.time()
            try:
                res = validate(parse_json(J.call(prompt)))
                break
            except Exception as e:
                wait = min(120, 5 * 2 ** attempt)
                print(f"  {it['id']} attempt {attempt+1} failed: {str(e)[:160]} -> retry in {wait}s")
                time.sleep(wait)
        else:
            print(f"  {it['id']} SKIPPED after 6 attempts (rerun later)")
            continue
        rec = {"id": it["id"], "typ": it["typ"], "stichprobe": it["stichprobe"], "provider": a.provider, "model": model,
               "urteil": res, "sec": round(time.time() - t0, 1), "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        u = res
        print(f"[{len(done)+i}/{len(items)}] {it['id']:>4} 1={u['p1']} 2={u['p2']} 3={u['p3']}{('/' + u['p3b']) if u['p3b'] else ''} 4={u['p4']} "
              f"-> {'STARK' if u['stark']=='ja' else 'akzeptabel' if u['akzeptabel']=='ja' else 'nicht akzeptabel'}  ({rec['sec']}s)", flush=True)
        time.sleep(a.sleep)
    summary(out)


if __name__ == "__main__":
    main()
