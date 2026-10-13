"""
pdf_struktur.py
---------------
V7: Strukturtreue Extraktion und Chunking (claude/Entwicklung_und_Evaluation.md, V7).

1. Extraktion mit MinerU (Layout-Erkennung, Formeln als LaTeX, Tabellen strukturiert,
   Abbildungen als Bildausschnitte, Überschriften). Quelle: MinerU, eingesetzt bei
   Yu et al. (2026, SF-RAG). MinerU läuft in einer EIGENEN conda-Umgebung ("mineru"),
   damit seine Abhängigkeiten (torch, transformers) die Projektumgebung nicht verändern.
2. Chunking entlang der Dokumentstruktur statt fester Satzzahl:
   - Grenzen an Überschriften und Absätzen; jeder Chunk kennt seinen Abschnittspfad
     (SF-RAG: Yu et al., 2026).
   - Zielgröße ca. 150–300 Tokens, keine Überlappung (Bennani & Moslonka, 2026).
   - Tabellen als eigene Chunks mit Überschrift (T²-RAGBench: Strich et al., 2026).
   - Formeln bleiben als LaTeX im Text.
   - Abbildungen: eigener Chunk aus Bildunterschrift (V7a) plus optional einer
     automatischen Bildbeschreibung durch ein kleines VLM (V7b, bildbeschreibung.py;
     Saucă & Rusnac, 2026).
Alle Regeln sind dokumentunabhängig (keine Sonderfälle für ein bestimmtes Buch).
"""
import html
import json
import os
import re
import shlex
import subprocess
import unicodedata
from pathlib import Path

# Befehl für MinerU; über die Umgebungsvariable MINERU_BEFEHL änderbar.
MINERU_BEFEHL = shlex.split(os.environ.get("MINERU_BEFEHL", "conda run --no-capture-output -n mineru mineru"))
MINERU_BACKEND = "pipeline"   # Layout-Modell + OCR + Formel-/Tabellenerkennung
MINERU_SPRACHE = os.environ.get("MINERU_SPRACHE", "")  # MinerU 3.x hat kein "latin"; leer = MinerU-Standard

ZIEL_WOERTER = 200            # ~ 260 Tokens; Obergrenze pro Text-Chunk
MIN_WOERTER = 40              # kleinere Reste werden mit dem nächsten Absatz desselben Abschnitts verbunden
TABELLE_MAX_WOERTER = 300

_NUMMERIERT = re.compile(r"^\s*(\d+(?:\.\d+)*)\.?\s+\S")


# ---------------------------------------------------------------------------
# 1. Extraktion
# ---------------------------------------------------------------------------
def mineru_ausfuehren(pdf, ausgabe, methode="auto"):
    """Ruft MinerU auf. methode: auto (Textebene + Erkennung) | ocr (alles per OCR).
    Ergebnis: Ordner mit *_content_list.json, *.md und images/."""
    ausgabe = Path(ausgabe)
    ausgabe.mkdir(parents=True, exist_ok=True)
    befehl = MINERU_BEFEHL + ["-p", str(pdf), "-o", str(ausgabe), "-b", MINERU_BACKEND,
                              "-m", methode] + (["-l", MINERU_SPRACHE] if MINERU_SPRACHE else [])
    print("MinerU:", " ".join(befehl), flush=True)
    subprocess.run(befehl, check=True)
    return finde_content_list(ausgabe, Path(pdf).stem)


def finde_content_list(ausgabe, stamm=None):
    kandidaten = sorted(Path(ausgabe).rglob("*_content_list.json"))
    if stamm:
        passend = [k for k in kandidaten if k.name.startswith(stamm)]
        kandidaten = passend or kandidaten
    if not kandidaten:
        raise FileNotFoundError(f"Keine *_content_list.json unter {ausgabe}")
    return kandidaten[0]


def lade_content_list(pfad):
    pfad = Path(pfad)
    with open(pfad, encoding="utf-8") as f:
        eintraege = json.load(f)
    return bildunterschriften_zuordnen(eintraege), pfad.parent  # Bildpfade relativ zu diesem Ordner


_UNTERSCHRIFT = re.compile(r"^\s*(Abb|Bild|Fig)\.?\s?\d")


