"""
vergleich_app.py – Vorführung: dieselbe Frage ohne RAG und mit RAG (Stand V20), nebeneinander.
Genau dieselben Aufrufe wie in der Auswertung Fragen300 (antworten300.py):
  ohne RAG: rp.frage_llm(prompt_ohne_rag(frage)) mit Prompt O-v1, gleiche Generierungsoptionen (T 0, seed 42)
  mit RAG : rp.beantworte_frage(frage, chunks, methode=hybrid_kg_rr) – volle V20-Pipeline, angezeigt wird die Lösung
Nur für Forschende/Vorführung; schreibt kein Interaktionsprotokoll.
Start (aus ~/RAG, pilot_rag aktiv, Ollama läuft):  bash skripte/laeufe/start_vergleich.sh   -> http://localhost:8503
"""
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(next(p for p in _pl.Path(__file__).resolve().parents if (p / "lernassistent").is_dir()) / "lernassistent")); import pfadsetup  # noqa: E402,F401
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent))

import csv
import os
import time
from pathlib import Path

import streamlit as st
import rag_pipeline as rp
from eval300_antworten import prompt_ohne_rag, OHNE_RAG_PROMPT_VERSION

KB = os.environ.get("LERNASSISTENT_KB", "daten/wissensbasen/knowledge_base_fischer_boege_v7r.json")
METHODE = os.environ.get("LERNASSISTENT_RETRIEVAL", "hybrid_kg_rr")
FRAGEN = Path("daten/testfragen/fragen300.csv")

st.set_page_config(page_title="Vergleich ohne/mit RAG", layout="wide")


@st.cache_resource(show_spinner="Wissensbasis wird geladen …")
def lade_chunks():
    return rp.lade_wissensbasis(KB)


@st.cache_data
def lade_fragen():
    if not FRAGEN.exists():
        return []
    with open(FRAGEN, encoding="utf-8") as f:
        return list(csv.DictReader(f))


st.title("Dieselbe Frage – ohne RAG und mit RAG")
st.caption(f"Modell {rp.MODEL_NAME} · {rp.GENERIERUNGS_OPTIONEN} · ohne RAG: Prompt {OHNE_RAG_PROMPT_VERSION} · "
           f"mit RAG: V20 ({rp.SCAFFOLDING_VERSION}), Retrieval {METHODE}, Wissensbasis {Path(KB).name}")

fragen = lade_fragen()
auswahl = None
if fragen:
    optionen = ["(eigene Frage eingeben)"] + [f"{q['id']} · {q['typ']} · {q['frage'][:90]}" for q in fragen]
    wahl = st.selectbox("Frage aus Fragen300 wählen oder eigene eingeben", optionen)
    if wahl != optionen[0]:
        auswahl = fragen[optionen.index(wahl) - 1]

frage = st.text_area("Frage", value=auswahl["frage"] if auswahl else "", height=90)
if auswahl and auswahl.get("referenz"):
    with st.expander("Referenzantwort (aus dem Testsatz)"):
        st.write(auswahl["referenz"])
        st.caption(f"Buch {auswahl.get('buch', '')}, PDF-Seite {auswahl.get('seite_pdf', '')}")

if st.button("Beide Antworten erzeugen", type="primary", disabled=not frage.strip()):
    chunks = lade_chunks()
    links, rechts = st.columns(2)
    with links:
        st.subheader("Ohne RAG")
        with st.spinner("Antwort ohne Buchquellen …"):
            t0 = time.time()
            try:
                antwort = rp.frage_llm(prompt_ohne_rag(frage.strip()), options=rp.GENERIERUNGS_OPTIONEN)
            except Exception as e:
                antwort = f"FEHLER: {type(e).__name__}: {e}"
        st.markdown(antwort)
        st.caption(f"{time.time() - t0:.1f} s · keine Quellen")
        with st.expander("Prompt ohne RAG (O-v1)"):
            st.code(prompt_ohne_rag(frage.strip()), language=None)
    with rechts:
        st.subheader("Mit RAG (V20)")
        with st.spinner("Buchstellen suchen und Antwort erzeugen …"):
            t0 = time.time()
            try:
                erg = rp.beantworte_frage(frage.strip(), chunks, methode=METHODE)
            except Exception as e:
                erg = {"status": "FEHLER", "loesung": f"FEHLER: {type(e).__name__}: {e}", "quellen": []}
        st.markdown(erg.get("loesung") or erg.get("antwort") or "(keine Antwort)")
        quellen = erg.get("quellen", [])
        st.caption(f"{time.time() - t0:.1f} s · Status {erg.get('status', '')} · {len(quellen)} Quellen")
        if quellen:
            with st.expander("Quellen (Buchabschnitte)"):
                for q in quellen:
                    st.write(f"- {q.get('thema', '')} ({q.get('id', '')})")
        if erg.get("hinweis"):
            with st.expander("Hinweis (Stufe 1 in der Lern-App)"):
                st.write(erg["hinweis"])
