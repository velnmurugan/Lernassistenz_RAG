"""V21-S: schnellere Fassung für die Pilotstudie (Antworten wie V20, nur andere Reihenfolge/Rechenort).

Zwei Schalter, beide standardmäßig AUS (dann verhält sich alles wie V20; Auswertungsskripte unberührt):
  LERNASSISTENT_RR_GPU=1          Reranker (bge) läuft auf der GPU: qwen wird dafür kurz aus der GPU entladen,
                                  der Reranker danach wieder auf die CPU geschoben; qwen lädt beim nächsten Aufruf neu.
                                  Bei jedem Problem (keine GPU, kein Speicher) Rückfall auf die CPU wie in V20.
  LERNASSISTENT_HINWEIS_ZUERST=1  Die App zeigt den Hinweis, sobald die Antwort geschrieben ist; Rechenprüfung und
                                  Abschlussprüfungen laufen im Hintergrund weiter. Lösung, Rückmeldung und Protokoll
                                  kommen erst aus dem vollständigen V20-Ergebnis (unverändert).
Alles oder nichts: jede Ersetzung prüft ihren Anker. Sicherungen *.vor_v21s. Zurück: cp <datei>.vor_v21s <datei>.
Aufruf aus ~/RAG:  python ~/v21s/patch_v21s.py
"""
import shutil
import sys
from pathlib import Path

MARKE = "# V21-S"
WURZEL = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
APP = WURZEL / "app.py"
RR = WURZEL / "lernassistent" / "reranker.py"
RP = WURZEL / "lernassistent" / "rag_pipeline.py"
E = []

# ---------------------------------------------------------------- 1 Reranker auf der GPU (mit Entladen von qwen)
E.append((RR, "def bewerte(frage, texte):", '''import os as _os21, threading as _th21, time as _t21  # V21-S
_RR_GPU = _os21.environ.get("LERNASSISTENT_RR_GPU") == "1"
GPU_SPERRE = _th21.RLock()  # V21-S: Reranker und Sprachmodell nie gleichzeitig auf der GPU
GPU_PROTOKOLL = []  # V21-S: (Sekunden, "gpu" | "cpu-rueckfall") je Aufruf


def _ollama_entladen():
    """V21-S: alle geladenen Ollama-Modelle aus der GPU nehmen (keep_alive 0) und warten, bis sie weg sind."""
    import requests
    import rag_pipeline as _rp
    ps = _rp.OLLAMA_URL.replace("/api/generate", "/api/ps")
    try:
        for m in requests.get(ps, timeout=5).json().get("models", []):
            requests.post(_rp.OLLAMA_URL, json={"model": m["name"], "keep_alive": 0}, timeout=60)
        for _ in range(80):
            if not requests.get(ps, timeout=5).json().get("models"):
                return True
            _t21.sleep(0.25)
    except Exception as e:
        print(f"WARNUNG V21-S Ollama entladen: {e}")
    return False


def _bewerte_gpu(paare):
    """V21-S: dieselbe Bewertung wie auf der CPU, gerechnet auf der GPU (fp32, gleiches Modell)."""
    import torch
    import torch.nn as nn
    modell = _lade()  # geladen auf RERANKER_GERAET ("cpu")
    netz = modell if isinstance(modell, nn.Module) else modell.model
    t, art = _t21.perf_counter(), "gpu"
    with GPU_SPERRE:
        try:
            if not torch.cuda.is_available():
                raise RuntimeError("keine GPU")
            if not _ollama_entladen():
                raise RuntimeError("Ollama-Modell nicht entladen")
            netz.to("cuda")
            if hasattr(modell, "_target_device"):
                modell._target_device = torch.device("cuda")
            werte = modell.predict(paare, batch_size=16, show_progress_bar=False)
        except Exception as e:
            print(f"WARNUNG V21-S Reranker auf GPU nicht möglich ({e}) – CPU wie V20")
            art = "cpu-rueckfall"
            netz.to("cpu")
            if hasattr(modell, "_target_device"):
                modell._target_device = torch.device("cpu")
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
            werte = modell.predict(paare, batch_size=16, show_progress_bar=False)
        finally:
            netz.to("cpu")
            if hasattr(modell, "_target_device"):
                modell._target_device = torch.device("cpu")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
    GPU_PROTOKOLL.append((round(_t21.perf_counter() - t, 2), art))
    return werte


def bewerte(frage, texte):'''))
E.append((RR, '''    werte = _lade().predict(paare, batch_size=16, show_progress_bar=False)
    return [float(w) for w in werte]''', '''    if _RR_GPU:  # V21-S
        return [float(w) for w in _bewerte_gpu(paare)]
    werte = _lade().predict(paare, batch_size=16, show_progress_bar=False)
    return [float(w) for w in werte]'''))