def bildunterschriften_zuordnen(eintraege):
    """MinerU erkennt Bildunterschriften nicht immer (Pilot: Abb. 2.10 und 4.44 kamen als
    normaler Text). Eine Abbildung ohne Unterschrift bekommt den nächstgelegenen Text derselben
    Seite, der mit "Abb./Bild/Fig. <Nr>" beginnt; dieser Text wird dann nicht doppelt geführt."""
    for e in eintraege:
        if not (e.get("img_path") and e.get("type") not in ("table", "equation", "text", "list")):
            continue
        if any(k.endswith("_caption") and v for k, v in e.items()):
            continue
        kandidaten = [(abs(j - eintraege.index(e)), t) for j, t in enumerate(eintraege)
                      if t.get("type") == "text" and t.get("page_idx") == e.get("page_idx")
                      and _UNTERSCHRIFT.match(t.get("text", "")) and not t.get("_als_unterschrift")]
        if kandidaten:
            _, t = min(kandidaten, key=lambda x: x[0])
            e[f"{e.get('type', 'image')}_caption"] = [t["text"]]
            t["_als_unterschrift"] = True
            t["type"] = "discarded"
    return eintraege


# ---------------------------------------------------------------------------
# 2. Bereinigung (allgemein, dokumentunabhängig)
# ---------------------------------------------------------------------------
# LaTeX -> lesbarer Text. MinerU liefert Formeln als LaTeX mit Leerzeichen zwischen allen
# Zeichen ("1 2 0 ^ { \circ }"). Für BM25, Embeddings und das Sprachmodell wird daraus
# lesbarer Text ("120°", "U₁₂", "R_thJU = 150 K/W", "√3 · 230 V"). Nur Schreibweise, kein Inhalt.
_SYMBOLE = {
    "cdot": "·", "times": "×", "div": "÷", "pm": "±", "mp": "∓", "circ": "°", "degree": "°",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠", "approx": "≈", "sim": "~",
    "equiv": "≡", "propto": "∼", "infty": "∞", "to": "→", "rightarrow": "→", "leftarrow": "←",
    "Rightarrow": "⇒", "Leftrightarrow": "⇔", "partial": "∂", "nabla": "∇", "int": "∫", "oint": "∮",
    "sum": "Σ", "prod": "Π", "cdots": "…", "ldots": "…", "dots": "…", "angle": "∠", "perp": "⊥",
    "bot": "⊥", "parallel": "∥", "prime": "′", "in": "∈", "%": "%", "$": "$", "&": "&", "#": "#",
    "{": "{", "}": "}", "_": "_",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "varepsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "vartheta": "ϑ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "varrho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "varphi": "φ", "chi": "χ", "psi": "ψ",
    "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π",
    "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω",
}
_AUSPACKEN = {"mathrm", "mathit", "mathbf", "mathsf", "mathtt", "mathcal", "mathbb", "boldsymbol",
              "text", "textrm", "textit", "textbf", "mbox", "operatorname", "underline", "overline",
              "vec", "hat", "bar", "tilde", "dot", "widehat", "overrightarrow", "displaystyle"}
_WOERTLICH = {"mathrm", "text", "textrm", "mbox", "operatorname", "mathit", "mathbf", "mathsf"}
_WEGLASSEN = {"left", "right", "big", "Big", "bigg", "Bigg", "bigl", "bigr", "Bigl", "Bigr",
              "displaystyle", "textstyle", "scriptstyle", "limits", "nolimits", "mathstrut"}
_HOCH = str.maketrans("0123456789-+", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺")
_TIEF = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _gruppe(s, i):
    """s[i] == '{' -> (Inhalt, Index nach der schließenden Klammer)."""
    tiefe, j = 0, i
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "{":
            tiefe += 1
        elif s[j] == "}":
            tiefe -= 1
            if tiefe == 0:
                return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)


