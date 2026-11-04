"""UI-v2 für app.py (+ eine Regel in lernhilfen.py, ein Muster in rag_pipeline.py).

Alles oder nichts: Jede Ersetzung prüft ihren Anker; fehlt einer, wird NICHTS geändert.
Sicherungen: *.vor_ui2. Zurück: cp app.py.vor_ui2 app.py (ebenso für die beiden anderen Dateien).
Aufruf aus ~/RAG:  python ~/ui2/patch_ui2.py
"""
import shutil
import sys
from pathlib import Path

MARKE = "# UI-v2"
WURZEL = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
APP = WURZEL / "app.py"
LH = WURZEL / "lernassistent" / "lernhilfen.py"
RP = WURZEL / "lernassistent" / "rag_pipeline.py"

E = []  # (Datei, alt, neu)

# --- 1 Seitenleiste offen ---------------------------------------------------------------------------------
E.append((APP, 'st.set_page_config(page_title=APP_NAME, page_icon="🎓", layout="centered")',
          'st.set_page_config(page_title=APP_NAME, page_icon="🎓", layout="centered", initial_sidebar_state="expanded")  # UI-v2'))

# --- 2 Zeit immer sichtbar ----------------------------------------------------------------------------------
E.append((APP, '''def zeige_zeiten(eintrag):
    """Aufklappbare Zeitübersicht je Antwort ("Gedacht für x Sekunden")."""
    zeiten = eintrag.get("zeiten") or {}
    if not zeiten:
        return
    gesamt = sum(zeiten.values())
    with st.expander(f"⏱ Gedacht für {sek(gesamt)}"):
        for phase, (_, fertig) in PHASEN.items():
            if phase in zeiten:
                st.markdown(f"- {fertig}: **{sek(zeiten[phase])}**")''',
          '''PHASEN_KURZ = {"suche": "Suche", "antwort": "Antwort", "pruefung": "Prüfung"}  # UI-v2


def zeige_zeiten(eintrag):
    """UI-v2: Zeit immer sichtbar – Gesamtzeit und Phasen in einer Zeile."""
    zeiten = eintrag.get("zeiten") or {}
    if not zeiten:
        return
    gesamt = sum(zeiten.values())
    phasen = " · ".join(f"{PHASEN_KURZ.get(p, p)} {sek(zeiten[p])}" for p in PHASEN if p in zeiten)
    st.markdown(f"<div style='font-size:.85rem;opacity:.8;margin:4px 0'>⏱ <b>{sek(gesamt)}</b> &nbsp;·&nbsp; {phasen}</div>",
                unsafe_allow_html=True)'''))

# --- 3 Neutrale Vertrauens-Marken -----------------------------------------------------------------------------
E.append((APP, '        chips.append("✓ im Lernmaterial beantwortet")',
          '        chips.append("📖 Antwort stützt sich auf das Lernmaterial")  # UI-v2: neutral, kein Richtigkeitsversprechen'))
E.append((APP, '    chips.append("✓ passende Textstelle gefunden" if gefunden else "◔ keine eindeutig passende Textstelle – bitte prüfen")',
          '    chips.append("📖 Passende Buchstelle gefunden" if gefunden else "◔ keine eindeutig passende Textstelle – bitte prüfen")  # UI-v2'))
E.append((APP, '            chips = [c for c in chips if not c.startswith("✓")]',
          '            chips = [c for c in chips if not c.startswith(("✓", "📖"))]  # UI-v2'))
E.append((APP, '''        ok = c.startswith("✓")
        farbe = "46,160,67" if ok else "224,140,0"''',
          '''        ok = c.startswith(("✓", "📖"))
        farbe = "140,140,140" if ok else "224,140,0"  # UI-v2: neutral grau statt grün; orange = bitte prüfen'''))

