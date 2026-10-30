"""Offline-Test für Patch M-v1: lädt nur frage_llm und MODEL_NAME aus rag_pipeline.py (keine schweren Importe, kein Ollama)."""
import os, re, sys, glob

pfad = sys.argv[1] if len(sys.argv) > 1 else (glob.glob("lernassistent/rag_pipeline.py") + glob.glob("rag_pipeline.py"))[0]
quelle = open(pfad, encoding="utf-8").read()
fehler = []


def pruefe(name, ok):
    print(("OK    " if ok else "FEHLER"), name)
    if not ok:
        fehler.append(name)


m = re.search(r'^MODEL_NAME = .*$', quelle, re.M)
f = re.search(r'^def frage_llm\(.*?(?=^\S)', quelle[quelle.index("def frage_llm("):] + "\nX", re.M | re.S)
pruefe("MODEL_NAME und frage_llm gefunden", bool(m and f))


class Antwort:
    def __init__(self, code=200, text="ok"):
        self.status_code, self._t = code, text
    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")
    def json(self):
        return {"response": f" {self._t} "}


def lade(env, codes=(200,)):
    for k in ("LERNASSISTENT_MODELL", "LERNASSISTENT_THINK", "LERNASSISTENT_TIMEOUT"):
        os.environ.pop(k, None)
    os.environ.update(env)
    aufrufe = []
    class R:
        @staticmethod
        def post(url, json=None, timeout=None):
            aufrufe.append((json, timeout))
            return Antwort(codes[min(len(aufrufe) - 1, len(codes) - 1)])
    R.exceptions = type("E", (), {"Timeout": type("T", (Exception,), {}), "ConnectionError": type("C", (Exception,), {})})
    ns = {"os": os, "requests": R, "OLLAMA_URL": "http://x/api/generate", "KONTEXT_TOKENS": 0, "DENK_KONTEXT_TOKENS": 16384}
    exec(m.group(0), ns)
    exec(f.group(0), ns)
    return ns, aufrufe


ns, a = lade({})
pruefe("Standard: Modell qwen3.5:9b", ns["MODEL_NAME"] == "qwen3.5:9b")
r = ns["frage_llm"]("hallo")
pruefe("Standard: think ist False", a[0][0].get("think") is False)
pruefe("Standard: Timeout unverändert (120 alt / 300 neu)", a[0][1] in (120, 300))
pruefe("Standard: Antwort getrimmt", r == "ok")
ns["frage_llm"]("hallo", bild="AAAA")
pruefe("Bild im Payload", a[1][0].get("images") == ["AAAA"])
ns["frage_llm"]("x", options={"temperature": 0})
pruefe("Optionen werden durchgereicht", a[2][0].get("options") == {"temperature": 0})
ns, a = lade({"LERNASSISTENT_MODELL": "gemma4:12b-it-qat", "LERNASSISTENT_TIMEOUT": "600"})
ns["frage_llm"]("x", model=ns["MODEL_NAME"])
pruefe("Modell per Umgebung", a[0][0]["model"] == "gemma4:12b-it-qat")
pruefe("Timeout per Umgebung", a[0][1] == 600.0)
ns, a = lade({"LERNASSISTENT_THINK": "low"})
ns["frage_llm"]("x")
pruefe("think=low", a[0][0].get("think") == "low")
ns, a = lade({"LERNASSISTENT_THINK": "ohne"})
ns["frage_llm"]("x")
pruefe("think weggelassen", "think" not in a[0][0])
ns, a = lade({}, codes=(400, 200))
r = ns["frage_llm"]("x")
pruefe("HTTP 400 mit think -> Wiederholung ohne think", len(a) == 2 and "think" not in a[1][0] and r == "ok")
ns, a = lade({"LERNASSISTENT_THINK": "ohne"}, codes=(400,))
try:
    ns["frage_llm"]("x"); ok = False
except RuntimeError:
    ok = len(a) == 1
pruefe("HTTP 400 ohne think -> Fehler, keine Wiederholung", ok)
print(f"\n{'ALLE OK' if not fehler else 'FEHLER: ' + ', '.join(fehler)} ({len(fehler)} Fehler)")
sys.exit(1 if fehler else 0)