def _argument(s, i):
    """Nächstes Argument ab i (Gruppe, Befehl oder einzelnes Zeichen)."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        return _gruppe(s, i)
    if s[i] == "\\":
        m = re.match(r"\\([A-Za-z]+|.)", s[i:])
        return m.group(0), i + len(m.group(0))
    return s[i], i + 1


def _einfach(t):
    return bool(re.fullmatch(r"[\wÄÖÜäöüα-ωΑ-Ωϑφ°′]+", t))


def _latex(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            m = re.match(r"\\([A-Za-z]+|.)", s[i:])
            name, i = m.group(1), i + len(m.group(0))
            if name in ("frac", "dfrac", "tfrac"):
                a, i = _argument(s, i)
                b, i = _argument(s, i)
                a, b = _latex(a).strip(), _latex(b).strip()
                out.append(f"{a if _einfach(a) else '(' + a + ')'}/{b if _einfach(b) else '(' + b + ')'}")
            elif name == "sqrt":
                n = ""
                if i < len(s) and s[i] == "[":
                    k = s.index("]", i)
                    n, i = s[i + 1:k], k + 1
                a, i = _argument(s, i)
                a = _latex(a).strip()
                wurzel = "√" if not n.strip() else f"{n.strip()}√"
                out.append(wurzel + (a if _einfach(a) else f"({a})"))
            elif name == "tag":
                a, i = _argument(s, i)
                out.append(f"   ({_latex(a).strip()})")
            elif name in ("begin", "end"):
                _, i = _argument(s, i)
                spalten = re.match(r" *\{[lcr| ]+\}", s[i:]) if name == "begin" else None
                if spalten:
                    i += len(spalten.group(0))
            elif name in _AUSPACKEN:
                a, i = _argument(s, i)
                a = _latex(a)
                if name in _WOERTLICH:  # MinerU: "m a l" -> "mal", "t h J U" -> "thJU"
                    w = a.replace("~", " ").split()
                    a = "".join(w) if len(w) > 1 and all(len(x) == 1 for x in w[:-1]) else " ".join(w)
                out.append(a.strip())
            elif name in _WEGLASSEN:
                pass
            elif name in ("quad", "qquad"):
                out.append("   ")
            elif name in (",", ";", ":", "!", " ", "enspace", "thinspace"):
                out.append(" " if name != "!" else "")
            elif name == "\\":
                out.append("; ")
            elif name in _SYMBOLE:
                out.append(_SYMBOLE[name] + (" " if name.isalpha() and len(name) > 1 and name not in ("circ", "prime", "degree") else ""))
            else:
                out.append(name)
        elif c in "^_":
            a, i = _argument(s, i + 1)
            a = _latex(a).strip().replace(" ", "")
            if c == "^":
                if a in ("°", "∘"):
                    out.append("°")
                elif re.fullmatch(r"[-+]?\d+", a):
                    out.append(a.translate(_HOCH))
                else:
                    out.append("^" + (a if len(a) == 1 else f"({a})"))
            else:
                if re.fullmatch(r"\d+", a):
                    out.append(a.translate(_TIEF))
                else:
                    out.append("_" + a)
        elif c == "{":
            a, i = _gruppe(s, i)
            out.append(_latex(a))
        elif c == "}":
            i += 1
        elif c in "~&":
            out.append(" ")
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def latex_lesbar(latex):
    t = re.sub(r"\s+", " ", _latex(latex))
    for _ in range(3):
        t = re.sub(r"(?<=\d) (?=\d)", "", t)                      # "1 2 0" -> "120"
    t = re.sub(r"(?<=\d) ?([,.]) ?(?=\d)", r"\1", t)              # "4 , 6" -> "4,6"
    t = re.sub(r" +([_^′°⁰¹²³⁴⁵⁶⁷⁸⁹⁻₀₁₂₃₄₅₆₇₈₉)])", r"\1", t)  # "U _1" -> "U_1"
    t = re.sub(r"\( +", "(", t)
    t = re.sub(r"(?<=\b[kMGmμn]) (?=Ω)", "", t)                  # "1 k Ω" -> "1 kΩ"
    t = re.sub(r"° ?C\b", "°C", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _mathe_ersetzen(text):
    text = re.sub(r"\$\$(.+?)\$\$", lambda m: " " + latex_lesbar(m.group(1)) + " ", text, flags=re.S)
    return re.sub(r"\$(.+?)\$", lambda m: latex_lesbar(m.group(1)), text, flags=re.S)


def bereinige(text):
    text = unicodedata.normalize("NFKC", text or "")
    text = re.sub(r"(?i)</?su[bp]>", "", text)                   # "2<sub>.</sub>10" -> "2.10"
    text = text.replace(",,", "„")                                # OCR: ,,Drehspannung“
    text = _mathe_ersetzen(text)
    text = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"\s+([,.;:!?])(?=\s|$)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def tabelle_als_text(html_text):
    t = html_text or ""
    t = re.sub(r"(?i)</t[dh]\s*>", " | ", t)
    t = re.sub(r"(?i)</tr\s*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t)
    zeilen = [bereinige(z).strip(" |") for z in t.splitlines()]
    return "\n".join(z for z in zeilen if z)


def _liste(wert):
    if isinstance(wert, list):
        t = " ".join(bereinige(str(w)) for w in wert if w)
    else:
        t = bereinige(str(wert)) if wert else ""
    return re.sub(r"^((?:Abb|Tab|Fig|Bild)\.? ?\d+(?:\.\d+)*)(?=[A-ZÄÖÜ])", r"\1 ", t)  # "Abb. 1.102Gefährdung"


def _woerter(t):
    return len(t.split())


# Abbildungsartige Einträge: MinerU-Versionen nennen sie unterschiedlich ("image", "chart",
# "figure" ...). Alles mit Bildpfad, das keine Tabelle/Formel ist, gilt als Abbildung.
def ist_abbildung(e):
    return bool(e.get("img_path")) and e.get("type") not in ("table", "equation", "text", "list")


def _feld(e, endung):
    """Erstes Feld, dessen Name auf endung endet (image_caption, chart_caption, img_caption ...)."""
    for k, v in e.items():
        if k.endswith(endung) and v:
            return v
    return None


def bildunterschrift(e):
    return _liste(_feld(e, "_caption"))


def bildfussnote(e):
    return _liste(_feld(e, "_footnote"))


# Satzgrenzen: nur vor Großbuchstaben, nicht nach Abkürzungen ("z. B.", "Abb.", "Gl.") oder
# Ordnungszahlen ("1."). Ohne diesen Schutz entstanden Chunks wie "Teppichboden erreicht, ...".
_ABK = {"abb", "gl", "tab", "abschn", "kap", "bzw", "ca", "evtl", "vgl", "nr", "bsp", "usw", "etc",
        "ggf", "inkl", "bzgl", "max", "min", "dr", "prof", "dipl", "ing", "hrsg", "aufl", "bd",
        "st", "jh", "mio", "mrd", "allg", "einschl", "u.a", "z.b", "d.h", "s.o", "s.u", "o.ä"}


def _saetze(text):
    teile = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„\"(])", text)
    saetze = []
    for t in teile:
        if saetze:
            letztes = saetze[-1].split()[-1].rstrip(".").lower() if saetze[-1].split() else ""
            if (len(letztes) <= 1 or letztes in _ABK or re.fullmatch(r"\d+", letztes)
                    or not saetze[-1].endswith((".", "!", "?"))):
                saetze[-1] += " " + t
                continue
        saetze.append(t)
    return saetze


# ---------------------------------------------------------------------------
# 3. Chunking
# ---------------------------------------------------------------------------
def strukturchunks(eintraege, bildbeschreibungen=None, mit_beschreibungen=False):
    """content_list (MinerU) -> Chunks im Format der Wissensbasis.
    bildbeschreibungen: {img_path: beschreibung}; nur genutzt, wenn mit_beschreibungen=True.
    Chunk-Felder: id, thema (Abschnittspfad), text, seite (1-basiert), typ (text|tabelle|abbildung),
    bild (relativer Bildpfad bei abbildung/tabelle).

    Regeln: nummerierte Überschriften bilden den Abschnittspfad und beenden den Chunk;
    unnummerierte Überschriften (z. B. "Beispiel 2.3") beenden den Chunk und stehen als erste
    Zeile im nächsten, ohne in den Pfad zu gehen; Absätze werden bis ~ZIEL_WOERTER gesammelt,
    ein zu langer Absatz wird an Satzgrenzen geteilt; Formeln bleiben beim vorangehenden Text;
    Abbildungen und Tabellen sind eigene Chunks und unterbrechen den Textfluss nicht;
    Reste unter MIN_WOERTER werden an den vorigen Chunk desselben Abschnitts angehängt."""
    bildbeschreibungen = bildbeschreibungen or {}
    chunks = []
    pfad = []                # [(ebene, titel)]
    puffer, puffer_seite, puffer_thema = [], None, ""

    def abschnitt():
        return " > ".join(t for _, t in pfad)

    def neuer_chunk(text, seite, typ="text", bild="", thema=None):
        chunks.append({"id": f"pdf_{len(chunks):04d}", "thema": abschnitt() if thema is None else thema,
                       "text": text, "seite": seite, "typ": typ, "bild": bild})

    def text_chunk(text, seite, thema):
        letzter = next((c for c in reversed(chunks) if c["typ"] == "text"), None)
        if (_woerter(text) < MIN_WOERTER and letzter is not None and letzter["thema"] == thema
                and _woerter(letzter["text"]) + _woerter(text) <= ZIEL_WOERTER * 1.3):
            letzter["text"] += " " + text
            return
        neuer_chunk(text, seite, thema=thema)

    def leere_puffer():
        nonlocal puffer, puffer_seite
        if not puffer:
            return
        text = " ".join(puffer).strip()
        puffer, seite = [], puffer_seite
        puffer_seite = None
        if _woerter(text) <= ZIEL_WOERTER * 1.3:
            text_chunk(text, seite, puffer_thema)
            return
        saetze = _saetze(text)
        n_teile = max(2, round(_woerter(text) / ZIEL_WOERTER))
        ziel = _woerter(text) / n_teile
        aktuell = []
        for satz in saetze:
            if aktuell and _woerter(" ".join(aktuell)) >= ziel:
                text_chunk(" ".join(aktuell), seite, puffer_thema)
                aktuell = []
            aktuell.append(satz)
        if aktuell:
            text_chunk(" ".join(aktuell), seite, puffer_thema)

    def anhaengen(text, seite, ist_formel=False):
        nonlocal puffer_seite, puffer_thema
        if (not ist_formel and puffer and abschnitt() == puffer_thema
                and _woerter(" ".join(puffer)) + _woerter(text) > ZIEL_WOERTER
                and _woerter(" ".join(puffer)) >= MIN_WOERTER):
            leere_puffer()
        if not puffer:
            puffer_seite, puffer_thema = seite, abschnitt()
        puffer.append(text)

    for e in eintraege:
        typ = e.get("type", "text")
        seite = int(e.get("page_idx", 0)) + 1
        if typ in ("discarded", "header", "footer", "page_number", "page_header", "page_footer",
                   "page_footnote", "aside_text"):
            continue

        if typ == "text" or typ == "list" or (not ist_abbildung(e) and typ not in ("table", "equation") and e.get("text")):
            if typ == "list" and e.get("list_items"):
                text = bereinige(" ".join(e.get("list_items")))
            else:
                text = bereinige(e.get("text", ""))
            if not text or re.fullmatch(r"[\d\sIVXivx.\-–]+", text):
                continue  # leere Zeilen, reine Seitenzahlen
            m = _NUMMERIERT.match(text)
            if e.get("text_level") and _woerter(text) <= 15:
                leere_puffer()
                if m:
                    ebene = len(m.group(1).split("."))
                    while pfad and pfad[-1][0] >= ebene:
                        pfad.pop()
                    pfad.append((ebene, text))
                else:
                    anhaengen(text + ":", seite)
                continue
            anhaengen(text, seite)
            continue

        if typ == "equation":
            latex = (e.get("text") or "").strip()
            if latex:
                anhaengen(bereinige(latex if latex.startswith("$") else f"$${latex}$$"), seite, ist_formel=True)
            continue

        if typ == "table":
            titel = _liste(e.get("table_caption"))
            fuss = _liste(e.get("table_footnote"))
            koerper = tabelle_als_text(e.get("table_body", ""))
            zeilen = koerper.splitlines() or [""]
            teil, teile = [], []
            for z in zeilen:
                if teil and _woerter("\n".join(teil + [z])) > TABELLE_MAX_WOERTER:
                    teile.append(teil)
                    teil = []
                teil.append(z)
            teile.append(teil)
            for t in teile:
                text = "\n".join(x for x in [f"Tabelle: {titel}" if titel else "Tabelle", "\n".join(t), fuss] if x)
                neuer_chunk(text.strip(), seite, "tabelle", e.get("img_path", ""))
            continue

        if ist_abbildung(e):
            titel = bildunterschrift(e)
            fuss = bildfussnote(e)
            bild = e.get("img_path", "")
            beschreibung = bildbeschreibungen.get(bild, "") if mit_beschreibungen else ""
            if not (titel or beschreibung):
                continue
            teile = [f"Abbildung: {titel}" if titel else "Abbildung"]
            if fuss:
                teile.append(fuss)
            if beschreibung:
                teile.append(f"Bildbeschreibung (automatisch erzeugt): {beschreibung}")
            neuer_chunk("\n".join(teile), seite, "abbildung", bild)
            continue

    leere_puffer()
    for n, c in enumerate(chunks):
        c["id"] = f"pdf_{n:04d}"
    return chunks


def statistik(chunks):
    from collections import Counter
    w = sorted(_woerter(c["text"]) for c in chunks)
    typen = Counter(c["typ"] for c in chunks)
    median = w[len(w) // 2] if w else 0
    return (f"{len(chunks)} Chunks ({', '.join(f'{k} {v}' for k, v in typen.items())}); "
            f"Wörter Median {median}, Min {w[0] if w else 0}, Max {w[-1] if w else 0}")