# --- 4 Erste Quelle im Kopf des Quellenkastens ------------------------------------------------------------------
E.append((APP, '    with st.expander(f"📎 Quellen ({len(infos)})"):',
          '''    (b0, s0, t0), *_ = infos[0]  # UI-v2: erste (passendste) Quelle direkt im Kopf
    kopf = " · ".join(x for x in (b0, (t0 or "").split(">")[-1].strip(), f"S. {s0}" if s0 else "") if x)
    with st.expander(f"📎 Quellen: {kopf}" + (f"  (+{len(infos) - 1})" if len(infos) > 1 else "")):'''))

# --- 5 Schrittleiste: vier Schritte, aktueller hervorgehoben ---------------------------------------------------------
E.append((APP, '''def schrittleiste(stufe, hat_idee):
    """Kleine Fortschrittsanzeige: Hinweis → Deine Idee → Lösung."""
    aktiv = 3 if stufe >= 2 else (2 if hat_idee else 1)
    namen = ["Hinweis", "Deine Idee", "Lösung"]
    teile = []
    for i, n in enumerate(namen, start=1):
        if i == 2 and aktiv == 3 and not hat_idee:
            teile.append(f"– {n} (übersprungen)")
        elif i < aktiv:
            teile.append(f"✓ {n}")
        elif i == aktiv:
            teile.append(f"**● {n}**")
        else:
            teile.append(f"○ {n}")
    st.caption("  →  ".join(teile))''',
          '''def schrittleiste(stufe, hat_idee):
    """UI-v2: Lernschritte Hinweis → Dein Versuch → Rückmeldung → Lösung; aktueller Schritt hervorgehoben."""
    namen = ["Hinweis", "Dein Versuch", "Rückmeldung", "Lösung"]
    if stufe >= 2:
        zustand = ["fertig", "fertig" if hat_idee else "aus", "fertig" if hat_idee else "aus", "aktiv"]
    elif hat_idee:
        zustand = ["fertig", "fertig", "aktiv", "offen"]  # Rückmeldung erhalten; weiterer Versuch oder Lösung
    else:
        zustand = ["fertig", "aktiv", "offen", "offen"]
    stil = {"fertig": ("✓", "rgba(140,140,140,.18)", "rgba(140,140,140,.5)", "1"),
            "aktiv": ("●", "rgba(255,153,0,.22)", "rgba(255,153,0,.9)", "1"),
            "offen": ("○", "transparent", "rgba(140,140,140,.4)", ".6"),
            "aus": ("–", "transparent", "rgba(140,140,140,.3)", ".45")}
    teile = []
    for i, (n, z) in enumerate(zip(namen, zustand), start=1):
        sym, bg, rand, op = stil[z]
        fett = "font-weight:600;" if z == "aktiv" else ""
        teile.append(f"<span style='display:inline-block;margin:2px 4px 2px 0;padding:2px 10px;border-radius:12px;"
                     f"font-size:.8rem;background:{bg};border:1px solid {rand};opacity:{op};{fett}'>{sym} {i} {n}</span>")
    st.markdown("".join(teile), unsafe_allow_html=True)'''))

# --- 6 Hauptaktion: Idee prüfen ---------------------------------------------------------------------------------
E.append((APP, '    if st.button("Idee prüfen lassen", key=f"btn_idee_{idx}_{n}"):',
          '    if st.button("Idee prüfen lassen", key=f"btn_idee_{idx}_{n}", type="primary"):  # UI-v2: Hauptaktion'))

# --- 7 Lösung einklappen, solange die Übungsfrage beantwortet wird --------------------------------------------------
_ALT_LOESUNG = '''            if aktuelle_stufe >= 2:
                zeige_loesung(eintrag["loesung"], {"markiert": True, "ersetzt": "ersetzt", "denkmodus": "denkmodus", "ungeprueft": "ungeprueft"}.get(eintrag.get("rechen_pruefung"), False))
'''
E.append((APP, _ALT_LOESUNG, '''            if aktuelle_stufe >= 2:
                _mk = {"markiert": True, "ersetzt": "ersetzt", "denkmodus": "denkmodus", "ungeprueft": "ungeprueft"}.get(eintrag.get("rechen_pruefung"), False)
                _ue = st.session_state.get(f"uebung_{idx}") or {}
                if _ue.get("u") and not _ue.get("fb"):  # UI-v2: während der Übungsfrage eingeklappt
                    with st.expander("✅ Lösung (eingeklappt, solange du die Übungsfrage beantwortest)"):
                        zeige_loesung(eintrag["loesung"], _mk)
                else:
                    zeige_loesung(eintrag["loesung"], _mk)
'''))