# ---------------------------------------------------------------- 2 Pipeline: Hinweis vorab melden, Sprachmodell unter der GPU-Sperre
E.append((RP, '''    top_chunks, prompt, stufen = _formelsuche_nachher(frage, chunks, top_chunks, prompt, stufen, methode, ergebnis, fortschritt)  # ab V12.1 (FS-v2)
    _ende("antwort", t0)''', '''    top_chunks, prompt, stufen = _formelsuche_nachher(frage, chunks, top_chunks, prompt, stufen, methode, ergebnis, fortschritt)  # ab V12.1 (FS-v2)
    _ende("antwort", t0)
    if fortschritt is not None and getattr(fortschritt, "_v21", False) and ist_g_version():  # V21-S: Hinweis vorab
        try:  # Vorschau auf einer Kopie: der weitere Ablauf (Rechenprüfung, Hinweisprüfung) bleibt wie in V20
            import copy as _cp21
            _vorab = _cp21.deepcopy(stufen)
            hinweis_pruefen(frage, _vorab)
            fortschritt("antwort", "hinweis_vorab", None, _vorab)
        except Exception as _e21:
            print(f"WARNUNG V21-S Hinweis vorab: {_e21}")'''))
E.append((RP, '''INTERAKTIONS_FELDER = [''', '''# V21-S: Sprachmodell-Aufrufe teilen sich die GPU mit dem Reranker (nur mit LERNASSISTENT_RR_GPU=1)
if os.environ.get("LERNASSISTENT_RR_GPU") == "1":
    import reranker as _rr21
    _frage_llm_v20 = frage_llm

    def frage_llm(*args, **kwargs):  # noqa: F811  V21-S
        with _rr21.GPU_SPERRE:
            return _frage_llm_v20(*args, **kwargs)


INTERAKTIONS_FELDER = ['''))

