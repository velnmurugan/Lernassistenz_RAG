#!/usr/bin/env python3
"""
Blind LLM-as-judge for Fragen300 (4 answers per question: GPT ohne/mit RAG, qwen ohne/mit RAG).

The judge sees question, reference answer, book passage and the four answers shuffled as A-D
(no system names). It returns ja | teilweise | nein + a short reason per answer.
Results are appended to judge_<provider>.jsonl (one line per question) -> safe to stop and resume.

Usage (API keys only as environment variables):
  export GEMINI_API_KEY=...      # or MISTRAL_API_KEY=...
  python judge.py --provider gemini  --list-models
  python judge.py --provider gemini  --limit 3          # test run
  python judge.py --provider gemini                     # full run (resumes automatically)
  python judge.py --provider mistral --model mistral-large-latest
  python judge.py --provider gemini --summary           # print scores from the jsonl
"""
import argparse, json, os, random, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COND = ["gpt_o", "gpt_m", "qw_o", "qw_m"]
VALID = {"ja", "teilweise", "nein"}
DEFAULT_MODEL = {"gemini": "gemini-4-argon", "mistral": "mistral-large-latest"}

SYSTEM = (
    "Du bist ein strenger, unabhängiger Prüfer für Antworten auf Fachfragen aus der beruflichen Bildung "
    "(Elektrotechnik, Maschinenbau, Regelungstechnik, Werkstoffe). Du bewertest ausschließlich nach den "
    "Bewertungsregeln, der Referenzantwort und der Buchstelle. Rechne Zahlenwerte selbst nach."
)

def build_prompt(rubric, item, order):
    parts = [rubric.strip(), "",
             f"## Frage ({item['id']}, Typ: {item['typ']})", item["frage"].strip(), "",
             "## Referenzantwort (gilt als richtig)", (item["referenz"] or "").strip(), "",
             "## Buchstelle (Auszug aus dem Lehrbuch, OCR)", (item["buchstelle"] or "(keine)").strip(), ""]
    for letter, cond in zip("ABCD", order):
        parts += [f"## Antwort {letter}", (item["antworten"][cond] or "(leer)").strip(), ""]
    parts += [
        "## Ausgabe",
        "Antworte NUR mit einem JSON-Objekt, ohne weiteren Text, genau in dieser Form:",
        '{"A": {"urteil": "ja|teilweise|nein", "begruendung": "..."}, "B": {...}, "C": {...}, "D": {...}}',
        "Begründung: 1–2 Sätze auf Deutsch; bei teilweise/nein konkret, was falsch ist oder fehlt; bei ja kurz.",
    ]
    return "\n".join(parts)

SCHEMA = {
    "type": "object",
    "properties": {L: {"type": "object",
                       "properties": {"urteil": {"type": "string", "enum": sorted(VALID)},
                                      "begruendung": {"type": "string"}},
                       "required": ["urteil", "begruendung"]} for L in "ABCD"},
    "required": list("ABCD"),
}

def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            return json.loads(m.group(0))
        raise

def validate(obj):
    out = {}
    for L in "ABCD":
        e = obj.get(L) or obj.get(L.lower())
        if not isinstance(e, dict):
            raise ValueError(f"missing {L}")
        u = str(e.get("urteil", "")).strip().lower()
        if u not in VALID:
            raise ValueError(f"bad verdict {L}: {u!r}")
        out[L] = {"urteil": u, "begruendung": str(e.get("begruendung", "")).strip()}
    return out