# --- 8 Versionsanzeige RP-v13 --------------------------------------------------------------------------------------
E.append((APP, 'Rechenprüfung {_rp.RECHEN_PRUEFUNG_VERSION}',
          "Rechenprüfung {'RP-v13' if getattr(_rp, 'RP_V13', False) else _rp.RECHEN_PRUEFUNG_VERSION}"))

# --- 9 Chatseite mit Seitenleiste (Verlauf, Sitzungsübersicht, Infos) und Startbeispielen ------------------------------
_ALT_CHAT_KOPF = '''def seite_chat():
    st.title(f"🎓 {APP_NAME}")
    st.caption(f"Sitzung: {st.session_state['sitzungs_id']}")
    st.checkbox("Lösung sofort anzeigen (Demo)", key="loesung_direkt",
                help="Zeigt Hinweis und Lösung gleichzeitig. Aus = Hinweis zuerst, Lösung auf Klick (Studienablauf).")

    with st.expander("📚 Verfügbare Themen"):
        themen = sorted(set(c["thema"] for c in CHUNKS))
        st.write(", ".join(themen))

    with st.expander("ℹ️ Wie funktioniert die Antwort?"):
        st.write(
            "Du bekommst zuerst nur einen **Hinweis** — versuch, damit selbst "
            "weiterzukommen. Wenn du magst, schreib **deine Idee** auf: Der Assistent "
            "sagt dir, was daran schon stimmt und worüber du noch nachdenken kannst, "
            "ohne die Lösung zu verraten. Du kannst bis zu drei Ideen ausprobieren. "
            "Wenn du nicht weiterkommst, zeig dir die **Lösung mit Begründung** an."
        )

    zeige_ueber()
    if _os.environ.get("LERNASSISTENT_DEV") == "1" or st.query_params.get("dev") == "1":
        with st.expander("📊 Nutzungsauswertung (Entwicklermodus)"):
            zeige_dashboard()

    anzahl = len(st.session_state["verlauf"])
    for idx, eintrag in enumerate(st.session_state["verlauf"]):
        zeige_eintrag(idx, eintrag, ist_letzter=(idx == anzahl - 1))
'''
_NEU_CHAT_KOPF = '''# UI-v2: Beispiele auf der leeren Startseite (abschalten: LERNASSISTENT_BEISPIELE=0)
BEISPIELE = [
    "Warum nimmt man für Spulen im kHz-Bereich keine geblechten Eisenkerne mehr?",
    "Auf dem Leistungsschild eines Verteiltransformators steht die Schaltgruppe Yzn 5. Was bedeuten die Buchstaben und die Kennzahl?",
    "Wie heißt die Fläche am Schneidkeil, über die der Span abläuft?",
    "Zwei Rohre (d = 40 mm) werden durch eine Überlappungsklebung verbunden und mit dem Torsionsmoment MT = 50 Nm belastet. "
    "Die Bindefestigkeit des Klebstoffs beträgt KB = 20 N/mm², die Sicherheit bei wechselnder Beanspruchung S = 4. "
    "Welche Überlappungslänge b ist mindestens erforderlich?",
]


def _ist_dev():
    return _os.environ.get("LERNASSISTENT_DEV") == "1" or st.query_params.get("dev") == "1"


def _symbol(e):
    """Symbol im Verlauf: abgelehnt, teilweise, Rechnung, sonst Frage."""
    if e.get("status") in ("GATE", "NICHT_IM_MATERIAL"):
        return "🔎"
    if e.get("status") == "TEILWEISE":
        return "◐"
    if e.get("rechen_pruefung"):
        return "🧮"
    return "💬"


def _kurz(text, n=38):
    t = " ".join(str(text or "").split())
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def zeige_hinweis_nutzung(h, kompakt=False):
    """UI-v2: Kennzahlen zum Umgang mit dem Hinweis (Seitenleiste kompakt, Auswertung ausführlich)."""
    n = h["fragen"]
    if kompakt:
        st.markdown(
            f"<div style='font-size:.85rem;line-height:1.7'>✍️ Selbst versucht: <b>{h['versucht']}/{n}</b><br>"
            f"🎯 Mit Hinweis gelöst: <b>{h['geloest']}/{n}</b><br>"
            f"⏭ Direkt zur Lösung: <b>{h['direkt']}/{n}</b></div>", unsafe_allow_html=True)
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Selbst versucht", f"{h['versucht']}/{n}", help="Fragen mit mindestens einer Idee, bevor die Lösung geöffnet wurde")
    c2.metric("Mit Hinweis gelöst", f"{h['geloest']}/{n}", help="Eine Idee wurde vor dem Öffnen der Lösung als richtig beurteilt")
    c3.metric("Nach Rückmeldung besser", f"{h['verbessert']}/{h['mehrere']}",
              help="Unter Fragen mit mehreren Ideen: eine spätere Idee wurde besser beurteilt als die vorherige")
    c4.metric("Direkt zur Lösung", f"{h['direkt']}/{n}", help="Lösung geöffnet, ohne vorher eine Idee aufzuschreiben")
    if h["versucht"]:
        st.caption(f"Urteil über den ersten Versuch (Ø {h['versuche_mittel']} Ideen je Frage vor der Lösung)")
        st.bar_chart(h["erster"])


def seitenleiste():
    """UI-v2: Seitenleiste wie in Chat-Anwendungen – Verlauf (neueste oben, mit Zeit), Sitzungsübersicht, Infos."""
    verlauf = st.session_state["verlauf"]
    fokus = st.session_state.get("fokus")
    with st.sidebar:
        st.markdown(f"### 🎓 {APP_NAME}")
        st.caption(f"Sitzung: {st.session_state['sitzungs_id']}")
        c1, c2 = st.columns(2)
        if c1.button("📋 Alle Fragen", width="stretch", disabled=fokus is None):
            st.session_state["fokus"] = None
            st.rerun()
        if c2.button("🗑 Neu starten", width="stretch", disabled=not verlauf,
                     help="Leert den Verlauf auf dem Bildschirm (das Protokoll bleibt erhalten)."):
            for k in [k for k in st.session_state if k.startswith(("stufe_", "ideen_", "idee_text_", "folge_", "uebung_"))]:
                del st.session_state[k]
            st.session_state["verlauf"] = []
            st.session_state["bilder"], st.session_state["bild_meta"] = {}, {}
            st.session_state["fokus"] = None
            st.rerun()

        st.markdown("**Verlauf**")
        if not verlauf:
            st.caption("Noch keine Fragen.")
        for i in range(len(verlauf) - 1, -1, -1):
            e = verlauf[i]
            t = sum((e.get("zeiten") or {}).values())
            if st.button(f"{_symbol(e)} {_kurz(e.get('frage'))}" + (f" · {sek(t)}" if t else ""), key=f"verlauf_{i}",
                         width="stretch", type="primary" if fokus == i else "secondary", help=str(e.get("frage") or "")):
                st.session_state["fokus"] = i
                st.rerun()

        if verlauf:
            st.markdown("**Diese Sitzung**")
            zeiten = [sum((e.get("zeiten") or {}).values()) for e in verlauf if e.get("zeiten")]
            im_buch = sum(e.get("status") in ("BEANTWORTET", "TEILWEISE") for e in verlauf)
            geoeffnet = sum(st.session_state.get(f"stufe_{i}", 1) >= 2 for i in range(len(verlauf)))
            ideen = sum(len(st.session_state.get(f"ideen_{i}", [])) for i in range(len(verlauf)))
            m1, m2 = st.columns(2)
            m1.metric("Fragen", len(verlauf))
            m2.metric("Ø Zeit", sek(sum(zeiten) / len(zeiten)) if zeiten else "–")
            m3, m4 = st.columns(2)
            m3.metric("Im Buch belegt", f"{im_buch}/{len(verlauf)}")
            m4.metric("Eigene Ideen", ideen)
            st.caption(f"Lösung geöffnet: {geoeffnet}/{len(verlauf)} · abgelehnt (nicht im Buch): {len(verlauf) - im_buch}")
            h = lernhilfen.hinweis_nutzung([
                (st.session_state.get(f"stufe_{i}", 1) >= 2,
                 [(x.get("stufe"), x.get("urteil")) for x in st.session_state.get(f"ideen_{i}", [])])
                for i, e in enumerate(verlauf) if e.get("status") in ("BEANTWORTET", "TEILWEISE")])
            if h["fragen"]:
                st.markdown("**Umgang mit dem Hinweis**")
                zeige_hinweis_nutzung(h, kompakt=True)

        st.divider()
        st.checkbox("Lösung sofort anzeigen (Demo)", key="loesung_direkt",
                    help="Zeigt Hinweis und Lösung gleichzeitig. Aus = Hinweis zuerst, Lösung auf Klick (Studienablauf).")
        with st.expander("📚 Verfügbare Themen"):
            themen = sorted(set(c["thema"] for c in CHUNKS))
            st.write(", ".join(themen))
        with st.expander("ℹ️ Wie funktioniert die Antwort?"):
            st.write(
                "Du bekommst zuerst nur einen **Hinweis** — versuch, damit selbst "
                "weiterzukommen. Wenn du magst, schreib **deine Idee** auf: Der Assistent "
                "sagt dir, was daran schon stimmt und worüber du noch nachdenken kannst, "
                "ohne die Lösung zu verraten. Du kannst bis zu drei Ideen ausprobieren. "
                "Wenn du nicht weiterkommst, zeig dir die **Lösung mit Begründung** an."
            )
        zeige_ueber()
        if _ist_dev():
            with st.expander("📊 Nutzungsauswertung (Entwicklermodus)"):
                zeige_dashboard()


def willkommen():
    """UI-v2: leere Startseite mit kurzer Erklärung und anklickbaren Beispielfragen."""
    st.markdown("Stell eine Frage zur **Elektrotechnik** oder zum **Maschinenbau**. Du bekommst zuerst einen "
                "**Hinweis** und kannst selbst eine Idee aufschreiben; die **Lösung** mit den Buchstellen gibt es auf Klick.")
    if _os.environ.get("LERNASSISTENT_BEISPIELE", "1") == "0":
        return
    st.caption("Zum Ausprobieren:")
    spalten = st.columns(2)
    for j, q in enumerate(BEISPIELE):
        if spalten[j % 2].button(q, key=f"bsp_{j}", width="stretch"):
            st.session_state["naechste_frage"] = q
            st.rerun()


def seite_chat():
    seitenleiste()  # UI-v2
    st.title(f"🎓 {APP_NAME}")
    verlauf = st.session_state["verlauf"]
    anzahl = len(verlauf)
    fokus = st.session_state.get("fokus")
    if fokus is not None and not (0 <= fokus < anzahl):
        fokus = st.session_state["fokus"] = None
    if not verlauf:
        willkommen()
    if fokus is None:
        for idx, eintrag in enumerate(verlauf):
            zeige_eintrag(idx, eintrag, ist_letzter=(idx == anzahl - 1))
    else:
        st.caption(f"Frage {fokus + 1} von {anzahl} (aus dem Verlauf) · „📋 Alle Fragen“ zeigt wieder alle.")
        zeige_eintrag(fokus, verlauf[fokus], ist_letzter=(fokus == anzahl - 1))
'''
E.append((APP, _ALT_CHAT_KOPF, _NEU_CHAT_KOPF))
E.append((APP, '''        st.session_state["verlauf"].append(ergebnis)
        st.rerun()''', '''        st.session_state["verlauf"].append(ergebnis)
        st.session_state["fokus"] = None  # UI-v2: neue Frage -> alle zeigen
        st.rerun()'''))