# ---------------------------------------------------------------- 3 App: Hinweis zuerst, Lösung im Hintergrund
E.append((APP, '''def seite_chat():
    seitenleiste()  # UI-v2
    st.title(f"🎓 {APP_NAME}")
    verlauf = st.session_state["verlauf"]''', '''_V21_HZ = _os.environ.get("LERNASSISTENT_HINWEIS_ZUERST") == "1"  # V21-S


def _v21_job_starten(frage):
    """V21-S: beantwortet die Frage in einem Hintergrund-Thread (vollständige V20-Pipeline). Der Thread schreibt nur
    in das dict job (keine Streamlit-Aufrufe); die Oberfläche liest es."""
    import threading
    job = {"vorab": None, "ergebnis": None, "fehler": None, "phasen": {}, "quellen": None, "start": time.perf_counter()}

    def rueckruf(phase, ereignis, dauer=None, daten=None):
        if ereignis == "hinweis_vorab":
            if (daten or {}).get("status") in ("BEANTWORTET", "TEILWEISE") and (daten or {}).get("hinweis"):
                job["vorab"] = daten
        elif ereignis == "quellen":
            job["quellen"] = daten
        elif ereignis in ("start", "ende"):
            job["phasen"][phase] = (ereignis, dauer)
    rueckruf._v21 = True

    def arbeit():
        try:
            job["ergebnis"] = beantworte_frage(frage, CHUNKS, fortschritt=rueckruf)
        except Exception as fehler:
            print(f"FEHLER beantworte_frage (V21-S): {type(fehler).__name__}: {fehler}")
            job["fehler"] = fehler
    threading.Thread(target=arbeit, daemon=True).start()
    return job


def _v21_status_zeigen(status, job, zeilen):
    """V21-S: Fortschritt wie fortschritt_anzeige, aber aus dem Job gelesen."""
    if job["quellen"] and "quellen" not in zeilen:
        orte = []
        for c in job["quellen"]:
            ort = (f"{c['buch']} " if c.get("buch") else "") + (f"S. {c['seite']}" if c.get("seite") else "")
            if ort.strip() and ort.strip() not in orte:
                orte.append(ort.strip())
        zeilen["quellen"] = status.empty()
        if orte:
            zeilen["quellen"].markdown("📎 Gefunden: " + " · ".join(orte))
    for phase in PHASEN:
        if phase in job["phasen"]:
            ereignis, dauer = job["phasen"][phase]
            if phase not in zeilen:
                zeilen[phase] = status.empty()
            zeilen[phase].markdown(f"⏳ {PHASEN[phase][0]} …" if ereignis == "start"
                                   else f"✓ {PHASEN[phase][1]} · {sek(dauer)}")


def _v21_fertig(job, frage):
    """V21-S: Endergebnis (wie V20) oder Fehlerhinweis; Protokoll wie in V20 nach der Antwort."""
    if job["ergebnis"] is not None:
        erg = job["ergebnis"]
        vorab = (job.get("vorab") or {}).get("hinweis")
        if vorab and vorab != erg.get("hinweis"):
            print(f"HINWEIS V21-S: Vorab-Hinweis wich vom endgültigen ab ({frage[:60]})")
        protokolliere_interaktion(st.session_state["sitzungs_id"], erg, scaffolding_stufe_erreicht=1)
        return erg
    return {"frage": frage, "status": "GATE", "hinweis": "", "erklaerung": "", "vollstaendig_geparst": False,
            "loesung": "Die Antwort konnte gerade nicht fertig erzeugt werden. Bitte stelle die Frage noch einmal.",
            "quellen": [], "top_chunks": [], "sicherheitshinweis": None, "zeiten": {}}


def _v21_abschliessen(verlauf):
    """V21-S: fertige Hintergrund-Jobs durch ihr Endergebnis ersetzen."""
    for i, e in enumerate(verlauf):
        job = e.get("_v21_job")
        if job is not None and (job["ergebnis"] is not None or job["fehler"] is not None):
            verlauf[i] = _v21_fertig(job, e["frage"])


def _frage_hintergrund(frage):
    """V21-S: Frage starten, auf den Hinweis warten (Fortschritt sichtbar), Lösung im Hintergrund weiterrechnen."""
    with st.chat_message("user"):
        st.write(frage)
    with st.chat_message("assistant"):
        with st.status("Der Assistent arbeitet …", expanded=True) as status:
            job, zeilen = _v21_job_starten(frage), {}
            while job["ergebnis"] is None and job["fehler"] is None and job["vorab"] is None:
                _v21_status_zeigen(status, job, zeilen)
                time.sleep(0.3)
            _v21_status_zeigen(status, job, zeilen)
            if job["fehler"] is not None:
                status.update(label="Keine Antwort erzeugt", state="error", expanded=False)
                st.error("Die Antwort konnte gerade nicht erzeugt werden (das Sprachmodell hat nicht rechtzeitig "
                         "geantwortet). Bitte stelle die Frage noch einmal.")
                st.stop()
            status.update(label=f"{'Fertig' if job['ergebnis'] is not None else 'Hinweis bereit'} · "
                                f"{sek(time.perf_counter() - job['start'])}", state="complete", expanded=False)
    if job["ergebnis"] is not None:
        st.session_state["verlauf"].append(_v21_fertig(job, frage))
    else:
        v = job["vorab"]
        st.session_state["verlauf"].append({
            "frage": frage, "_v21_job": job, "hinweis": v.get("hinweis", ""), "status": v.get("status", ""),
            "vollstaendig_geparst": True, "loesung": "", "quellen": [], "top_chunks": [], "sicherheitshinweis": None,
            "zeiten": {}})
    st.session_state["fokus"] = None
    st.rerun()


def _v21_wartend(idx, eintrag):
    """V21-S: Hinweis schon da, Lösung und Rückmeldung werden noch vorbereitet; aktualisiert sich selbst."""
    schrittleiste(1, False)
    st.markdown(f"💡 **Hinweis:** {eintrag['hinweis']}")
    st.caption("⏳ Lösung und Rückmeldung werden noch vorbereitet (die Rechnung wird geprüft). "
               "Denk schon über den Hinweis nach – gleich kannst du deine Idee eingeben.")
    job = eintrag["_v21_job"]

    @st.fragment(run_every=2)
    def _warte():
        if job["ergebnis"] is not None or job["fehler"] is not None:
            try:
                st.rerun(scope="app")
            except TypeError:
                st.rerun()
    _warte()


def seite_chat():
    seitenleiste()  # UI-v2
    st.title(f"🎓 {APP_NAME}")
    _v21_abschliessen(st.session_state["verlauf"])  # V21-S
    verlauf = st.session_state["verlauf"]'''))
