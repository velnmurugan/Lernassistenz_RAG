"""
rechenbaustein.py
-----------------
Rechenbaustein RB-v1 (V11, 20 Oct 2026): unabhängige Nachrechnung per Python.

Anlass: In N100 (V10a) sind 10 von 19 Rechenaufgaben richtig. Die Fehler stehen oft in Antworten ohne
prüfbare Gleichung ("ω = 1047,2 s⁻¹ … J ≈ 0,25 kg·m²", "U = 8,5 V" statt 13,3 V); RP-v3 sieht nur
ausgeschriebene Gleichungsketten und meldet dort "ok".

Vorgehen (Program-aided: das Modell stellt die Rechnung auf, Python führt sie aus):
  1. Zweiter, unabhängiger Aufruf (Prompt RB-v1): FORMEL, WERTE (Name = Zahl [Einheit]), RECHNUNG (ein
     Python-Ausdruck), EINHEIT. Das Modell sieht Frage und Material, aber NICHT seine erste Antwort.
  2. Python wertet RECHNUNG sicher aus (ast, nur + − * / ** und sqrt/sin/cos/tan/exp/ln/log10/pi/e/abs).
  3. Herkunftsprüfung: Jede Zahl in WERTE muss in der Frage oder im Material stehen (oder eine
     Umrechnungskonstante sein: 60, 100, 1000, 3600, 2, 3 …); sonst gilt die Nachrechnung als nicht verwertbar.
  4. Vergleich: Der Wert im ersten Satz der Lösung (Zahlen aus der Frage zählen nicht) muss zum Ergebnis
     passen (Toleranz wie RP, auch Prozent, Vorsatz-Faktoren 10³). Stimmt nichts überein: Befund.
Der Befund geht in die vorhandene Reparatur von rag_pipeline.rechnung_pruefen (ein Neuschreib-Aufruf mit dem
Python-Ergebnis, sonst sichtbarer Vermerk). Grenzen: falsch gewählte Formel und falsche Eingangswerte werden
nicht erkannt, wenn beide Wege denselben Fehler machen; Aufgaben ohne Zahl im ersten Satz werden übersprungen.

RB-v2 (V11b, 21 Oct 2026, gehört zu RP-v5; RB-v1 bleibt für RP-v4 unverändert). Anlass: Live-Test "Drehstrom-Öltransformator
40 kVA, 5 kV / 400 V: primärer und sekundärer Bemessungsstrom" – die Lösung nannte "2,89 A und 72 A" (Zahlen des
Buchbeispiels 50 kVA / 10 kV), der Rechenweg darunter ergab 4,62 A und 57,7 A. Änderungen:
  1. Mehrere Ergebnisse: RECHNUNG besteht aus Zeilen "name = ausdruck" (Zwischen- und Endergebnisse, spätere Zeilen
     dürfen frühere Namen nutzen); ERGEBNIS nennt die gesuchten Größen.
  2. Jede Zahl mit Einheit im ersten Satz der Lösung (nicht aus der Frage) muss zu einem Ergebnis passen; Zahlen ohne
     Einheit zählen nicht (Fall "bei 3 Phasen"). Ohne Zahl mit Einheit gilt wie in RB-v1: mindestens eine muss passen.
  3. Formelquelle: QUELLE nennt die Formel wörtlich aus dem Material oder GRUNDWISSEN; der Auszug wird im Material
     gesucht (`quelle_im_material`). Ergebnis: True / False / None (ohne Quelle).
  4. Geprüfte Lösung (`pruefloesung`): Weicht die Antwort ab und behebt der Neuschreib-Aufruf das nicht, wird die
     Python-Nachrechnung als Lösung gezeigt – nur wenn Zahlen und Formel aus dem Material belegt sind (Quelle True).
"""
import ast
import difflib
import math
import operator
import re

import rechenpruefung as rp

RB_VERSION = "RB-v1"

_FUNKTIONEN = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "exp": math.exp,
               "ln": math.log, "log": math.log, "log10": math.log10, "abs": abs, "radians": math.radians,
               "atan": math.atan, "asin": math.asin, "acos": math.acos}
_KONSTANTEN = {"pi": math.pi}
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
# Umrechnungs- und Strukturzahlen, die nicht aus Frage oder Material stammen müssen
ERLAUBTE_KONSTANTEN = {0, 1, 2, 3, 4, 5, 10, 60, 100, 1000, 3600, 1e6, 1e-3, 1e-6, 0.5, 0.001, 0.01, 0.1,
                       360, 1e3, 1e9, 1e-9, 1e-12, 273.15, 9.81, 9.80665}



_HOCH_ZIFFER = {"⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9", "⁻": "-"}