E.append((APP, '''    st.caption(f"Konfiguration: {_os.path.basename(KB_PFAD)} · {RETRIEVAL} · {_rp.SCAFFOLDING_VERSION}")''',
          '''    if _ist_dev():  # UI-v2: technische Angaben nur im Entwicklermodus
        st.caption(f"Konfiguration: {_os.path.basename(KB_PFAD)} · {RETRIEVAL} · {_rp.SCAFFOLDING_VERSION}")'''))
E.append((APP, '        if st.button("Zur Bewertung →", type="primary", disabled=len(st.session_state["verlauf"]) == 0):',
          '        if st.button("Feedback zum Lernassistenten →", disabled=len(st.session_state["verlauf"]) == 0):  # UI-v2'))

E.append((APP, "    col1, col2 = st.columns([3, 1])", "    col1, col2 = st.columns([3, 2])  # UI-v2: Platz für den längeren Knopftext"))

# --- 10 Übungsfrage: anderer Aspekt ---------------------------------------------------------------------------------
E.append((LH, "- Es darf nicht dieselbe Frage sein wie die gestellte.\n",
          "- Es darf nicht dieselbe Frage sein wie die gestellte.\n"
          "- Frage nach einem anderen Aspekt des Lernmaterials als die gestellte Frage (nicht nach derselben Ursache oder Begründung).\n"))

