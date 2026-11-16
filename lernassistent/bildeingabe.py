"""
bildeingabe.py
--------------
BE-v1: Aufgabe als Foto oder Screenshot hochladen.

Ablauf: Bild im Eingabefeld anhängen -> Vision-Modell (qwen3.5:9b, dasselbe Modell wie die Antworten) schreibt die
Aufgabenstellung ab und beschreibt die Abbildung -> beides läuft sofort als Frage durch die normale Pipeline (Suche, Antwort,
Rechenprüfung); die Frage im Chat zeigt, was erkannt wurde (Abbildung als "automatisch beschrieben, ohne Gewähr").
Mit LERNASSISTENT_BILD_PRUEFEN=1 (Entwicklung) erscheint der Text vorher zum Prüfen. Das Bild selbst wird nicht gespeichert,
nur der Text (bildeingabe.csv).

Aufgabentext, Zahlen und Einheiten werden zuverlässig gelesen; Abbildungsbeschreibungen sind weniger zuverlässig. Die
Beschreibung geht deshalb gekennzeichnet in die Frage ein; Fehler sind damit sichtbar und werden im Protokoll (roh_text)
festgehalten.
"""
import base64
import csv
import datetime
import hashlib
import io
import os
import re
import time
from pathlib import Path

import requests

BILD_VERSION = "BE-v5"
BILD_MODELL = os.environ.get("LERNASSISTENT_BILDMODELL", "")  # leer = Modell der Pipeline (qwen3.5:9b)
BILD_OPTIONEN = {"temperature": 0, "seed": 42, "num_predict": 900, "repeat_penalty": 1.1}
MAX_KANTE_PX = 1600
MAX_BYTES = 8 * 1024 * 1024
BILD_LOG = Path("evaluationsdaten") / "bildeingabe.csv"
BILD_LOG_FELDER = ["zeitstempel", "sitzungs_id", "version", "modell", "bild_hash", "sekunden", "roh_text",
                   "bestaetigter_text", "geaendert", "abbildung_erkannt"]

PROMPT = """Du siehst die Aufnahme einer Seite oder Abbildung aus einem technischen Lehrbuch.
1. AUFGABENTEXT: Schreibe eine im Bild vorhandene Aufgabenstellung wörtlich ab (bei Teilaufgaben alle). Zahlen, Einheiten und Formelzeichen genau wie im Bild, Formeln im Klartext mit Klammern in Brüchen. Schreibe keine Lösung und keine Rechnung ab, die unter der Aufgabe steht. Steht im Bild keine Aufgabenstellung (zum Beispiel nur eine Abbildung), schreibe: keiner. Erfinde niemals eine Aufgabe.
2. THEMA: Nenne in 3 bis 8 Stichwörtern das technische Thema des Bildes (Fachbegriffe, Bildunterschrift, sichtbare Beschriftungen). Nur was im Bild erkennbar ist; wenn du das Thema nicht sicher kennst, nenne nur die sichtbaren Beschriftungen.
3. ABBILDUNG: Beschreibe eine vorhandene Abbildung so genau, dass man sie ohne das Bild erklären könnte: Art (Schaltplan, Diagramm, Schnittbild ...), alle Bauteile und Größen mit ihrer Beschriftung, wie sie verbunden sind oder zusammenhängen, Pfeile und Richtungen, bei Diagrammen die Achsen mit Einheiten und ablesbare Zahlenwerte. Gib nur wieder, was eindeutig zu sehen ist; Unsicheres kennzeichne mit [unsicher].
Was unleserlich ist, schreibe als [unleserlich]. Antworte auf Deutsch, ohne Markdown und ohne LaTeX, in genau diesem Format:
AUFGABENTEXT: ... (oder: keiner)
THEMA: ...
ABBILDUNG: ... (oder: keine Abbildung)"""