def normiere_ausdruck(ausdruck):
    """RB-v3 (V13): Schreibweisen des Modells in einen Python-Ausdruck übersetzen. Neu gegenüber RB-v2:
    "√2" / "√x" ohne Klammer (vorher "sqrt2" -> Auswertungsfehler, N100 F29), "2π" / "2 pi" / "2 sqrt(2)" / ")(" /
    ") pi" mit unsichtbarem Malzeichen, Hochzahlen ")²" / "x²", "÷". Reine Einheiten nach einer Zahl ("0,5 m") bleiben
    unberührt: Malzeichen werden nur vor pi, sqrt, Klammer auf und nach Klammer zu eingefügt."""
    t = (ausdruck or "").strip()
    t = t.replace("^", "**").replace("·", "*").replace("×", "*").replace("−", "-").replace("÷", "/")
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)  # deutsche Dezimalkommas
    t = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+", lambda m: "**(" + "".join(_HOCH_ZIFFER[c] for c in m.group(0)) + ")", t)
    t = re.sub(r"√\s*(\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_]*)(?!\s*\()", r"sqrt(\1)", t)  # √2, √x
    t = t.replace("√", "sqrt").replace("π", "pi")
    t = re.sub(r"\bsqrt\s*(\d+(?:\.\d+)?)", r"sqrt(\1)", t)                         # sqrt3
    t = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s+(?=(?:pi|sqrt)\b)", r"\1*", t)       # 2 pi, 2 sqrt(2)
    t = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)(?=(?:pi|sqrt)\b)", r"\1*", t)          # 2pi
    t = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)\s*(?=\()", r"\1*", t)                     # 2 (..)
    t = re.sub(r"\)\s*(?=[\d(]|pi\b|sqrt\b)", ")*", t)                              # ) (..) / ) 2 / ) pi
    return t


def sicher_auswerten(ausdruck, namen=None):
    """Wertet einen Python-Ausdruck aus (nur Zahlen, Namen aus `namen`, + − * / **, erlaubte Funktionen).
    Rückgabe float oder None. Kein eval."""
    namen = {**(namen or {}), **_KONSTANTEN} if RB_V8 else {**_KONSTANTEN, **(namen or {})}
    ausdruck = normiere_ausdruck(ausdruck)

    def w(k):
        if isinstance(k, ast.Expression):
            return w(k.body)
        if isinstance(k, ast.Constant) and isinstance(k.value, (int, float)) and not isinstance(k.value, bool):
            return float(k.value)
        if isinstance(k, ast.Name) and k.id in namen:
            return float(namen[k.id])
        if isinstance(k, ast.BinOp) and type(k.op) in _OPS:
            a, b = w(k.left), w(k.right)
            if isinstance(k.op, ast.Pow) and abs(b) > (30 if a == 10 else 12):  # V12.2: 10^18 (Elementarladung) erlaubt
                raise ValueError("Exponent")
            return _OPS[type(k.op)](a, b)
        if isinstance(k, ast.UnaryOp) and type(k.op) in _OPS:
            return _OPS[type(k.op)](w(k.operand))
        if (isinstance(k, ast.Call) and isinstance(k.func, ast.Name) and k.func.id in _FUNKTIONEN
                and len(k.args) == 1 and not k.keywords):
            return float(_FUNKTIONEN[k.func.id](w(k.args[0])))
        raise ValueError("nicht erlaubt")
    try:
        wert = w(ast.parse(ausdruck, mode="eval"))
        return wert if math.isfinite(wert) else None
    except Exception:
        return None


def baue_prompt(frage, kontext):
    return f"""Du rechnest eine Aufgabe aus der Technik nach. Antworte NUR in diesem Format, ohne weiteren Text:

FORMEL: <die Formel, die zur Frage passt, mit Quelle aus dem Material, sonst Grundwissen>
WERTE:
<name> = <Zahl oder Rechenausdruck> <Einheit>
(eine Zeile je Größe; nur Zahlen aus der Frage oder dem Material; Umrechnungen in die Zahl schreiben,
z. B. n = 1000/60 für 1000 1/min in 1/s; Namen nur Buchstaben und Ziffern, ohne Leerzeichen)
RECHNUNG: <ein Python-Ausdruck mit den Namen aus WERTE; erlaubt: + - * / ** ( ) sqrt() sin() cos() tan() exp() ln() log10() pi>
EINHEIT: <Einheit des Ergebnisses>

Ist die Frage keine Rechenaufgabe oder fehlt ein Wert, schreibe nur: RECHNUNG: KEINE

Material:
{kontext}

Frage: {frage}"""


def parse(roh):
    """Liest die Modellantwort. Rückgabe dict mit formel, werte (name -> text), rechnung, einheit; None bei Formatfehler."""
    roh = roh or ""
    m = re.search(r"RECHNUNG:\s*(.+)", roh)
    if not m:
        return None
    rechnung = m.group(1).strip().strip("`")
    if rechnung.upper().startswith("KEINE"):
        return {"rechnung": "KEINE", "werte": {}, "formel": "", "einheit": ""}
    werte = {}
    wm = re.search(r"WERTE:\s*\n(.*?)(?=\nRECHNUNG:)", roh, re.S)
    for zeile in (wm.group(1).splitlines() if wm else []):
        z = re.match(r"\s*[-*]?\s*([A-Za-zα-ωΑ-ΩηφΦϑ_][A-Za-z0-9α-ωΑ-Ωηφ_Φϑ]*)\s*=\s*(.+)$", zeile)
        if z:
            werte[z.group(1)] = z.group(2).strip()
    fm = re.search(r"FORMEL:\s*(.+)", roh)
    em = re.search(r"EINHEIT:\s*(.+)", roh)
    return {"rechnung": rechnung, "werte": werte, "formel": fm.group(1).strip() if fm else "",
            "einheit": em.group(1).strip() if em else ""}


def _wert_ausdruck(text, namen=None):
    """'1000/60 1/s' oder '0,5 m/s' -> (Ausdruck ohne Einheit, Wert): der längste Anfang (in Leerraum-Schritten),
    den sicher_auswerten liest. Nie stillschweigend kürzen, wenn der Rest nach Rechnung aussieht."""
    teile = text.strip().split()
    for n in range(len(teile), 0, -1):
        kandidat = " ".join(teile[:n])
        wert = sicher_auswerten(kandidat, namen)
        if wert is not None:
            rest = " ".join(teile[n:])
            if re.match(r"[-+*/^·×(]|\d", rest) and not re.fullmatch(r"1\s*/\s*[A-Za-zµ°]+\S*", rest):
                # Rest sieht nach Rechnung aus (Einheiten wie "1/s", "1/min" ausgenommen)
                continue
            return kandidat.replace(",", "."), wert
    return None, None


def _zahlen_in(text):
    return {round(w, 9) for w, _, _ in rp._zahlen_mit_stellen(text)}


def rechne(parsed, frage, kontext):
    """Führt die Nachrechnung aus. Rückgabe dict(ergebnis, einheit, formel, werte, grund). ergebnis=None wenn
    nicht verwertbar; grund sagt warum (keine_rechnung | formatfehler | wert_unlesbar | erfunden | auswertung)."""
    if parsed is None:
        return {"ergebnis": None, "grund": "formatfehler"}
    if parsed["rechnung"] == "KEINE":
        return {"ergebnis": None, "grund": "keine_rechnung"}
    bekannt = _zahlen_in(frage) | _zahlen_in(kontext) | {round(float(c), 9) for c in ERLAUBTE_KONSTANTEN}
    namen = {}
    for name, text in parsed["werte"].items():
        ausdruck, wert = _wert_ausdruck(text)
        if wert is None:
            return {"ergebnis": None, "grund": "wert_unlesbar", "detail": f"{name} = {text}"}
        for lit in re.findall(r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", ausdruck):
            if round(float(lit), 9) not in bekannt:
                return {"ergebnis": None, "grund": "erfunden", "detail": f"{name} = {text}"}
        namen[name] = wert
    ergebnis = sicher_auswerten(parsed["rechnung"], namen)
    if ergebnis is None:
        return {"ergebnis": None, "grund": "auswertung", "detail": parsed["rechnung"]}
    return {"ergebnis": ergebnis, "einheit": parsed["einheit"], "formel": parsed["formel"],
            "werte": parsed["werte"], "rechnung": parsed["rechnung"], "grund": ""}


def kopfzahlen(loesung, frage):
    """Zahlen im ersten Satz der Lösung, die nicht aus der Frage stammen. Leer = nichts zu vergleichen."""
    text = loesung or ""
    m = rp._erster_satz_ende(text)
    kopf = text[:m.start()] if m else text
    aus_frage = {w for w, _, _ in rp._zahlen_mit_stellen(frage)}
    return [(w, st, t) for w, st, t in rp._zahlen_mit_stellen(kopf) if w not in aus_frage]


def vergleiche(loesung, frage, res):
    """Befundliste (leer = ok oder nicht vergleichbar). Passt mindestens eine Kopfzahl zum Ergebnis
    (auch Prozent, Vorsatz-Faktor 10³), ist alles in Ordnung."""
    if res.get("ergebnis") is None:
        return []
    kopf = kopfzahlen(loesung, frage)
    if not kopf:
        return []
    erg = abs(res["ergebnis"])
    for w, st, _ in kopf:
        if any(rp._passt(k, w, st) for k in (erg, erg * 100, erg / 100)):
            return []
    genannt = " / ".join(t for _, _, t in kopf[:3])
    return [{"art": "baustein", "ausdruck": res.get("rechnung", ""), "gerechnet": erg, "angegeben": kopf[0][0],
             "satz": (loesung or "")[:200],
             "text": (f"Die unabhängige Python-Nachrechnung ({res.get('formel', '').strip() or 'Formel'}; "
                      f"{res.get('rechnung', '')}) ergibt {rp._zahl_de(res['ergebnis'])} {res.get('einheit', '')}".strip()
                      + f", die Lösung nennt {genannt}")}]



# ---------------------------------------------------------------------------------------------------------
# RB-v2 (V11b)
# ---------------------------------------------------------------------------------------------------------
RB_VERSION_2 = "RB-v2"


def baue_prompt_v2(frage, kontext):
    return f"""Du rechnest eine Aufgabe aus der Technik nach. Antworte NUR in diesem Format, ohne weiteren Text:

FORMEL: <die Formeln, die zur Frage passen>
WERTE:
<name> = <Zahl oder Rechenausdruck> <Einheit>
(eine Zeile je Größe; nur Zahlen aus der Frage oder dem Material; Umrechnungen in die Zahl schreiben,
z. B. n = 1000/60 für 1000 1/min in 1/s; Namen nur Buchstaben und Ziffern, ohne Leerzeichen und Unterstrich)
RECHNUNG:
<name> = <Python-Ausdruck mit den Namen aus WERTE und aus früheren Zeilen; erlaubt: + - * / ** ( ) sqrt() sin() cos() tan() exp() ln() log10() pi>
(eine Zeile je Zwischen- und Endergebnis, von oben nach unten)
ERGEBNIS: <Namen der gesuchten Größen, durch Komma getrennt, in der Reihenfolge der Frage>
EINHEIT: <Einheiten der gesuchten Größen, durch Komma getrennt, in derselben Reihenfolge>
QUELLE: <die Formel wörtlich aus dem Material als kurzer Auszug mit Gleichungszeichen (höchstens eine Zeile) oder GRUNDWISSEN, wenn sie nicht im Material steht>

Sind mehrere Größen gesucht (zum Beispiel Primär- und Sekundärstrom), rechne jede mit einer eigenen Zeile.
Beachte die genaue Bedingung der Frage (zum Beispiel Art der Last, welche Größe vernachlässigt wird) und setze sie in die Formel ein.
Ist die Frage keine Rechenaufgabe oder fehlt ein Wert, schreibe nur: RECHNUNG: KEINE

Material:
{kontext}

Frage: {frage}"""


_NAME = r"[A-Za-zα-ωΑ-ΩηφΦϑ_][A-Za-z0-9α-ωΑ-Ωηφ_Φϑ]*"


def parse_v2(roh):
    """Liest die RB-v2-Antwort. Rückgabe dict(formel, quelle, werte, schritte[(name, ausdruck)], ergebnis_namen, einheit,
    rechnung) oder None bei Formatfehler. rechnung == "KEINE" bei Nicht-Rechenaufgaben."""
    roh = roh or ""
    m = re.search(r"RECHNUNG:[ \t]*(.*?)(?=\n\s*(?:ERGEBNIS|EINHEIT)\s*:|\Z)", roh, re.S)
    if not m:
        return None
    block = m.group(1).strip().strip("`")
    if block.upper().startswith("KEINE"):
        return {"rechnung": "KEINE", "werte": {}, "schritte": [], "ergebnis_namen": [], "formel": "", "quelle": "",
                "einheit": ""}
    schritte = []
    for zeile in block.splitlines():
        zeile = zeile.strip().strip("`")
        if not zeile:
            continue
        z = re.match(rf"[-*]?\s*({_NAME})\s*=\s*(.+)$", zeile)
        if z:
            schritte.append((z.group(1), z.group(2).strip()))
        elif not schritte and "=" not in zeile:
            schritte.append(("ergebnis", zeile))  # alte Form: ein einzelner Ausdruck
    if not schritte:
        return None
    werte = {}
    wm = re.search(r"WERTE:\s*\n(.*?)(?=\nRECHNUNG:)", roh, re.S)
    for zeile in (wm.group(1).splitlines() if wm else []):
        z = re.match(rf"\s*[-*]?\s*({_NAME})\s*=\s*(.+)$", zeile)
        if z:
            werte[z.group(1)] = z.group(2).strip()
    gm = re.search(r"ERGEBNIS:\s*(.+)", roh)
    namen = [n.strip() for n in re.split(r"[,;]|\bund\b", gm.group(1)) if n.strip()] if gm else []
    namen = [n for n in namen if any(n == s[0] for s in schritte)] or [schritte[-1][0]]
    fm = re.search(r"FORMEL:\s*(.+)", roh)
    qm = re.search(r"QUELLE:\s*(.+)", roh)  # eine Zeile; V12.2: auf 400 Zeichen gekürzt (Schleifen)
    em = re.search(r"EINHEIT:\s*(.+)", roh)
    return {"rechnung": "; ".join(f"{n} = {a}" for n, a in schritte), "werte": werte, "schritte": schritte,
            "ergebnis_namen": namen, "formel": fm.group(1).strip() if fm else "",
            "quelle": qm.group(1).strip()[:400] if qm else "", "einheit": em.group(1).strip() if em else ""}


_SUBZIFFER = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def _norm_formel(text):
    """Vergleichsform einer Formel: klein, ohne Leerraum, Malpunkt/Stern, Klammern, Unterstrich und LaTeX-Reste;
    Wurzel, Hochzahlen, Tiefzahlen (μ₀ = mu0) vereinheitlicht. V12: Mal-Zeichen und Klammern entfallen ganz, damit
    "F = B²·A/(2·μ₀)" und "F = (B² · A)/(2 · μ₀)" gleich werden (V11b: falsche Meldung "Formel nicht im Material")."""
    t = (text or "").lower()
    for a, b in (("√", "sqrt"), ("−", "-"), ("–", "-"), ("²", "^2"), ("³", "^3"), ("μ", "mu"), ("µ", "mu"),
                 ("\\cdot", ""), ("\\sqrt", "sqrt"), ("\\left", ""), ("\\right", ""), ("\\frac", "frac"),
                 ("·", ""), ("×", ""), ("*", "")):
        t = t.replace(a, b)
    t = t.translate(_SUBZIFFER)
    return re.sub(r"[\s_{}$\\()\[\]]", "", t)


def quelle_im_material(quelle, kontext):
    """True, wenn die genannte Formelquelle im Material steht: Gleichungsnummer ("Gl. 4.30") kommt vor, oder ein Auszug
    von mindestens 8 Zeichen stimmt zu mindestens 75 % mit einem zusammenhängenden Stück des Materials überein.
    False, wenn GRUNDWISSEN oder nichts passt. None, wenn keine Quelle genannt wurde."""
    q = (quelle or "").strip()
    if not q:
        return None
    if re.match(r"(?:grundwissen|keine|nicht im material|-)", q, re.I):
        return False
    for nr in re.findall(r"(?:Gl\.?|Gleichung)\s*\(?(\d+\.\d+)\)?", q, re.I):
        if re.search(rf"(?<![\d.]){re.escape(nr)}(?![\d])", kontext or ""):
            return True
    if "=" not in q:  # V12.2: ein Auszug ohne Gleichung belegt keine Formel (F1: Quelle nannte nur die Ladung von 1 C)
        return False
    if V18_B:  # V18-B: nur der Teil vor einer Kürzung („…“) oder vor einem weiteren Zitat zählt
        q = re.split(r"\|\|\||…|\.\.\.", q)[0].strip()
        if "=" not in q:
            return False
    qn, kn = _norm_formel(q), _norm_formel(kontext)
    if len(qn) < 8:
        return V18_B and len(qn) >= 5 and qn in kn  # V18-B: kurze Formel (F = P2/v) gilt bei wörtlichem Treffer
    
    if qn in kn:
        return True
    teil = difflib.SequenceMatcher(None, qn, kn, autojunk=False).find_longest_match(0, len(qn), 0, len(kn))
    return teil.size >= 0.75 * len(qn)


_FAKTOREN = (1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9, 100.0, 0.01, 60.0, 3600.0)


def _belegt(lit, bekannt):
    """Zahl `lit` steht in Frage/Material oder ist eine bekannte Zahl mal einem Umrechnungsfaktor (kVA -> VA: 40 -> 40000).
    RB-v1 prüfte nur die exakte Zahl und wies "40000 VA" bei "40 kVA" in der Frage als erfunden ab (Live-Test 21 Oct 2026)."""
    if round(lit, 9) in bekannt:
        return True
    return any(round(lit / f, 9) in bekannt or round(lit * f, 9) in bekannt for f in _FAKTOREN)


def _ohne_einheit(ausdruck, namen):
    """V12.2: "500 * (0,5 / x)**2 kg*m**2" -> ("500 * (0,5 / x)**2", Wert). Hängt eine Einheit am Ausdruck, wird der längste
    auswertbare Anfang genommen, wenn der Rest wie eine Einheit aussieht (beginnt mit Buchstabe, kein Name aus `namen`)."""
    wert = sicher_auswerten(ausdruck, namen)
    if wert is not None:
        return ausdruck, wert
    teile = ausdruck.split()
    for n in range(len(teile) - 1, 0, -1):
        rest = " ".join(teile[n:])
        if not re.fullmatch(r"[A-Za-zµμΩ°][A-Za-z0-9µμΩ°*/^·²³\-]*", rest) or any(
                tok in namen or tok in _KONSTANTEN for tok in re.findall(r"[A-Za-zα-ωΑ-Ω_][A-Za-z0-9α-ωΑ-Ω_]*", rest)
                if tok in namen or tok in _KONSTANTEN):
            continue
        w = sicher_auswerten(" ".join(teile[:n]), namen)
        if w is not None:
            return " ".join(teile[:n]), w
    return ausdruck, None


def _literale(ausdruck):
    """Zahlenliterale zur Belegprüfung; "10^18"/"10**-3" (Zehnerpotenzen) zählen als Struktur, nicht als erfundene Zahl."""
    a = re.sub(r"(?<![\w.])10\s*(?:\^|\*\*)\s*\(?-?\d+\)?", " ", ausdruck)
    return re.findall(r"(?<![A-Za-z_])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", a)


def rechne_v2(parsed, frage, kontext):
    """Wie `rechne`, für mehrere Zeilen. Rückgabe dict(ergebnisse=[(name, wert)], ergebnis=erster Wert, einheit, formel,
    quelle, formel_im_material, werte, rechnung, schritte, grund). ergebnisse leer wenn nicht verwertbar."""
    if parsed is None:
        return {"ergebnis": None, "ergebnisse": [], "grund": "formatfehler"}
    if parsed["rechnung"] == "KEINE":
        return {"ergebnis": None, "ergebnisse": [], "grund": "keine_rechnung"}
    bekannt = _zahlen_in(frage) | _zahlen_in(kontext) | {round(float(c), 9) for c in ERLAUBTE_KONSTANTEN}
    namen = {}
    unleserlich = {}  # V12.2: unlesbare Werte brechen nur ab, wenn die Rechnung sie braucht (F29: "R_L = unendlich Ohm")
    for name, text in parsed["werte"].items():
        ausdruck, wert = _wert_ausdruck(text, namen)  # V12.2: Werte dürfen frühere Namen und pi nutzen (ω = 2·pi·n)
        if wert is None:
            unleserlich[name] = text
            continue
        for lit in _literale(ausdruck):
            if not _belegt(float(lit), bekannt):
                return {"ergebnis": None, "ergebnisse": [], "grund": "erfunden", "detail": f"{name} = {text}"}
        namen[name] = wert
    berechnet = set()  # Namen, die aus einer echten Rechnung stammen
    nur_zahl = set()   # Namen, die nur als fertige Zahl hingeschrieben wurden (Kopfrechnung des Modells)
    for name, ausdruck in parsed["schritte"]:
        ausdruck_ohne, wert = _ohne_einheit(ausdruck, namen)
        ist_literal = wert is not None and bool(re.fullmatch(r"\s*[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?\s*", ausdruck_ohne))
        if ist_literal and name in berechnet:
            continue  # V12.2b: "P = 31,4925" nach der Rechnung überschreibt sie nicht (A/B F15: 19,298 statt 18,95)
        if wert is None:
            fehlt = [n for n in unleserlich if re.search(rf"(?<![A-Za-z0-9_]){re.escape(n)}(?![A-Za-z0-9_])", ausdruck)]
            if fehlt:
                return {"ergebnis": None, "ergebnisse": [], "grund": "wert_unlesbar", "detail": f"{fehlt[0]} = {unleserlich[fehlt[0]]}"}
            return {"ergebnis": None, "ergebnisse": [], "grund": "auswertung", "detail": f"{name} = {ausdruck}"}
        namen[name] = wert
        if ist_literal:
            nur_zahl.add(name)
        else:
            berechnet.add(name)
            nur_zahl.discard(name)
    if any(n in nur_zahl for n in parsed["ergebnis_namen"]):  # Ergebnis ist nur eine hingeschriebene Zahl, nicht gerechnet
        return {"ergebnis": None, "ergebnisse": [], "grund": "literal", "detail": parsed["rechnung"]}
    ergebnisse = [(n, namen[n]) for n in parsed["ergebnis_namen"] if n in namen]
    if not ergebnisse:
        return {"ergebnis": None, "ergebnisse": [], "grund": "auswertung", "detail": parsed["rechnung"]}
    return {"ergebnis": ergebnisse[0][1], "ergebnisse": ergebnisse, "einheit": parsed["einheit"],
            "formel": parsed["formel"], "quelle": parsed["quelle"],
            "formel_im_material": quelle_im_material(parsed["quelle"], kontext), "werte": parsed["werte"],
            "rechnung": parsed["rechnung"], "schritte": parsed["schritte"], "grund": ""}


def _einheiten_liste(res):
    teile = [e.strip() for e in re.split(r"[,;]", res.get("einheit") or "") if e.strip()]
    return teile if len(teile) == len(res["ergebnisse"]) else [""] * len(res["ergebnisse"])


def ergebnis_text(res):
    """'I1N = 4,619 A; I2N = 57,74 A' (Einheiten nur, wenn je Ergebnis genau eine genannt ist)."""
    einheiten = _einheiten_liste(res)
    return "; ".join(f"{n} = {rp._zahl_de(w)} {e}".rstrip() for (n, w), e in zip(res["ergebnisse"], einheiten))


def _kopf_mit_einheit(loesung, frage):
    """Zahlen im ersten Satz (nicht aus der Frage) mit Kennzeichen, ob direkt eine Einheit folgt: [(w, stellen, text, hat_einheit)]."""
    text = loesung or ""
    m = rp._erster_satz_ende(text)
    kopf = rp._VERWEIS_ZAHL.sub(" ", text[:m.start()] if m else text)
    aus_frage = {w for w, _, _ in rp._zahlen_mit_stellen(frage)}
    out = []
    for z in re.finditer(r"(?<![A-Za-zÄÖÜäöüßα-ωΑ-Ω_₀-₉])\d+(?:[.,]\d+)*", kopf):  # nicht die "1" in "I1N"
        try:
            w = abs(rp.zahl(z.group(0)))
        except ValueError:
            continue
        if w in aus_frage:
            continue
        nach = re.match(r"\s*(%|[A-Za-zΩµμ°]+)", kopf[z.end():])
        hat = bool(nach) and (nach.group(1) == "%" or bool(rp._EINHEIT.fullmatch(nach.group(1))))
        out.append((w, rp._stellen(z.group(0)), z.group(0), hat))
    return out


def vergleiche_v2(loesung, frage, res):
    """Befundliste (leer = ok oder nicht vergleichbar). Jede Zahl mit Einheit im ersten Satz muss zu einem Ergebnis der
    Nachrechnung passen (auch Prozent, Vorsatz-Faktor 10³); gibt es keine Zahl mit Einheit, genügt eine passende Zahl."""
    if not res.get("ergebnisse"):
        return []
    kopf = _kopf_mit_einheit(loesung, frage)
    if not kopf:
        return []
    werte = [abs(w) for _, w in res["ergebnisse"]]

    def passt(w, st):
        return any(rp._passt(k, w, st) for e in werte for k in (e, e * 100, e / 100))
    mit = [k for k in kopf if k[3]]
    if mit:
        schlecht = any(not passt(w, st) for w, st, _, _ in mit)
    else:
        schlecht = not any(passt(w, st) for w, st, _, _ in kopf)
    if not schlecht:
        return []
    genannt = " / ".join(t for _, _, t, _ in (mit or kopf)[:3])
    return [{"art": "baustein", "ausdruck": res.get("rechnung", ""), "gerechnet": werte[0], "angegeben": kopf[0][0],
             "satz": (loesung or "")[:200],
             "text": (f"Die unabhängige Python-Nachrechnung ({res.get('formel', '').strip() or 'Formel'}) ergibt "
                      f"{ergebnis_text(res)}, die Lösung nennt {genannt}")}]


_HOCHZIFFER = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")
_GRIECHISCH = {"eta": "η", "phi": "φ", "varphi": "φ", "mu0": "μ₀", "pi": "π", "delta": "Δ", "omega": "ω", "rho": "ρ",
               "alpha": "α", "lambda": "λ", "tau": "τ", "theta": "θ"}


def lesbar(s):
    """Python-Schreibweise -> Lehrbuchschreibweise für die Anzeige: ** -> Hochzahl, sqrt -> √, * -> ·, 1e-3 -> 1·10⁻³,
    Dezimalpunkt -> Komma, [T] -> T, [-] entfällt, eta -> η. Nur Darstellung, die Rechnung bleibt unberührt."""
    t = str(s or "")
    t = re.sub(r"\s*\[\s*-?\s*\]", "", t)
    t = re.sub(r"\[([^\]]*)\]", r" \1", t)
    t = re.sub(r"sqrt\s*\(", "√(", t)
    t = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)[eE]([-+]?\d+)",
               lambda m: f"{m.group(1)}·10{m.group(2).lstrip('+').translate(_HOCHZIFFER)}", t)
    t = re.sub(r"\*\*\s*\(?\s*(-?\d+)\s*\)?", lambda m: m.group(1).translate(_HOCHZIFFER), t)
    t = re.sub(r"\^\s*\(?\s*(-?\d+)\s*\)?", lambda m: m.group(1).translate(_HOCHZIFFER), t)
    t = t.replace("**", "^").replace("*", " · ")
    t = re.sub(r"\b(" + "|".join(_GRIECHISCH) + r")\b", lambda m: _GRIECHISCH[m.group(1)], t)
    t = re.sub(r"(?<=\d)\.(?=\d)", ",", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def pruefloesung(res, urspruenglich=""):
    """Lösungstext aus der Nachrechnung (nur Python-Werte und die Formel aus dem Material). Format wie die Modelllösung:
    erster Satz mit den Ergebnissen, dann 'Begründung:' mit Formel, Werten und Rechnung (ab V12 in Lehrbuchschreibweise)."""
    werte = "; ".join(f"{lesbar(n)} = {lesbar(t)}" for n, t in res.get("werte", {}).items())
    schritte = "; ".join(f"{lesbar(n)} = {lesbar(a)}" for n, a in res.get("schritte", []))
    teile = [f"Formel: {lesbar(res.get('formel', ''))}"] if res.get("formel") else []
    if werte:
        teile.append(f"Werte: {werte}")
    if schritte:
        teile.append(f"Rechnung: {schritte}")
    begr = ". ".join(teile)
    kopf = f"Nachgerechnet ergibt sich: {ergebnis_text(res)}."
    vermerk = ("⚠ Automatische Prüfung: Die erste Antwort des Modells wich von der Nachrechnung ab; "
               "gezeigt wird die Nachrechnung (Formel aus dem Lernmaterial).")
    return f"{kopf}\n\nBegründung: {begr}\n\n{vermerk}" if begr else f"{kopf}\n\n{vermerk}"


# ---------------------------------------------------------------------------------------------------------
# RB-v3 (V13, 25 Oct 2026; gehört zu RP-v6)
# ---------------------------------------------------------------------------------------------------------
# Anlass: N100 V11B (21 Oct) – bei F1, F29, F62 und B24 war die Nachrechnung "nicht verwertbar: wert_unlesbar",
# also wurde nichts geprüft; F29 scheiterte an "2√2" ohne Klammer; F61 (V12.9, alte KB) blieb unbemerkt, weil die
# Antwort nur eine Zahl aus der Frage nannte; F1 bekam eine falsche Warnung, obwohl die Formel der Nachrechnung
# nicht im Buch stand. Änderungen:
#   1. normiere_ausdruck (oben): √2, 2π, ")(", Hochzahlen.
#   2. Retry: ist die erste Nachrechnung nicht auswertbar (RETRY_GRUENDE), ein zweiter Aufruf mit Fehlerbericht und
#      Formatbeispiel (baue_prompt_v3).
#   3. Kopfzahlen-Rückfall: nennt der erste Satz nur Zahlen aus der Frage (Antwort = gegebener Wert), werden sie
#      trotzdem gegen das Ergebnis geprüft (vergleiche_v3).
RB_VERSION_3 = "RB-v3"
RETRY_GRUENDE = ("wert_unlesbar", "auswertung", "formatfehler", "literal", "dimension", "zwischenwert", "ergebnis_name")  # "dimension": nur RB-v8


def baue_prompt_v3(frage, kontext, fehler=None):
    """Wie baue_prompt_v2; mit `fehler` (grund, detail) als Wiederholung: der Fehlerbericht und das Formatbeispiel stehen
    davor, damit das Modell dieselbe Aufgabe in auswertbarer Schreibweise noch einmal rechnet."""
    basis = baue_prompt_v2(frage, kontext)
    regeln = ("Schreibweise (wichtig, die Zeilen werden automatisch ausgewertet):\n"
              "- WERTE: eine Zahl oder ein Rechenausdruck je Zeile, danach die Einheit. Keine Wörter wie „unendlich“ oder „gesucht“.\n"
              "- RECHNUNG: nur Namen aus WERTE, Zahlen und + - * / ** ( ) sqrt() pi; Malzeichen immer ausschreiben (2*pi*n,"
              " nicht 2πn); Wurzel als sqrt(x), nie √; Potenzen mit **; keine Einheiten in RECHNUNG.\n"
              "- Beispiel: WERTE: U = 230 V / n = 1500/60 1/s   RECHNUNG: w = 2*pi*n / P = U**2/R\n\n")
    if V18_A:  # V18-A: jede Größe in eigener Zeile, rechts vom = nur Zahlen; das alte Beispiel zeigte zwei Größen in einer Zeile
        regeln = ("Schreibweise (wichtig, die Zeilen werden automatisch ausgewertet):\n"
                  "- WERTE: genau eine Größe je Zeile, Form „Name = Zahl Einheit“. Rechts vom = nur Zahlen oder Rechenausdrücke\n"
                  "  mit Zahlen, nie eine Variable oder Gleichung (nicht „n1 = n/10“, sondern „n1 = 1/10“). Keine Platzhalter.\n"
                  "- Mehrere Größen nie in einer Zeile trennen (nicht „A = 1 / B = 2“).\n"
                  "- Keine Wörter wie „unendlich“ oder „gesucht“. Fehlt eine Zahl, schreibe nur: RECHNUNG: KEINE\n"
                  "- RECHNUNG: nur Namen aus WERTE, Zahlen und + - * / ** ( ) sqrt() pi; Malzeichen immer ausschreiben;"
                  " Wurzel als sqrt(x), nie √; Potenzen mit **; keine Einheiten in RECHNUNG.\n"
                  "- Beispiel:\n  U = 230 V\n  n = 1500/60 1/s\n  RECHNUNG: w = 2*pi*n\n\n")
    if not fehler:
        return basis.replace("Material:\n", regeln + "Material:\n", 1)
    grund, detail = fehler
    bericht = {"wert_unlesbar": "ein Wert in WERTE war nicht lesbar", "auswertung": "eine Zeile in RECHNUNG war nicht auswertbar",
               "formatfehler": "das Format war nicht erkennbar", "literal": "das Ergebnis war nur eine hingeschriebene Zahl, nicht gerechnet",
               "dimension": "die Einheiten der Rechnung passen physikalisch nicht zusammen",
               "zwischenwert": "in RECHNUNG stand eine selbst ausgerechnete Zahl; rechne mit den Namen aus WERTE und RECHNUNG statt mit Zwischenergebnissen",
               "ergebnis_name": "der Name unter ERGEBNIS kommt in RECHNUNG nicht als berechnete Größe vor"}.get(grund, grund)
    kopf = (f"Deine erste Nachrechnung war nicht auswertbar: {bericht}"
            + (f" ({detail})" if detail else "") + ". Rechne dieselbe Aufgabe noch einmal und halte dich genau an die Schreibweise.\n\n")
    return kopf + basis.replace("Material:\n", regeln + "Material:\n", 1)


_EINHEITEN_FOLGE = re.compile(r"(?:%s)+" % rp._EINHEIT.pattern)  # "kgm" in "kgm²" = kg + m


def kopfzahlen_v3(loesung, frage):
    """Zahlen mit Einheit im ersten Satz. Nur Zahlen aus der Frage? Dann (liste, True): die Antwort wiederholt vielleicht einen
    gegebenen Wert (F61 im V12.9-Lauf: "0,02 kgm²"). Rückgabe (liste von (w, stellen, text, hat_einheit), rueckfall)."""
    eigene = _kopf_mit_einheit(loesung, frage)
    if eigene:
        return eigene, False
    text = loesung or ""
    m = rp._erster_satz_ende(text)
    kopf = rp._VERWEIS_ZAHL.sub(" ", text[:m.start()] if m else text)
    alle = []
    for z in re.finditer(r"(?<![A-Za-zÄÖÜäöüßα-ωΑ-Ω_₀-₉])\d+(?:[.,]\d+)*", kopf):
        try:
            w = abs(rp.zahl(z.group(0)))
        except ValueError:
            continue
        nach = re.match(r"\s*(%|[A-Za-zΩµμ°]+)", kopf[z.end():])
        hat = bool(nach) and (nach.group(1) == "%" or bool(_EINHEITEN_FOLGE.fullmatch(nach.group(1))))
        if hat:
            alle.append((w, rp._stellen(z.group(0)), z.group(0), True))
    return (alle, True) if len(alle) == 1 else ([], False)  # genau eine Zahl mit Einheit: eindeutig die Antwort


def vergleiche_v3(loesung, frage, res):
    """Wie vergleiche_v2, mit Rückfall auf Zahlen aus der Frage (siehe kopfzahlen_v3)."""
    if not res.get("ergebnisse"):
        return []
    kopf, rueckfall = kopfzahlen_v3(loesung, frage)
    if not kopf:
        return []
    if not rueckfall:
        return vergleiche_v2(loesung, frage, res)
    werte = [abs(w) for _, w in res["ergebnisse"]]
    w, st, t, _ = kopf[0]
    if any(rp._passt(k, w, st) for e in werte for k in (e, e * 100, e / 100)):
        return []
    return [{"art": "baustein", "ausdruck": res.get("rechnung", ""), "gerechnet": werte[0], "angegeben": w,
             "satz": (loesung or "")[:200],
             "text": (f"Die unabhängige Python-Nachrechnung ({res.get('formel', '').strip() or 'Formel'}) ergibt "
                      f"{ergebnis_text(res)}, die Lösung nennt nur den gegebenen Wert {t}")}]


# ---------------------------------------------------------------------------------------------------------
# RB-v5 (V13.4, 26 Oct 2026; gehört zu RP-v10)
# ---------------------------------------------------------------------------------------------------------
# Anlass: Rechenvarianten-Test RV-v1 (26 Oct 2026, 22 Buchaufgaben mit geänderten Zahlen): die Nachrechnung war in 14 von
# 22 Fragen "nicht verwertbar: auswertung", auch nach dem Retry. Offline nachgestellte Ursachen (Schreibweisen, die das
# Modell nutzt, die die Auswertung aber nicht las):
#   1. Kettenzeilen "P2 = P1 * η = 16000" (Ergebnis hinter dem Ausdruck) -> nur der Ausdruck zählt.
#   2. Namen mit "ϑ", "ϕ", "µ": Python liest Namen in NFKC-Form (ϑ -> θ, µ -> μ), die Werte standen unter dem Originalnamen.
#   3. "math.sqrt", "np.sqrt", LaTeX (\sqrt{x}, \frac{a}{b}, \cdot), "≈".
#   4. Prozentwerte "η = 90 %" wurden als 90 gerechnet (still falsch, nicht nur nicht verwertbar).
#   5. Winkel in Grad (cos(36,87) als Bogenmaß gerechnet, still falsch).
# Zusätzlich: Rohtexte der Nachrechnung werden für das Protokoll aufbewahrt (letzte_rohtexte), damit ein weiterer
# Ausfall diagnostizierbar ist.
import unicodedata

RB_VERSION_5 = "RB-v5"
letzte_rohtexte = []  # Rohantworten der letzten Nachrechnungs-Aufrufe (Protokoll; rag_pipeline leert und liest)


def _nfkc(t):
    return unicodedata.normalize("NFKC", t or "")


def _latex_weg(t):
    t = t.replace("\\left", "").replace("\\right", "").replace("\\,", " ").replace("\\cdot", "*").replace("\\times", "*")
    t = t.replace("\\pi", "pi").replace("\\eta", "η").replace("\\varphi", "φ").replace("\\phi", "φ").replace("$", "")
    for _ in range(3):  # verschachtelte Brüche/Wurzeln von innen nach außen
        t = re.sub(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"((\1)/(\2))", t)
        t = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"sqrt(\1)", t)
    t = re.sub(r"\\text\s*\{[^{}]*\}", "", t)
    return t.replace("{", "(").replace("}", ")")