# --- 11 "du hast gesehen/gelesen" als Verweis auf unsichtbares Material (HP-v4/FP-v3) -----------------------------------
E.append((RP, r'''r"|\bsuch\w*\s+(?:in|im|nach)\b|\bnach\b[^.?!]{0,60}?\bsuch\w*|\bwas siehst du\b", re.I)''',
          r'''r"|\bsuch\w*\s+(?:in|im|nach)\b|\bnach\b[^.?!]{0,60}?\bsuch\w*|\bwas siehst du\b"
    r"|\bdu hast (?:\w+ ){0,2}(?:gesehen|gelesen)\b", re.I)  # UI-v2: "Du hast gesehen, dass …" (Lernende sehen das Material nicht)'''))


# --- 12 Startseite: "So funktioniert's" in vier Schritten, nur Name, kein Häkchen ---------------------------------------
E.append((APP, "def seite_start():" + '\n    st.title(f"🎓 {APP_NAME} für die technische Ausbildung")\n    st.write(\n        "Willkommen! Dieser Lernassistent beantwortet Fragen zu ausgewählten "\n        "Themen der technischen Ausbildung (siehe Liste der verfügbaren Themen im Chat) "\n        "auf Basis geprüfter Lernmaterialien."\n    )\n\n    with st.expander("ℹ️ Hinweise zur Teilnahme", expanded=True):\n        st.markdown(\n            "- Deine Eingaben werden **pseudonymisiert** gespeichert (über die Sitzungs-ID unten), "\n            "nicht mit deinem Namen verknüpft.\\n"\n            "- Fragen, Antworten, deine eingegebenen Ideen und deine Bewertung im Abschlussfragebogen werden für die "\n            "wissenschaftliche Auswertung dieser Pilotstudie verwendet.\\n"\n            "- **Alles läuft lokal** auf dem Rechner der Studie: keine Daten gehen an externe Dienste oder Cloud-KI.\\n"\n            "- Protokolliert werden nur Sitzungs-ID, Zeitpunkt, Frage, Antwort, deine Idee und deine Bewertung – "\n            "keine Namen, keine IP-Adressen.\\n"\n            "- Du kannst die Teilnahme jederzeit ohne Angabe von Gründen abbrechen.\\n"\n            "- Der Assistent antwortet **nur** auf Basis der hinterlegten Lernmaterialien. "\n            "Findet er keine passende Quelle, sagt er das ehrlich, statt zu raten."\n        )\n\n    st.text_input(\n        "Sitzungs-ID (z. B. von deiner Lehrkraft vergeben, kein Klarname):",\n        key="sitzungs_id_eingabe",\n        value="TEST-Demo",  # TEST-Präfix: Demo-Sitzungen lassen sich aus interaktionen.csv herausfiltern\n        placeholder="z. B. TN-07",\n    )\n\n    einverstanden = st.checkbox("Ich habe die Hinweise gelesen und bin mit der Teilnahme einverstanden.")\n\n    if st.button("Starten", type="primary", disabled=not einverstanden):\n        eingabe = st.session_state.get("sitzungs_id_eingabe", "").strip()\n        if not eingabe:\n            st.error("Bitte gib eine Sitzungs-ID ein.")\n        else:\n            st.session_state["sitzungs_id"] = eingabe\n            st.session_state["seite"] = "chat"\n            st.rerun()', '''def seite_start():
    """UI-v2: kurze Startseite – so funktioniert's in vier Schritten, Name eingeben, los."""
    st.title(f"🎓 {APP_NAME}")
    st.markdown("Dein Lernbegleiter für **Elektrotechnik** und **Maschinenbau**. "
                "Er verrät nicht sofort die Lösung, sondern hilft dir, **selbst draufzukommen**.")
    schritte = [("❓", "Frage stellen", "zu einem Thema aus deinen Fachbüchern"),
                ("💡", "Hinweis lesen", "ein Denkanstoß – noch nicht die Lösung"),
                ("✍️", "Idee aufschreiben", "du bekommst eine kurze Rückmeldung"),
                ("📖", "Lösung ansehen", "mit Begründung und Buchseite")]
    karten = "".join(
        f"<div style='flex:1 1 140px;padding:12px 12px 10px;border-radius:12px;border:1px solid rgba(140,140,140,.3);"
        f"background:rgba(140,140,140,.07)'><div style='font-size:1.6rem;line-height:1'>{sym}</div>"
        f"<div style='font-weight:600;margin-top:6px'><span style='opacity:.55'>{i}.</span> {titel}</div>"
        f"<div style='font-size:.82rem;opacity:.75;margin-top:2px'>{text}</div></div>"
        for i, (sym, titel, text) in enumerate(schritte, start=1))
    st.markdown(f"<div style='display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 6px'>{karten}</div>",
                unsafe_allow_html=True)
    st.caption("Steht etwas nicht in den Büchern, sagt der Assistent das ehrlich, statt zu raten. "
               "🔒 Alles läuft lokal auf diesem Rechner.")
    st.text_input("Dein Name", key="sitzungs_id_eingabe", placeholder="z. B. Alex", max_chars=40)
    if st.button("Los geht's →", type="primary"):
        eingabe = st.session_state.get("sitzungs_id_eingabe", "").strip()
        if not eingabe:
            st.error("Bitte gib deinen Namen ein.")
        else:
            st.session_state["sitzungs_id"] = eingabe
            st.session_state["seite"] = "chat"
            st.rerun()'''))