_LATEX = (
    (r"\\\(|\\\)|\\\[|\\\]|\$", ""),
    (r"\\mathrm\{([^}]*)\}|\\text\{([^}]*)\}", lambda m: m.group(1) or m.group(2) or ""),
    (r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1)/(\2)"),
    (r"\\sqrt\{([^}]*)\}", r"√(\1)"),
    (r"\\sqrt\s*", "√"),
    (r"\\cdot", "·"), (r"\\times", "×"), (r"\\Omega", "Ω"), (r"\\omega", "ω"), (r"\\varphi|\\phi", "φ"),
    (r"\\mu", "μ"), (r"\\eta", "η"), (r"\\pi", "π"), (r"\\leq?", "≤"), (r"\\geq?", "≥"), (r"\\approx", "≈"),
    (r"\\,|\\;|\\ ", " "),
    (r"\^\{?2\}?", "²"), (r"\^\{?3\}?", "³"),
    (r"_\{([^}]*)\}", r"_\1"),
)


def bereinige(text):
    """Entfernt LaTeX-Reste und Markdown-Zeichen aus der Abschrift (leichte Reinigung, keine inhaltliche Änderung)."""
    t = text or ""
    for muster, ersatz in _LATEX:
        t = re.sub(muster, ersatz, t)
    t = re.sub(r"[*#`]+", "", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


_LEER = re.compile(r"(?is)^\W*(keine?r?|kein\s+text|keine\s+abbildung|keine\s+aufgabe\w*|-+|n/a)\W*$")


def zerlege_felder(roh):
    """Antwort -> (aufgabentext, thema, abbildung). Fehlt das Format, gilt der ganze Text als Aufgabentext.
    'keiner' / 'keine Abbildung' zählen als leer."""
    t = (roh or "").strip()
    marken = list(re.finditer(r"(?im)^\s*(AUFGABENTEXT|THEMA|ABBILDUNG)\s*:\s*", t))
    if not marken:
        return bereinige(t), "", ""
    felder = {}
    for i, m in enumerate(marken):
        ende = marken[i + 1].start() if i + 1 < len(marken) else len(t)
        felder.setdefault(m.group(1).upper(), t[m.end():ende].strip())
    def sauber(x):
        x = bereinige(x or "")
        return "" if _LEER.match(x) or re.match(r"(?i)keine abbildung\b", x) or re.match(r"(?i)keiner\b", x) else x
    return sauber(felder.get("AUFGABENTEXT")), sauber(felder.get("THEMA")), sauber(felder.get("ABBILDUNG"))


def zerlege(roh):
    """Wie zerlege_felder, ohne Thema (Rückwärtskompatibel): (aufgabentext, abbildung)."""
    a, _, b = zerlege_felder(roh)
    return a, b


ABB_KOPF = "Abbildung zur Aufgabe (automatisch beschrieben, ohne Gewähr):"
STANDARD_FRAGE = "Erkläre diese Abbildung: Aufbau, Bauteile und Funktionsweise."
_FRAGEWORT = re.compile(r"(?i)\?|\b(berechne\w*|bestimme\w*|ermittle\w*|erkl[äa]r\w*|nenne\w*|beschreib\w*|begr[üu]nde\w*|zeige\w*|skizzier\w*|"
                        r"leite\w*|gib|geben|wie|was|warum|wieso|weshalb|welche\w*|wozu|wof[üu]r|wann|wo|wer|wieviel\w*|"
                        r"explain|describe|calculate|what|why|how|which)\b|\?")


def braucht_standardfrage(text):
    """True, wenn die Eingabe keine Frage/Aufgabe enthält (nur Bild, Bildunterschrift o. Ä.): dann wird STANDARD_FRAGE ergänzt."""
    t = (text or "").strip()
    return not t or not _FRAGEWORT.search(t)


_FUELLWORT = set("""erkläre erklär erklären erklärt diese dieses diesen dieser die der das den dem ein eine einen bitte mir uns was ist sind
zeigt zeigen sehe sehen siehst hier wir hat haben wie funktioniert funktionieren bild abbildung abb figur grafik zeichnung skizze
bedeutet bedeuten mal kurz genau ausführlich und oder zu zur zum von im in am an auf dazu dort da""".split())


def thema_im_text(text):
    """True, wenn die Eingabe neben Aufforderungs-/Füllwörtern mindestens ein inhaltliches Wort enthält (Thema, Fachbegriff)."""
    woerter = re.findall(r"[A-Za-zÄÖÜäöüß0-9_\-]+", text or "")
    return any(w.lower() not in _FUELLWORT and len(w) > 2 for w in woerter)


def kombiniere(text, abbildung):
    """Frage für die Pipeline: Aufgabentext plus, falls vorhanden, die Abbildungsbeschreibung (gekennzeichnet als automatisch)."""
    text = (text or "").strip()
    abb = (abbildung or "").strip()
    return f"{text}\n\n{ABB_KOPF} {abb}" if abb else text


def pruefen_verlangt():
    """LERNASSISTENT_BILD_PRUEFEN=1: erkannter Text wird vor dem Senden angezeigt und kann korrigiert werden (Entwicklungsmodus).
    Standard: Bild lesen und direkt beantworten."""
    return os.environ.get("LERNASSISTENT_BILD_PRUEFEN", "") == "1"


def verkleinere(daten):
    """Bild auf höchstens MAX_KANTE_PX verkleinern (schneller, gleiche Lesbarkeit); ohne Pillow unverändert."""
    try:
        from PIL import Image
        bild = Image.open(io.BytesIO(daten))
        bild.load()
        if max(bild.size) > MAX_KANTE_PX:
            faktor = MAX_KANTE_PX / max(bild.size)
            bild = bild.resize((max(1, int(bild.width * faktor)), max(1, int(bild.height * faktor))))
        if bild.mode not in ("RGB", "L"):
            bild = bild.convert("RGB")
        puffer = io.BytesIO()
        bild.save(puffer, format="PNG")
        return puffer.getvalue()
    except Exception:
        return daten


def lies_aufgabe(daten, url=None, modell=None, post=None):
    """Bild (bytes) -> dict(text, abbildung, roh, sekunden, fehler, modell, bild_hash). Wirft keine Ausnahme nach außen.
    post: für Tests austauschbar (Standard requests.post)."""
    t0 = time.perf_counter()
    erg = {"text": "", "abbildung": "", "roh": "", "sekunden": 0.0, "fehler": "", "modell": "",
           "thema": "", "bild_hash": hashlib.sha256(daten or b"").hexdigest()[:12]}
    try:
        if not daten:
            raise ValueError("leere Datei")
        if len(daten) > MAX_BYTES:
            raise ValueError("Datei größer als 8 MB")
        import rag_pipeline as rp
        url = url or rp.OLLAMA_URL
        modell = modell or BILD_MODELL or rp.MODEL_NAME
        erg["modell"] = modell
        nutzlast = {"model": modell, "prompt": PROMPT, "stream": False, "think": False, "options": BILD_OPTIONEN,
                    "images": [base64.b64encode(verkleinere(daten)).decode()]}
        r = (post or requests.post)(url, json=nutzlast, timeout=240)
        r.raise_for_status()
        erg["roh"] = r.json()["response"].strip()
        erg["text"], erg["thema"], erg["abbildung"] = zerlege_felder(erg["roh"])
        if not erg["text"] and not erg["abbildung"] and not erg["thema"]:
            erg["fehler"] = "Im Bild wurde weder Text noch eine Abbildung erkannt."
    except Exception as e:
        erg["fehler"] = f"Das Bild konnte nicht gelesen werden ({str(e)[:100]})."
    erg["sekunden"] = round(time.perf_counter() - t0, 1)
    return erg


def protokolliere_bild(sitzungs_id, erg, bestaetigt, pfad=None):
    """Eine Zeile je bestätigter Bildfrage (nur Text, kein Bild). geaendert = Person hat die Abschrift korrigiert."""
    pfad = Path(pfad or BILD_LOG)
    pfad.parent.mkdir(exist_ok=True)
    neu = not pfad.exists()
    with open(pfad, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=BILD_LOG_FELDER)
        if neu:
            w.writeheader()
        w.writerow({
            "zeitstempel": datetime.datetime.now().isoformat(timespec="seconds"), "sitzungs_id": sitzungs_id,
            "version": BILD_VERSION, "modell": erg.get("modell", ""), "bild_hash": erg.get("bild_hash", ""),
            "sekunden": erg.get("sekunden", ""), "roh_text": erg.get("roh") or erg.get("text", ""), "bestaetigter_text": bestaetigt,
            "geaendert": (bestaetigt.strip() not in ((erg.get("text") or "").strip(), kombiniere(erg.get("text"), erg.get("abbildung")))),
            "abbildung_erkannt": bool(erg.get("abbildung")),
        })


def _chat_input_mit_datei():
    """True, wenn st.chat_input Dateien annimmt (Streamlit >= 1.43, Parameter accept_file)."""
    try:
        import inspect
        import streamlit as st
        return "accept_file" in inspect.signature(st.chat_input).parameters
    except Exception:
        return False


DATEITYPEN = ["png", "jpg", "jpeg", "webp"]


def chat_eingabe(platzhalter):
    """Eingabefeld der App. Mit Büroklammer im Feld (accept_file), sofern die Streamlit-Version es kann: Bild anhängen ->
    Text wird gelesen -> Bestätigungsblock im Chat (bildeingabe_ui). Ohne Bild wie st.chat_input. Rückgabe: Frage (str) oder None."""
    import streamlit as st
    if not _chat_input_mit_datei():
        return st.chat_input(platzhalter)
    wert = st.chat_input(platzhalter, accept_file=True, file_type=DATEITYPEN)
    if not wert:
        return None
    text = (getattr(wert, "text", None) if not isinstance(wert, str) else wert) or ""
    dateien = list(getattr(wert, "files", None) or []) if not isinstance(wert, str) else []
    if not dateien:
        return text.strip() or None
    with st.spinner("Das Bild wird gelesen …"):
        erg = lies_aufgabe(dateien[0].getvalue())
    erg["abgleich"] = None
    try:  # optional (LERNASSISTENT_BILDABGLEICH=1): Abbildung der Wissensbasis zuordnen
        import bildabgleich
        idx = bildabgleich.index_fuer_app()
        if idx:
            erg["abgleich"] = bildabgleich.finde(dateien[0].getvalue(), idx)
    except Exception as e:
        print(f"WARNUNG Bildabgleich: {e}")
    erg["hinweis_text"] = text.strip()  # was die Person zusätzlich ins Feld geschrieben hat
    aufgabe = (erg["text"] + ("\n" + text.strip() if text.strip() else "")).strip()
    if not pruefen_verlangt() and not erg["fehler"] and braucht_standardfrage(aufgabe):
        aufgabe = (aufgabe + "\n" + STANDARD_FRAGE).strip()  # nur Bild/Bildunterschrift -> Abbildung erklären
    if pruefen_verlangt() or erg["fehler"] or not aufgabe:
        st.session_state["bild_ergebnis"] = erg  # Fehler oder Entwicklungsmodus: Block mit Text/Meldung
        st.session_state["bild_text"] = aufgabe
    else:
        frage = kombiniere(aufgabe, erg.get("abbildung"))
        such_extra = ""
        if erg.get("abgleich"):
            import bildabgleich
            such_extra, fund = bildabgleich.fundstelle(erg["abgleich"])
            frage = f"{frage}\n\n{fund}"
            erg["roh"] = (erg.get("roh") or "") + f"\n[ABGLEICH] {erg['abgleich']['inlier']} Inlier (2.: {erg['abgleich']['rang2']}) {fund}"
        try:
            protokolliere_bild(st.session_state.get("sitzungs_id", ""), erg, frage)
        except Exception as e:
            print(f"WARNUNG Bildprotokoll: {e}")
        st.session_state["naechste_frage"] = frage
        # Suche nur mit Aufgabentext/Eingabe + Thema-Stichwörtern; die (oft fehlerhafte) Beschreibung geht nur an die Antwort
        st.session_state["naechste_suche"] = " ".join(x for x in (aufgabe, erg.get("thema"), such_extra) if x).strip()
        st.session_state["naechste_bild_meta"] = {"thema_fehlt": not thema_im_text(text) and not erg.get("abgleich")}  # nur die Eingabe der Person zählt
        st.session_state["naechstes_bild"] = dateien[0].getvalue()  # Bild im Chat zeigen und an die Antwort geben
    st.rerun()
    return None


def _senden_callback():
    import streamlit as st
    text = (st.session_state.get("bild_text") or "").strip()
    if not text:
        return
    text = kombiniere(text, (st.session_state.get("bild_ergebnis") or {}).get("abbildung"))
    try:
        protokolliere_bild(st.session_state.get("sitzungs_id", ""), st.session_state.get("bild_ergebnis") or {}, text)
    except Exception as e:  # Protokoll darf die Frage nie verhindern
        print(f"WARNUNG Bildprotokoll: {e}")
    st.session_state["naechste_frage"] = text
    st.session_state["bild_nr"] = st.session_state.get("bild_nr", 0) + 1
    for k in ("bild_ergebnis", "bild_text"):
        st.session_state.pop(k, None)


def _verwerfen_callback():
    import streamlit as st
    st.session_state["bild_nr"] = st.session_state.get("bild_nr", 0) + 1
    for k in ("bild_ergebnis", "bild_text"):
        st.session_state.pop(k, None)


def _bestaetigung(st, erg):
    """Prüfen/Korrigieren der erkannten Aufgabe (gemeinsam für Chat-Variante und Expander)."""
    if erg["fehler"]:
        st.error(erg["fehler"])
        st.button("Schließen", key="bild_zu", on_click=_verwerfen_callback)
        return
    st.text_area("Erkannte Aufgabe – bitte prüfen und korrigieren", key="bild_text", height=170)
    st.warning("Bitte Zahlen, Einheiten und Formelzeichen genau prüfen. Die Abbildung wird automatisch beschrieben und "
               "kann Fehler enthalten.")
    if len(st.session_state.get("bild_text") or "") > 1200:
        st.info("Der Text ist sehr lang. Lass bitte nur die Aufgabenstellung stehen, nicht die Lösung.")
    if erg.get("abbildung"):
        with st.expander("Vom Modell beschriebene Abbildung (automatisch, ohne Gewähr; geht in die Frage ein)"):
            st.write(erg["abbildung"])
    c1, c2 = st.columns([1, 1])
    with c1:
        st.button("Frage stellen", key="bild_senden", type="primary", on_click=_senden_callback)
    with c2:
        st.button("Verwerfen", key="bild_verwerfen", on_click=_verwerfen_callback)


def bildeingabe_ui():
    """Block über dem Eingabefeld. Mit Datei-Feld im Chat (Streamlit >= 1.43): nur der Bestätigungsblock, sobald ein Bild
    gelesen wurde. Sonst (ältere Streamlit-Version): Expander mit eigenem Upload-Feld.
    Die bestätigte Abschrift geht als st.session_state["naechste_frage"] in die normale Pipeline."""
    import streamlit as st
    erg = st.session_state.get("bild_ergebnis")
    if _chat_input_mit_datei():
        if erg:
            with st.chat_message("user"):
                st.caption("📷 Bild der Aufgabe angehängt")
            with st.chat_message("assistant"):
                st.write("Das habe ich im Bild erkannt. Bitte prüfe den Text, bevor ich ihn als Frage stelle.")
                _bestaetigung(st, erg)
        return
    nr = st.session_state.get("bild_nr", 0)
    with st.expander("📷 Aufgabe als Foto oder Screenshot hochladen"):
        st.caption("Das Bild wird nur gelesen und nicht gespeichert. Du prüfst den erkannten Text, bevor er als Frage gestellt wird.")
        datei = st.file_uploader("Bild der Aufgabe (PNG oder JPG)", type=DATEITYPEN, key=f"bild_datei_{nr}")
        if datei is not None:
            st.image(datei, width=320)
            if st.button("Text aus dem Bild lesen", key=f"bild_lesen_{nr}"):
                with st.spinner("Das Bild wird gelesen …"):
                    erg = lies_aufgabe(datei.getvalue())
                if pruefen_verlangt() or erg["fehler"]:
                    st.session_state["bild_ergebnis"] = erg
                    st.session_state["bild_text"] = erg["text"]
                else:
                    frage = kombiniere(erg["text"], erg.get("abbildung"))
                    try:
                        protokolliere_bild(st.session_state.get("sitzungs_id", ""), erg, frage)
                    except Exception as e:
                        print(f"WARNUNG Bildprotokoll: {e}")
                    st.session_state["naechste_frage"] = frage
                    st.session_state["bild_nr"] = st.session_state.get("bild_nr", 0) + 1
                    st.rerun()
        erg = st.session_state.get("bild_ergebnis")
        if erg:
            _bestaetigung(st, erg)