E.append((APP, '''    with st.chat_message("assistant"):
        verweigert = eintrag.get("status") in ("GATE", "NICHT_IM_MATERIAL")''', '''    with st.chat_message("assistant"):
        if eintrag.get("_v21_job") is not None:  # V21-S: Hinweis steht, Lösung wird noch vorbereitet
            _v21_wartend(idx, eintrag)
            return
        verweigert = eintrag.get("status") in ("GATE", "NICHT_IM_MATERIAL")'''))
E.append((APP, '''    if frage:
        with st.chat_message("user"):
            if bild:''', '''    if frage and _V21_HZ and not bild:  # V21-S: Textfragen mit Hinweis zuerst (Bildfragen wie V20)
        _frage_hintergrund(frage)
    if frage:
        with st.chat_message("user"):
            if bild:'''))


def main():
    dateien = (APP, RR, RP)
    texte = {p: p.read_text(encoding="utf-8") for p in dateien}
    if any(MARKE in t for t in texte.values()):
        for p in dateien:
            if MARKE in texte[p]:
                b = p.with_name(p.name + ".vor_v21s")
                if not b.exists():
                    print(f"FEHLER: {p.name} enthält V21-S, aber {b.name} fehlt – nichts geändert.")
                    return 1
                texte[p] = b.read_text(encoding="utf-8")
        print("Frühere V21-S-Fassung gefunden – wird aus den Sicherungen *.vor_v21s neu eingespielt.")
    fehlt = [f"{p.name}: Anker {'fehlt' if texte[p].count(a) == 0 else f'{texte[p].count(a)}x'}: {a.strip().splitlines()[0][:80]}"
             for p, a, _ in E if texte[p].count(a) != 1]
    if fehlt:
        print("FEHLER – nichts geändert (unerwarteter Stand):\n" + "\n".join("  " + f for f in fehlt))
        return 1
    neu = dict(texte)
    for p, a, n in E:
        neu[p] = neu[p].replace(a, n, 1)
    for p in neu:
        compile(neu[p], str(p), "exec")
    for p in dateien:
        if neu[p] != p.read_text(encoding="utf-8"):
            if MARKE not in p.read_text(encoding="utf-8"):
                shutil.copy2(p, p.with_name(p.name + ".vor_v21s"))
            p.write_text(neu[p], encoding="utf-8")
            print(f"geändert: {p} (Sicherung {p.name}.vor_v21s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