# --- 13 Statistik: Wie gehen Lernende mit dem Hinweis um? (Seitenleiste + Entwickler-Auswertung) --------------------
E.append((LH, "def auswertung(sitzung=None):", '''URTEIL_RANG = {"keine_idee": 0, "falsch": 1, "teilweise": 2, "richtig": 3}  # UI-v2


def hinweis_nutzung(fragen):
    """UI-v2: Umgang mit dem Hinweis. fragen = Liste (loesung_geoeffnet, [(stufe_beim_versuch, urteil), ...]),
    nur Fragen mit Hinweis (Status BEANTWORTET/TEILWEISE). Versuche auf Stufe 1 = vor dem Öffnen der Lösung."""
    n = len(fragen)
    versucht = geloest = direkt = mehrere = verbessert = 0
    erster = {"richtig": 0, "teilweise": 0, "falsch": 0, "keine_idee": 0}
    anzahl = []
    for geoeffnet, ideen in fragen:
        vor = [u for s, u in ideen if str(s) == "1"]
        if not vor:
            direkt += bool(geoeffnet)
            continue
        versucht += 1
        anzahl.append(len(vor))
        erster[vor[0]] = erster.get(vor[0], 0) + 1
        geloest += "richtig" in vor
        if len(vor) > 1:
            mehrere += 1
            r = [URTEIL_RANG.get(u, 0) for u in vor]
            verbessert += any(r[i] > r[i - 1] for i in range(1, len(r)))
    return {"fragen": n, "versucht": versucht, "geloest": geloest, "direkt": direkt,
            "mehrere": mehrere, "verbessert": verbessert, "erster": erster,
            "versuche_mittel": round(sum(anzahl) / len(anzahl), 1) if anzahl else 0}


def auswertung(sitzung=None):'''))
E.append((LH, '''        "status": status, "ideen": len(ideen), "urteile": urteile, "hilfen": typen,''',
          '''        "status": status, "ideen": len(ideen), "urteile": urteile, "hilfen": typen,
        "hinweis": _hinweis_aus_log(inter, ideen, je_frage),  # UI-v2'''))