# ---------------- providers ----------------
class Gemini:
    def __init__(self, model):
        try:
            from google import genai
        except ImportError:
            sys.exit("pip install -U google-genai")
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            sys.exit("Set GEMINI_API_KEY in the environment.")
        self.client = genai.Client(api_key=key)
        self.model = model

    def list_models(self):
        for m in self.client.models.list():
            print(getattr(m, "name", m))

    def call(self, prompt):
        full = SYSTEM + "\n\n" + prompt
        # 1) Interactions API (current docs); 2) fallback to generate_content (older SDKs/models)
        if hasattr(self.client, "interactions"):
            r = self.client.interactions.create(
                model=self.model, input=full,
                response_format={"type": "text", "mime_type": "application/json", "schema": SCHEMA},
            )
            return getattr(r, "output_text", None) or str(r)
        from google.genai import types
        r = self.client.models.generate_content(
            model=self.model, contents=full,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return r.text

class Mistral:
    URL = "https://api.mistral.ai/v1"
    def __init__(self, model):
        import requests
        self.rq = requests
        self.key = os.environ.get("MISTRAL_API_KEY")
        if not self.key:
            sys.exit("Set MISTRAL_API_KEY in the environment.")
        self.model = model

    def _h(self):
        return {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def list_models(self):
        r = self.rq.get(f"{self.URL}/models", headers=self._h(), timeout=60); r.raise_for_status()
        for m in r.json().get("data", []):
            print(m.get("id"), "|", ", ".join(m.get("aliases") or []))

    plain = False   # set True after a 400: some models reject temperature / response_format

    def call(self, prompt):
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        body = {"model": self.model, "messages": msgs}
        if not self.plain:
            body.update({"temperature": 0, "response_format": {"type": "json_object"}})
        r = self.rq.post(f"{self.URL}/chat/completions", headers=self._h(), json=body, timeout=600)
        if r.status_code == 400 and not self.plain:
            print("  400 from Mistral:", r.text[:400])
            print("  -> retrying without temperature/response_format (JSON is parsed from the text)")
            self.plain = True
            return self.call(prompt)
        if r.status_code == 429:
            raise RuntimeError("429 rate limit")
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
        msg = r.json()["choices"][0]["message"]["content"]
        if isinstance(msg, list):   # reasoning models may return content chunks (thinking + text)
            msg = "".join(c.get("text", "") for c in msg if isinstance(c, dict) and c.get("type") == "text")
        return msg

# ---------------- main ----------------
def summary(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    P = {"ja": 1, "teilweise": .5, "nein": 0}
    print(f"{len(rows)} questions in {path.name}")
    for c in COND:
        book = [r["ratings"][c] for r in rows if r["typ"] != "Außerhalb"]
        aus = [r["ratings"][c] for r in rows if r["typ"] == "Außerhalb"]
        sc = 100 * sum(P[v] for v in book) / len(book) if book else 0
        print(f"  {c:6s} book score {sc:5.1f} % (n={len(book)}) | out-of-scope declined {aus.count('ja')}/{len(aus)}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=["gemini", "mistral"])
    ap.add_argument("--model")
    ap.add_argument("--input", default=str(HERE / "judge_input.json"))
    ap.add_argument("--rubric", default=str(HERE / "rubrik.md"))
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions (test)")
    ap.add_argument("--sleep", type=float, default=1.0, help="pause between calls (s)")
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()

    model = a.model or DEFAULT_MODEL[a.provider]
    out = HERE / f"judge_{a.provider}.jsonl"
    if a.summary:
        return summary(out)
    J = Gemini(model) if a.provider == "gemini" else Mistral(model)
    if a.list_models:
        return J.list_models()

    items = json.load(open(a.input, encoding="utf-8"))
    rubric = Path(a.rubric).read_text(encoding="utf-8")
    done = set()
    if out.exists():
        done = {json.loads(l)["id"] for l in open(out, encoding="utf-8") if l.strip()}
    todo = [it for it in items if it["id"] not in done]
    if a.limit:
        todo = todo[: a.limit]
    print(f"{a.provider} / {model}: {len(done)} done, {len(todo)} to go -> {out.name}")

    for i, it in enumerate(todo, 1):
        order = COND[:]
        random.Random(f"{a.provider}|{it['id']}").shuffle(order)
        prompt = build_prompt(rubric, it, order)
        for attempt in range(6):
            t0 = time.time()
            try:
                raw = J.call(prompt)
                res = validate(parse_json(raw))
                break
            except Exception as e:
                wait = min(120, 5 * 2 ** attempt)
                print(f"  {it['id']} attempt {attempt+1} failed: {str(e)[:160]} -> retry in {wait}s")
                time.sleep(wait)
        else:
            print(f"  {it['id']} SKIPPED after 6 attempts (rerun later to fill the gap)")
            continue
        rec = {"id": it["id"], "typ": it["typ"], "provider": a.provider, "model": model,
               "order": dict(zip("ABCD", order)),
               "ratings": {c: res[L]["urteil"] for L, c in zip("ABCD", order)},
               "reasons": {c: res[L]["begruendung"] for L, c in zip("ABCD", order)},
               "sec": round(time.time() - t0, 1), "ts": time.strftime("%Y-%m-%d %H:%M:%S")}
        with open(out, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{len(done)+i}/{len(items)}] {it['id']} " + " ".join(f"{c}={rec['ratings'][c]}" for c in COND) + f"  ({rec['sec']}s)")
        time.sleep(a.sleep)
    summary(out)

if __name__ == "__main__":
    main()