def normiere_v5(ausdruck):
    """Ausdruck vor RB-v3-Normierung: NFKC, LaTeX, Modulpräfixe, arccos/arcsin/arctan, Grad-Literale in Winkelfunktionen."""
    t = _latex_weg(_nfkc(ausdruck))
    t = re.sub(r"\b(?:math|np|numpy)\s*\.\s*", "", t)
    t = re.sub(r"\barc(sin|cos|tan)\b", r"a\1", t)
    t = re.sub(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*°(?![CF])", r"radians(\1)", t)  # cos(36,87°), nicht 15 °C
    return t.replace("≈", "=")


def _ausdruck_vor_gleich(text):
    """'P1 * η = 16000' -> 'P1 * η' (Kettenzeile); ein einzelner Ausdruck bleibt unverändert."""
    return re.split(r"\s*=\s*", text, 1)[0].strip()


def _wert_v5(text):
    """WERTE-Zeile: Prozent -> /100 (nur wenn die Einheit genau % ist), Grad-Zeichen entfällt (Winkel bleibt in Grad;
    die Winkelfunktionen unten erkennen Grad an der Größe)."""
    t = _ausdruck_vor_gleich(normiere_v5(text)).replace("radians(", "(")
    m = re.match(r"\s*([-+]?\d+(?:[.,]\d+)?)\s*%\s*$", t)
    if m:
        return f"({m.group(1)}/100)"
    return re.sub(r"\s*(?:°(?![CF])|Grad\b)\s*$", "", t)


def _grad_bewusst(f):
    """Winkelfunktion, die Argumente > 2π als Grad liest: im technischen Rechnen ist cos(36,87) nie Bogenmaß gemeint."""
    return lambda x: f(math.radians(x)) if abs(x) > 2 * math.pi + 1e-9 else f(x)


_FUNKTIONEN_V5 = {**_FUNKTIONEN, "sin": _grad_bewusst(math.sin), "cos": _grad_bewusst(math.cos),
                  "tan": _grad_bewusst(math.tan)}


def parse_v5(roh):
    """parse_v2 auf normierten Rohtext; Namen und Ausdrücke in NFKC, Kettenzeilen gekürzt, Prozent- und Gradwerte gelesen."""
    letzte_rohtexte.append((roh or "")[:2500])
    roh_n = _latex_weg(_nfkc(roh or "")).replace("≈", "=")
    p = parse_v2(roh_n)
    if p is None or p["rechnung"] == "KEINE":
        return p
    p["werte"] = {_nfkc(n): _wert_v5(t) for n, t in p["werte"].items()}
    p["schritte"] = [(_nfkc(n), _ausdruck_vor_gleich(normiere_v5(a))) for n, a in p["schritte"]]
    p["ergebnis_namen"] = [_nfkc(n) for n in p["ergebnis_namen"]]
    p["rechnung"] = "; ".join(f"{n} = {a}" for n, a in p["schritte"])
    return p


def rechne_v5(parsed, frage, kontext):
    """rechne_v2 mit gradbewussten Winkelfunktionen."""
    global _FUNKTIONEN
    alt, _FUNKTIONEN = _FUNKTIONEN, _FUNKTIONEN_V5
    try:
        return rechne_v2(parsed, frage, kontext)
    finally:
        _FUNKTIONEN = alt


def pruefloesung_v5(res, urspruenglich=""):
    """Wie pruefloesung, für eine Nachrechnung, deren Formel NICHT im Lernmaterial belegt ist, die aber von einer zweiten,
    anders formulierten Nachrechnung bestätigt wurde (RP-v10). Der Vermerk sagt das ausdrücklich."""
    text = pruefloesung(res, urspruenglich)
    return text.replace("gezeigt wird die Nachrechnung (Formel aus dem Lernmaterial).",
                        "gezeigt wird die Nachrechnung. Ihre Formel steht nicht wörtlich im Lernmaterial; zwei unabhängige "
                        "Nachrechnungen ergaben dasselbe Ergebnis. Bitte mit dem Buch oder der Lehrkraft prüfen.")


# ---------------------------------------------------------------------------------------------------------
# RB-v6 (V13.5, 27 Oct 2026; gehört zu RP-v11)
# ---------------------------------------------------------------------------------------------------------
# Anlass: Rohtexte der Nachrechnung aus dem RV-Lauf V134 (erstmals protokolliert). Die Ausfälle hatten andere Ursachen als
# vermutet: (1) alle Zuweisungen in EINER Zeile, getrennt durch ";", ", " oder " / " (" / " stammt aus dem Formatbeispiel des
# RB-v3-Prompts, das Modell übernimmt es), (2) die ganze Rechnung unter WERTE, RECHNUNG fehlt, (3) Einheiten mitten in RECHNUNG
# ("1,5 mm + 2 * 0,25 mm", "0,5 Ω·mm²/m * l / A"), (4) Umformungsschritte ("R_V = eta*(Ri + RL + R_V)") vor der eigentlichen
# Formel, (5) "… -> Korrektur: x = …", (6) Formelsymbol als Wert ("M_K = M_K") bei Verhältnisaufgaben. Außerdem: eine bereits
# berechnete Größe, die das Modell als Zahl wiederholt, erscheint nicht mehr in der angezeigten Rechnung (N100 F15: "n = 19,298").
RB_VERSION_6 = "RB-v6"
_PRUEFE_LITERALE = True  # RB-v7 schaltet die Belegprüfung für die umgerechneten Werte ab (geprüft wird die Originallesung)
_KOPF_V6 = re.compile(r"(?im)^[ \t*_#-]*(FORMEL|WERTE|RECHNUNG|ERGEBNIS|EINHEIT|QUELLE)[ \t*_]*:")
_NAME_V6 = r"[A-Za-zα-ωΑ-Ω_][A-Za-z0-9α-ωΑ-Ω_]*"
_TRENNER_V6 = re.compile(rf"\s*(?:;|,\s+|\s/\s|->\s*(?:Korrektur\s*:)?|\bKorrektur\s*:)\s*(?={_NAME_V6}\s*=)")


def _abschnitte_v6(roh):
    teile, treffer = {}, list(_KOPF_V6.finditer(roh))
    for i, m in enumerate(treffer):
        ende = treffer[i + 1].start() if i + 1 < len(treffer) else len(roh)
        teile.setdefault(m.group(1).upper(), roh[m.end():ende].strip().strip("`").strip())
    return teile


def _zuweisungen_v6(block, rechnung):
    """Block -> [(name, ausdruck)]. Trennt Zeilen und mehrere Zuweisungen in einer Zeile. In RECHNUNG wird " / " nur getrennt,
    wenn dahinter keine reine Zahl folgt ("x = b / c = 5" bleibt eine Kettenzeile)."""
    out = []
    for zeile in (block or "").splitlines():
        zeile = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", zeile.strip().strip("`"))
        stuecke, pos = [], 0
        for m in _TRENNER_V6.finditer(zeile):
            if rechnung and m.group(0).strip() == "/" and re.match(
                    rf"{_NAME_V6}\s*=\s*[-+]?\d+(?:[.,]\d+)?(?:\s*[A-Za-zΩ°%][^\s]*)?\s*(?:$|(?:;|,\s+|\s/\s)\s*{_NAME_V6}\s*=)",
                    zeile[m.end():]):
                continue
            stuecke.append(zeile[pos:m.start()]); pos = m.end()
        stuecke.append(zeile[pos:])
        for st in stuecke:
            st = re.sub(r"^\s*Korrektur\s*:\s*", "", st.strip().rstrip(",;"))
            z = re.match(rf"({_NAME_V6})\s*=\s*(.+)$", st)
            if z:
                out.append((z.group(1), z.group(2).strip()))
    return out


def _ist_einheit_v6(tok):
    teile = [re.sub(r"[\^⁰¹²³⁴⁵⁶⁷⁸⁹⁻\-0-9]+$", "", x) for x in re.split(r"[·*/]", tok) if x]
    return bool(teile) and all(x and (x in ("€", "%", "Ω", "°C") or rp._EINHEIT.fullmatch(x)) for x in teile)


def _ohne_einheiten_v6(ausdruck, namen):
    """'1,5 mm + 2 * 0,25 mm' -> '1,5 + 2 * 0,25'; '0,5 Ω·mm²/m * l / A' -> '0,5 * l / A'. Nur Einheitenwörter direkt nach einer
    Zahl oder Klammer, die keine bekannten Namen sind."""
    def ersetze(m):
        tok, rest = m.group(2), ""
        while tok and tok[-1] in ")],;":
            rest, tok = tok[-1] + rest, tok[:-1]
        if tok in namen or not _ist_einheit_v6(tok):
            return m.group(0)
        return m.group(1) + rest
    return re.sub(r"((?:\d|\))\s*)(?<![A-Za-z_])([A-Za-zΩµμ°€%][^\s+\-*()]*(?:[*·/][A-Za-zΩµμ°][^\s+\-*()]*)*[)\],;]*)(?=\s|$|[*/+\-])",
                  ersetze, ausdruck)


def parse_v6(roh):
    """Wie parse_v5, liest aber die Formen (1)–(6) oben. Rückgabe wie parse_v2 oder None (Formatfehler)."""
    letzte_rohtexte.append((roh or "")[:2500])
    roh_n = _latex_weg(_nfkc(roh or "")).replace("≈", "=")
    a = _abschnitte_v6(roh_n)
    if "RECHNUNG" in a and a["RECHNUNG"].upper().startswith("KEINE"):
        return {"rechnung": "KEINE", "werte": {}, "schritte": [], "ergebnis_namen": [], "formel": "", "quelle": "", "einheit": ""}
    werte_roh = _zuweisungen_v6(a.get("WERTE", ""), False)
    schritte_roh = _zuweisungen_v6(a.get("RECHNUNG", ""), True)
    alle_namen = {_nfkc(n) for n, _ in werte_roh + schritte_roh}
    werte, schritte = {}, []
    for n, t in werte_roh:
        n = _nfkc(n)
        if re.fullmatch(rf"\s*{re.escape(n)}\s*", t):
            werte[n] = "1"  # (6) Formelsymbol als Wert: kürzt sich in Verhältnissen heraus
            continue
        ausdruck = _ohne_einheiten_v6(normiere_v5(t), alle_namen)
        if not schritte_roh and not re.fullmatch(r"\s*[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?\s*", _wert_v5(ausdruck)):
            schritte.append((n, _ausdruck_vor_gleich(ausdruck)))  # (2) Rechnung unter WERTE
        else:
            werte[n] = _wert_v5(ausdruck)
    for n, t in schritte_roh:
        schritte.append((_nfkc(n), _ausdruck_vor_gleich(_ohne_einheiten_v6(normiere_v5(t), alle_namen))))
    if not schritte:
        return None
    gesucht = [_nfkc(x.strip()) for x in re.split(r"[,;]|\bund\b", a.get("ERGEBNIS", "").splitlines()[0] if a.get("ERGEBNIS") else "")
               if x.strip()]
    namen = [n for n in gesucht if any(n == s[0] for s in schritte)]
    ergebnis_fehlt = ""
    if not namen and gesucht and V18_E:
        # V18-E: ERGEBNIS auch gegen die linke Seite der RECHNUNG-Zeilen prüfen ("M_stR / M_st = …" ergibt den Namen M_st)
        kurz = lambda x: re.sub(r"[\s_]", "", _nfkc(x))
        stepn = {s[0] for s in schritte}
        namen = [n for n in stepn if any(kurz(g) == kurz(n) for g in gesucht)][:1]  # "RV" = "R_V"
        for zeile in (a.get("RECHNUNG", "") or "").splitlines():
            if "=" not in zeile:
                continue
            links = zeile.split("=", 1)[0]
            letzter = (re.findall(_NAME_V6, _nfkc(links)) or [""])[-1]
            if letzter in stepn and any(kurz(g) == kurz(links) for g in gesucht):
                namen = [letzter]
        if not namen:
            ergebnis_fehlt = f"ERGEBNIS: {', '.join(gesucht)}"
    namen = namen or [schritte[-1][0]]
    return {"rechnung": "; ".join(f"{n} = {x}" for n, x in schritte), "werte": werte, "schritte": schritte, "_ergebnis_fehlt": ergebnis_fehlt,
            "ergebnis_namen": namen, "formel": a.get("FORMEL", "").splitlines()[0].strip() if a.get("FORMEL") else "",
            "quelle": a.get("QUELLE", "").splitlines()[0].strip()[:400] if a.get("QUELLE") else "",
            "einheit": a.get("EINHEIT", "").splitlines()[0].strip() if a.get("EINHEIT") else ""}


def rechne_v6(parsed, frage, kontext):
    """Wie rechne_v2 (gradbewusste Winkelfunktionen wie v5), zusätzlich: (4) ein nicht auswertbarer Schritt wird übersprungen, wenn
    seine Größe schon bekannt ist oder später neu berechnet wird; wiederholte Zahlen berechneter Größen fallen aus der Anzeige."""
    global _FUNKTIONEN
    if parsed is None:
        return {"ergebnis": None, "ergebnisse": [], "grund": "formatfehler"}
    if parsed["rechnung"] == "KEINE":
        return {"ergebnis": None, "ergebnisse": [], "grund": "keine_rechnung"}
    alt, _FUNKTIONEN = _FUNKTIONEN, _FUNKTIONEN_V5
    try:
        bekannt = _zahlen_in(frage) | _zahlen_in(kontext) | {round(float(c), 9) for c in ERLAUBTE_KONSTANTEN}
        namen, unleserlich = {}, {}
        for name, text in parsed["werte"].items():
            ausdruck, wert = _wert_ausdruck(text, namen)
            if wert is None:
                unleserlich[name] = text
                continue
            for lit in _literale(ausdruck):
                if _PRUEFE_LITERALE and not _belegt(float(lit), bekannt):
                    return {"ergebnis": None, "ergebnisse": [], "grund": "erfunden", "detail": f"{name} = {text}"}
            namen[name] = wert
        if parsed.get("_ergebnis_fehlt"):  # V18-E
            return {"ergebnis": None, "ergebnisse": [], "grund": "ergebnis_name", "detail": parsed["_ergebnis_fehlt"]}
        berechnet, nur_zahl, gezeigt = set(), set(), []
        schritte = _reihenfolge_v6(parsed["schritte"], namen)
        for i, (name, ausdruck) in enumerate(schritte):
            ausdruck_ohne, wert = _ohne_einheit(ausdruck, namen)
            ist_literal = wert is not None and bool(re.fullmatch(r"\s*[-+]?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?\s*", ausdruck_ohne))
            if V18_D and _PRUEFE_LITERALE and not ist_literal and ausdruck_ohne and name not in berechnet:
                # nur Schritte, die eine Größe erstmals berechnen (eine spätere Wiederholung wie "n = 19.298 s^-1" zählt nicht)
                bisher = [v for v in namen.values() if isinstance(v, (int, float))]
                for lit in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", re.sub(r"(\d),(\d)", r"\1.\2", ausdruck_ohne)):
                    x = float(lit)
                    if (x in _STRUKTURZAHLEN_V18 or _belegt(x, bekannt)
                            or any(abs(x - v) <= 0.005 * max(abs(v), 1e-12) for v in bisher)):
                        continue
                    return {"ergebnis": None, "ergebnisse": [], "grund": "zwischenwert", "detail": f"{name} = {ausdruck} (Zahl {lit})"}
            if ist_literal and name in berechnet:
                continue  # wiederholte Zahl einer berechneten Größe: weder rechnen noch anzeigen (F15)
            if wert is None:
                if name in namen or any(n2 == name for n2, _ in schritte[i + 1:]):
                    continue  # (4) Umformungsschritt
                fehlt = [n for n in unleserlich if re.search(rf"(?<![A-Za-z0-9_]){re.escape(n)}(?![A-Za-z0-9_])", ausdruck)]
                if fehlt:
                    return {"ergebnis": None, "ergebnisse": [], "grund": "wert_unlesbar", "detail": f"{fehlt[0]} = {unleserlich[fehlt[0]]}"}
                return {"ergebnis": None, "ergebnisse": [], "grund": "auswertung", "detail": f"{name} = {ausdruck}"}
            namen[name] = wert
            gezeigt.append((name, ausdruck))
            if ist_literal:
                nur_zahl.add(name)
            else:
                berechnet.add(name)
                nur_zahl.discard(name)
        if any(n in nur_zahl for n in parsed["ergebnis_namen"]):
            return {"ergebnis": None, "ergebnisse": [], "grund": "literal", "detail": parsed["rechnung"]}
        ergebnisse = [(n, namen[n]) for n in parsed["ergebnis_namen"] if n in namen]
        if not ergebnisse:
            return {"ergebnis": None, "ergebnisse": [], "grund": "auswertung", "detail": parsed["rechnung"]}
        return {"ergebnis": ergebnisse[0][1], "ergebnisse": ergebnisse, "einheit": parsed["einheit"], "formel": parsed["formel"],
                "quelle": parsed["quelle"], "formel_im_material": quelle_im_material(parsed["quelle"], kontext),
                "werte": parsed["werte"], "rechnung": "; ".join(f"{n} = {a}" for n, a in gezeigt), "schritte": gezeigt, "grund": ""}
    finally:
        _FUNKTIONEN = alt


def _reihenfolge_v6(schritte, namen):
    """Schritte, die eine erst später berechnete Größe brauchen, rücken hinter deren Berechnung (RV-v1 R01: "P_zu2 = P_ab2 / eta2"
    vor "P_ab2 = P_ab1"). Sonst bleibt die Reihenfolge."""
    definiert = {n for n, _ in schritte}
    rest, out, bekannt = list(schritte), [], set(namen) | set(_KONSTANTEN)
    for _ in range(len(schritte) + 1):
        weiter = []
        for n, a in rest:
            braucht = set(re.findall(rf"(?<![\w.]){_NAME_V6}(?!\s*\()", a)) & definiert
            if braucht <= bekannt | {n} or not (braucht - bekannt - {n}) & {m for m, _ in rest if m != n}:
                out.append((n, a)); bekannt.add(n)
            else:
                weiter.append((n, a))
        if not weiter or len(weiter) == len(rest):
            return out + weiter
        rest = weiter
    return out + rest


def _norm_einheit_v6(e):
    e = (e or "").strip().replace("Ohm", "Ω").replace("µ", "μ").replace(" ", "").replace("*", "·")
    return e.rstrip(".,;")


def vergleiche_v6(loesung, frage, res):
    """Wie vergleiche_v3; zusätzlich: steht hinter der Zahl im ersten Satz dieselbe Einheit wie beim Ergebnis der Nachrechnung,
    gilt kein Vorsatz-Faktor 10³ (RV-v1 Lauf V134 R14: "300 W" statt 0,3 W galt als passend)."""
    b = vergleiche_v3(loesung, frage, res)
    if b or not res.get("ergebnisse"):
        return b
    einheiten = _einheiten_liste(res)
    if not any(einheiten):
        return []
    text = loesung or ""
    m = rp._erster_satz_ende(text)
    kopf = rp._VERWEIS_ZAHL.sub(" ", text[:m.start()] if m else text)
    aus_frage = {w for w, _, _ in rp._zahlen_mit_stellen(frage)}
    falsch = []
    for z in re.finditer(r"(?<![A-Za-zÄÖÜäöüßα-ωΑ-Ω_₀-₉])\d+(?:[.,]\d+)*", kopf):
        try:
            w = abs(rp.zahl(z.group(0)))
        except ValueError:
            continue
        nach = re.match(r"\s*([A-Za-zΩµμ°%][A-Za-zΩµμ°²³⁻¹/·]*)", kopf[z.end():])
        if w in aus_frage or not nach:
            continue
        eh = _norm_einheit_v6(nach.group(1))
        gleiche = [abs(r) for (_, r), e in zip(res["ergebnisse"], einheiten) if e and _norm_einheit_v6(e) == eh]
        if not gleiche:
            continue
        st = rp._stellen(z.group(0))
        if any(rp._passt(r, w, st) for r in gleiche) and not any(
                abs(r - w) <= max(0.5 * 10 ** (-st), 0.006 * abs(w)) for r in gleiche):
            falsch.append(z.group(0) + " " + nach.group(1))
    if not falsch:
        return []
    return [{"art": "baustein", "ausdruck": res.get("rechnung", ""), "gerechnet": abs(res["ergebnisse"][0][1]), "angegeben": None,
             "satz": text[:200], "text": (f"Die unabhängige Python-Nachrechnung ({res.get('formel', '').strip() or 'Formel'}) ergibt "
                                         f"{ergebnis_text(res)}, die Lösung nennt {' / '.join(falsch[:3])}")}]



# RB-v7 (V15, 27 Oct 2026): Einheiten umrechnen statt streichen. Läufe V134/V14C/V14D: die Python-Nachrechnung rechnete richtig,
# lag aber um Faktoren 10³ daneben, weil Einheiten nur gestrichen wurden (R01: MWh · €/kWh; R02: Längen in mm mit Ω·mm²/m).
# RB-v7 rechnet jede Zahl mit Einheit in WERTE und RECHNUNG in die Grundeinheit ohne Vorsilbe um (37 mm -> 0,037; 0,08 €/kWh ->
# 0,08/3,6·10⁶; 900 min⁻¹ -> 15), rechnet damit und gibt die Ergebnisse in der unter EINHEIT genannten Einheit zurück.
# Nicht umgerechnet wird bei Zahlenwertgleichungen: enthält ein Rechenschritt eine Zahl, die weder in der Frage steht noch 1, 2, 3, 4
# oder 0,5 ist (z. B. 60, 1000, 9550), erwartet die Formel bestimmte Einheiten -> Lesung wie RB-v6. Unbekannte Einheiten (°C, Grad)
# werden wie bisher gestrichen. Die Belegprüfung (erfundene Zahlen) läuft auf der Originallesung.
RB_VERSION_7 = "RB-v7"
# RB-v8 (V17b, 28 Oct 2026) = RB-v7 + Dimensionsprüfung (dimensionspruefung.py, über rag_pipeline) + zwei Lesekorrekturen (Schalter RB_V8, gesetzt von rag_pipeline bei LERNASSISTENT_RB=RB-v8):
# (1) Konstanten (pi) gehen vor Einträgen unter WERTE: "pi = pi" wurde als pi = 1 gelesen (RV-v2 R11, Bestätigung 125000 Hz statt
# 39,79 Hz). (2) Selbst umgerechnete Zahl ("L = 20/1000 H") wird auch dann nicht noch einmal umgerechnet, wenn die Einheit hinter der
# Umrechnungszahl schon gestrichen ist ("20/1000.0"); vorher wurde 20 mit dem Faktor aus der Frage (20 mH) zu 0,02/1000.
RB_V8 = False
# V18 (28 Oct 2026): LERNASSISTENT_V18 enthält "A" (strengere Schreibweise der Bestätigung) und/oder "B" (Formelbeleg
# bei Kürzung und kurzen Formeln). Standard: aus.
_V18 = __import__("os").environ.get("LERNASSISTENT_V18", "")
V18_A = "A" in _V18
V18_B = "B" in _V18
V18_D = "D" in _V18  # D: Zahlen in RECHNUNG müssen aus Frage/Material stammen oder vorher berechnet sein
V18_E = "E" in _V18  # E: ERGEBNIS muss eine berechnete Größe nennen (kein stiller Rückfall auf den letzten Schritt)
_STRUKTURZAHLEN_V18 = {0.25, 0.5, 1.5, 1e9, 1e-9}
_PRAEFIX_V7 = {"T": 1e12, "G": 1e9, "M": 1e6, "k": 1e3, "h": 1e2, "d": 1e-1, "c": 1e-2, "m": 1e-3, "μ": 1e-6, "µ": 1e-6,
               "u": 1e-6, "n": 1e-9, "p": 1e-12}
_BASIS_V7 = {"m": 1.0, "g": 1e-3, "s": 1.0, "A": 1.0, "V": 1.0, "W": 1.0, "Ω": 1.0, "N": 1.0, "J": 1.0, "Hz": 1.0, "H": 1.0,
             "F": 1.0, "C": 1.0, "T": 1.0, "Wb": 1.0, "Pa": 1.0, "K": 1.0, "VA": 1.0, "var": 1.0, "€": 1.0, "bar": 1e5,
             "l": 1e-3, "L": 1e-3, "Wh": 3600.0, "Ah": 3600.0, "Ws": 1.0, "Nm": 1.0, "VAh": 3600.0, "Ohm": 1.0}
_DIREKT_V7 = {"min": 60.0, "h": 3600.0, "%": 0.01, "rpm": 1 / 60, "Nmm": 1e-3, "Ncm": 1e-2, "kNm": 1e3, "Mio€": 1e6,
              "Mio": 1e6, "Mrd€": 1e9, "Mrd": 1e9, "t": None, "°C": None, "°F": None, "°": None, "Grad": None, "dB": None}


def _atom_faktor_v7(atom):
    """'mm2' -> 1e-6, 'min-1' -> 1/60, 'kWh' -> 3,6e6, 'Ω' -> 1. Unbekannt -> None."""
    m = re.fullmatch(r"(.+?)(?:\^|\*\*)?\(?([-−]?\d)?\)?", atom)
    kern, hoch = (m.group(1), m.group(2)) if m else (atom, None)
    if kern and kern[-1:] in "-−" and hoch is None:
        return None
    hoch = int((hoch or "1").replace("−", "-"))
    if kern in _DIREKT_V7:
        f = _DIREKT_V7[kern]
    elif kern in _BASIS_V7:
        f = _BASIS_V7[kern]
    elif len(kern) > 1 and kern[0] in _PRAEFIX_V7 and kern[1:] in _BASIS_V7:
        f = _PRAEFIX_V7[kern[0]] * _BASIS_V7[kern[1:]]
    else:
        f = _zusammengeschrieben_v7(kern)  # "Vs", "Am", "kgm": Einheiten ohne Malzeichen
    return None if f is None else f ** hoch


def _zusammengeschrieben_v7(kern):
    """'Vs' -> 1, 'Am' -> 1, 'kgm' -> 1, 'kWh' über Wh. Zerlegung in 2–3 bekannte Einheiten (ohne Vorsilben außer k bei kg)."""
    bekannt = sorted(set(_BASIS_V7) | {"kg"}, key=len, reverse=True)

    def zerlege(rest, tiefe):
        if not rest:
            return 1.0
        if tiefe == 0:
            return None
        for b in bekannt:
            if rest.startswith(b):
                r = zerlege(rest[len(b):], tiefe - 1)
                if r is not None:
                    return r * (1.0 if b == "kg" else _BASIS_V7[b])
        return None
    return zerlege(kern, 3) if len(kern) >= 2 else None


def einheit_faktor_v7(einheit):
    """Faktor zur Grundeinheit ohne Vorsilbe: 'Ω·mm²/m' -> 1e-6, '€/kWh' -> 1/3,6e6, '1/min' -> 1/60, 'Mio €' -> 1e6.
    None = unbekannt oder nicht umzurechnen (°C, Grad)."""
    e = _nfkc(einheit or "").strip().rstrip(".,;:)").replace(" ", "").replace("Mio.", "Mio").replace("Mrd.", "Mrd")
    e = e.replace("U/min", "rpm").replace("1/min", "min-1").replace("1/s", "s-1").replace("*", "·").replace("×", "·")
    if not e:
        return None
    if e in _DIREKT_V7:
        return _DIREKT_V7[e]
    zaehler, _, nenner = e.partition("/")
    if nenner or "·" in e:
        e_ = e.replace("°C", "K")  # in zusammengesetzten Einheiten ist °C eine Temperaturdifferenz (J/(°C·kg))
        zaehler, _, nenner = e_.partition("/")
    f = 1.0
    for teil, vz in ((zaehler, 1), (nenner, -1)):
        for atom in [x for x in teil.replace("(", "").replace(")", "").split("·") if x]:
            if atom == "1":
                continue
            a = _atom_faktor_v7(atom)
            if a is None:
                return None
            f *= a ** vz
    return f


_EINHEIT_V7 = r"(?:Mio\.?\s*€|Mrd\.?\s*€|[A-Za-zΩµμ°€%][^\s+*()=,;]*?(?:[·/](?:\([A-Za-zΩµμ°·*]+\)|[A-Za-zΩµμ°€1][^\s+*()=,;]*?))*)"
_ZAHL_EINHEIT_V7 = re.compile(r"(?<![\w.,])(\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?)[ \t]*(" + _EINHEIT_V7 + r")(?=[\s)\],;=]|$|\*\*|[*+\-](?!\d))")


def _si_v7(text, namen, nur_entfernen=False):
    """Zahl + Einheit -> Zahl in der Grundeinheit (nur_entfernen: Einheit nur streichen, Faktor 1). Rückgabe (text, anzahl)."""
    n = 0

    def ersetze(m):
        nonlocal n
        tok = m.group(2)
        if tok in namen or re.fullmatch(r"[A-Za-z_]\w*", tok) and tok in namen:
            return m.group(0)
        f = einheit_faktor_v7(tok)
        if f is None:
            return m.group(0)
        wert = float(m.group(1).replace(",", "."))
        if nur_entfernen:
            f = 1.0
        n += 1  # auch Faktor 1 zählt: die Einheit ist danach sicher entfernt ("Vs/(Am)" war für RB-v6 unlesbar)
        return repr(wert * f)
    return _ZAHL_EINHEIT_V7.sub(ersetze, text), n


def _gleiche_zahl_v7(block, zuordnung):
    """Zahl ohne Einheit in RECHNUNG, die als Zahl mit Einheit unter WERTE steht (R02: "A = 1,5**2 * pi / 4" bei "d = 1,5 mm"),
    erhält denselben Faktor. Nicht für Hochzahlen und nicht für bereits umgerechnete Zahlen (repr mit Punkt und vielen Stellen)."""
    umrechnung = r"(?:10|60|100|1000|3600|1e-?\d+|10\s*(?:\*\*|\^)\s*\(?-?\d+\)?)"
    if RB_V8:  # V17: auch "1000.0" (Einheit dahinter schon gestrichen) ist eine Umrechnungszahl
        umrechnung = r"(?:(?:10|60|100|1000|3600)(?:\.0+)?|1e-?\d+|10\s*(?:\*\*|\^)\s*\(?-?\d+\)?)"

    def ersetze(m):
        w = round(float(m.group(1).replace(",", ".")), 9)
        f = zuordnung.get(w)
        vor, nach = block[max(0, m.start() - 12):m.start()], block[m.end():m.end() + 14]
        if re.match(rf"\s*[*/]\s*{umrechnung}(?![\d.,])", nach) or re.search(rf"(?<![\d.,]){umrechnung}\s*[*/]\s*$", vor):
            return m.group(0)  # das Modell rechnet hier selbst um ("70/100", "900/60", "37/1000")
        return repr(w * f) if f else m.group(0)
    return re.sub(r"(?<![\w.,^])(?<!\*\*)(?<!\*\*\s)(\d+(?:[.,]\d+)?)(?![\w]|[.,]\d|\s*[A-Za-zΩµμ°€%])", ersetze, block)


def _zuordnung_v7(text):
    """Zahl mit Einheit (Faktor ≠ 1) im Text -> Faktor; mehrdeutige Zahlen (verschiedene Faktoren) -> None."""
    out = {}
    for m in _ZAHL_EINHEIT_V7.finditer(_nfkc(text or "")):
        f = einheit_faktor_v7(m.group(2))
        if f is not None and abs(f - 1.0) > 1e-12:
            w = round(float(m.group(1).replace(",", ".")), 9)
            out[w] = f if out.get(w, f) == f else None
    return out


def parse_v7(roh):
    """Wie parse_v6; der Rohtext bleibt für die Lesung in Grundeinheiten (rechne_v7, dort mit der Frage) erhalten."""
    p6 = parse_v6(roh)
    if p6 is None or p6.get("rechnung") == "KEINE":
        return p6
    return dict(p6, _roh=roh)


def _si_lesung_v7(roh, frage, nur_entfernen=False):
    """Lesung mit Werten in Grundeinheiten oder None (nichts umzurechnen / nicht lesbar). Zahlen ohne Einheit, die in WERTE
    oder in der Frage mit Einheit stehen, erhalten deren Faktor (R02: "1,5 + 2*0,25 mm", "A = 1,5**2 * pi / 4")."""
    text = _latex_weg(_nfkc(roh or "")).replace("≈", "=")
    a = _abschnitte_v6(text)
    namen = {_nfkc(n) for n, _ in _zuweisungen_v6(a.get("WERTE", ""), False) + _zuweisungen_v6(a.get("RECHNUNG", ""), True)}
    zuordnung = {} if nur_entfernen else {k: v for k, v in _zuordnung_v7(frage).items()}
    if not nur_entfernen:
        zuordnung.update(_zuordnung_v7(a.get("WERTE", "")))
    zuordnung = {k: v for k, v in zuordnung.items() if v}
    teile, gesamt = list(_KOPF_V6.finditer(text)), 0
    neu, pos = [], 0
    for i, m_kopf in enumerate(teile):
        ende = teile[i + 1].start() if i + 1 < len(teile) else len(text)
        neu.append(text[pos:m_kopf.end()])
        block = text[m_kopf.end():ende]
        if m_kopf.group(1).upper() in ("WERTE", "RECHNUNG"):
            block, k = _si_v7(block, namen, nur_entfernen)
            gesamt += k
            if zuordnung:
                block = _gleiche_zahl_v7(block, zuordnung)
        neu.append(block)
        pos = ende
    neu.append(text[pos:])
    if not gesamt:
        return None
    anzahl = len(letzte_rohtexte)
    p7 = parse_v6("".join(neu))
    del letzte_rohtexte[anzahl:]
    return p7


def _zahlenwertgleichung_v7(parsed, frage):
    aus_frage = _zahlen_in(frage)
    for _, ausdruck in parsed.get("schritte", []):
        for lit in _literale(re.sub(r"(?<=\d),(?=\d)", ".", ausdruck)):
            w = round(float(lit), 9)
            if w in (0.5, 1.0, 2.0, 3.0, 4.0) or w in aus_frage:
                continue
            return True
    return False


def _ergebnis_namen_roh_v7(parsed):
    """Alle unter ERGEBNIS genannten Namen (auch nicht berechnete), für die Zuordnung der Einheiten."""
    a = _abschnitte_v6(_latex_weg(_nfkc(parsed.get("_roh") or "")))
    zeile = a.get("ERGEBNIS", "").splitlines()[0] if a.get("ERGEBNIS") else ""
    return [_nfkc(x.strip()) for x in re.split(r"[,;]|\bund\b", zeile) if x.strip()]


def rechne_v7(parsed, frage, kontext):
    """rechne_v6 mit Werten in Grundeinheiten; Ergebnisse in der unter EINHEIT genannten Einheit. Fällt auf rechne_v6 zurück,
    wenn nichts umzurechnen ist, die Rechnung eine Zahlenwertgleichung ist, die Originallesung Zahlen erfindet oder die
    umgerechnete Rechnung scheitert."""
    global _PRUEFE_LITERALE
    r6 = rechne_v6(parsed, frage, kontext)
    if not parsed or not parsed.get("_roh") or r6.get("grund") in ("erfunden", "zwischenwert", "ergebnis_name"):
        return r6
    if _zahlenwertgleichung_v7(parsed, frage):
        # Zahlenwertgleichung: Werte bleiben in den Einheiten des Modells, Einheiten werden nur sauber gestrichen
        # ("n = 19.298 s^-1" wurde von RB-v6 als "19.298 s - 1" gerechnet)
        p0 = _si_lesung_v7(parsed["_roh"], frage, nur_entfernen=True)
        if not p0:
            return r6
        r0 = rechne_v6(p0, frage, kontext)
        return dict(r0, formel=parsed.get("formel", ""), quelle=parsed.get("quelle", ""), werte=parsed.get("werte", {}),
                    formel_im_material=quelle_im_material(parsed.get("quelle", ""), kontext)) if r0.get("ergebnisse") else r6
    p7 = _si_lesung_v7(parsed["_roh"], frage)
    if not p7:
        return r6
    alt, _PRUEFE_LITERALE = _PRUEFE_LITERALE, False
    try:
        r7 = rechne_v6(p7, frage, kontext)
    finally:
        _PRUEFE_LITERALE = alt
    if not r7.get("ergebnisse"):
        return r6
    einheiten = [e.strip() for e in re.split(r"[,;]", parsed.get("einheit") or "") if e.strip()]
    gesucht = _ergebnis_namen_roh_v7(parsed)
    if len(einheiten) == len(gesucht) and len(einheiten) != len(r7["ergebnisse"]):
        einheiten = [einheiten[gesucht.index(n)] if n in gesucht else "" for n, _ in r7["ergebnisse"]]
    elif len(einheiten) != len(r7["ergebnisse"]):
        einheiten = [""] * len(r7["ergebnisse"])
    neu = []
    for (n, w), e in zip(r7["ergebnisse"], einheiten):
        f = einheit_faktor_v7(e) if e else None
        neu.append((n, w / f if f else w))
    r7 = dict(r7, ergebnisse=neu, ergebnis=neu[0][1], einheit=parsed.get("einheit", ""), formel=parsed.get("formel", ""),
              quelle=parsed.get("quelle", ""), werte=parsed.get("werte", {}), si="ja",
              formel_im_material=quelle_im_material(parsed.get("quelle", ""), kontext))
    return r7