E.append((LH, "def lies_csv(pfad):", '''def _hinweis_aus_log(inter, ideen, je_frage):
    """UI-v2: hinweis_nutzung() aus interaktionen.csv + ideen_feedback.csv (Schlüssel: Sitzung + Fragetext)."""
    mit_hinweis = [(r.get("sitzungs_id"), r.get("frage")) for r in inter
                   if str(r.get("scaffolding_stufe_erreicht")) == "1" and r.get("status") in ("BEANTWORTET", "TEILWEISE")]
    je_idee = {}
    for r in ideen:
        je_idee.setdefault((r.get("sitzungs_id"), r.get("frage")), []).append(r)
    fragen = []
    for k in dict.fromkeys(mit_hinweis):
        reihe = sorted(je_idee.get(k, []), key=lambda r: int(r.get("versuch_nr") or 0))
        fragen.append((je_frage.get(k, 1) >= 2, [(r.get("stufe_beim_versuch"), r.get("urteil")) for r in reihe]))
    return hinweis_nutzung(fragen)


def lies_csv(pfad):'''))
E.append((APP, '''    if a["hilfen"]:
        st.caption("Lernhilfen: "''', '''    if a.get("hinweis", {}).get("fragen"):  # UI-v2
        st.markdown("**Umgang mit dem Hinweis**")
        zeige_hinweis_nutzung(a["hinweis"])
    if a["hilfen"]:
        st.caption("Lernhilfen: "'''))


def main():
    texte = {p: p.read_text(encoding="utf-8") for p in (APP, LH, RP)}
    if any(MARKE in t for t in texte.values()):  # frühere UI-v2-Fassung: vom Stand davor (*.vor_ui2) neu aufbauen
        for p in texte:
            if MARKE in texte[p]:
                b = p.with_name(p.name + ".vor_ui2")
                if not b.exists():
                    print(f"FEHLER: {p.name} enthält UI-v2, aber {b.name} fehlt – nichts geändert.")
                    return 1
                texte[p] = b.read_text(encoding="utf-8")
        print("Frühere UI-v2-Fassung gefunden – wird aus den Sicherungen *.vor_ui2 neu eingespielt.")
    fehlt = []
    for p, alt, _ in E:
        n = texte[p].count(alt)
        if n != 1:
            fehlt.append(f"{p.name}: Anker {'fehlt' if n == 0 else f'{n}x'}: {alt.strip().splitlines()[0][:80]}")
    if fehlt:
        print("FEHLER – nichts geändert (unerwarteter Stand):")
        print("\n".join("  " + f for f in fehlt))
        return 1
    neu = dict(texte)
    for p, alt, ers in E:
        neu[p] = neu[p].replace(alt, ers, 1)
    for p in neu:
        compile(neu[p], str(p), "exec")  # Syntax prüfen, bevor geschrieben wird
    for p in neu:
        if neu[p] != p.read_text(encoding="utf-8"):
            if MARKE not in p.read_text(encoding="utf-8"):  # Sicherung nur vom Stand ohne UI-v2
                shutil.copy2(p, p.with_name(p.name + ".vor_ui2"))
            p.write_text(neu[p], encoding="utf-8")
            print(f"geändert: {p} (Sicherung {p.name}.vor_ui2)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
