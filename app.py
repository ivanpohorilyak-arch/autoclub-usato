import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime, timedelta
import time
from io import BytesIO
import re
import cv2
import numpy as np
from streamlit_autorefresh import st_autorefresh
import qrcode
from PIL import Image

# --- 1. CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. CREDENZIALI & TIMEOUT ---
CREDENZIALI = {"Luca Simonini": "2026", "Ivan Pohorilyak": "1234", "Abdul": "0000"}
TIMEOUT_MINUTI = 15

# --- 3. CONFIGURAZIONE ZONE BLINDATE ---
ZONE_INFO = {
    "Z01": "Deposito N.9", "Z02": "Deposito N.7", "Z03": "Deposito N.6 (Lavaggisti)",
    "Z04": "Deposito unificato 1 e 2", "Z05": "Showroom", "Z06": "Vetture vendute",
    "Z07": "Piazzale Lavaggio", "Z08": "Commercianti senza telo",
    "Z09": "Commercianti con telo", "Z10": "Lavorazioni esterni", "Z11": "Verso altre sedi"
}

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1", layout="wide")

# --- 4. GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'last_action' not in st.session_state:
    st.session_state['last_action'] = datetime.now()
if 'zona_id' not in st.session_state: st.session_state['zona_id'] = ""
if 'zona_nome' not in st.session_state: st.session_state['zona_nome'] = ""
if 'zona_id_sposta' not in st.session_state: st.session_state['zona_id_sposta'] = ""
if 'zona_nome_sposta' not in st.session_state: st.session_state['zona_nome_sposta'] = ""
if 'camera_attiva' not in st.session_state:
    st.session_state['camera_attiva'] = False

def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now()

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now() - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state['user_autenticato'] = None
            st.rerun()

# --- 5. FUNZIONI CORE ---
def registra_log(targa, azione, dettaglio, utente):
    try:
        supabase.table("log_movimenti").insert({
            "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente
        }).execute()
    except Exception as e:
        st.error(f"Errore Log: {e}")

def get_marche():
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        marche = {r["marca_modello"].split()[0].upper() for r in res.data if r.get("marca_modello")}
        return sorted(list(marche))
    except: return []

def get_modelli(marca):
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        modelli = {r["marca_modello"].upper().replace(marca.upper(), "").strip() for r in res.data if r.get("marca_modello") and r["marca_modello"].upper().startswith(marca.upper())}
        return sorted([m for m in modelli if m])
    except: return []

def get_colori():
    try:
        res = supabase.table("parco_usato").select("colore").execute()
        colori = {str(r['colore']).capitalize() for r in res.data if r.get('colore')}
        return sorted(list(colori)) if colori else ["Bianco", "Nero", "Grigio"]
    except: return ["Bianco", "Nero", "Grigio"]

def suggerisci_colore(targa_input):
    try:
        if len(targa_input) >= 7:
            res = supabase.table("parco_usato").select("colore").eq("targa", targa_input).order("created_at", desc=True).limit(1).execute()
            if res.data: return str(res.data[0]['colore']).capitalize()
        return None
    except: return None

def leggi_qr_zona(image_file):
    try:
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if not data or not data.startswith("ZONA|"): return None
        z_id = data.replace("ZONA|", "").strip()
        return z_id if z_id in ZONE_INFO else None
    except: return None

controllo_timeout()

# --- 6. LOGIN ---
if st.session_state['user_autenticato'] is None:
    st.title("🔐 Accesso Autoclub Center Usato")
    u = st.selectbox("Operatore", ["- Seleziona -"] + list(CREDENZIALI.keys()))
    p = st.text_input("PIN", type="password")
    if st.button("ACCEDI"):
        if u != "- Seleziona -" and p == CREDENZIALI.get(u):
            st.session_state['user_autenticato'] = u
            aggiorna_attivita(); st.rerun()
        else: st.error("Accesso negato")
else:
    # --- 7. SIDEBAR ---
    utente_attivo = st.session_state['user_autenticato']
    with st.sidebar:
        st.info(f"👤 {utente_attivo}")
        st.sidebar.markdown("### 📷 Scanner QR")
        st.checkbox("Attiva scanner", key="camera_attiva")
        if st.button("Log-out"): st.session_state.clear(); st.rerun()

    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", "📋 Verifica Zone", "📊 Dashboard Zone", "📊 Export", "📜 Log", "🖨️ Stampa QR", "♻️ Ripristina"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")

    if scelta not in ["➕ Ingresso", "🔍 Ricerca/Sposta"]:
        st.session_state["zona_id"] = ""; st.session_state["zona_nome"] = ""
        st.session_state["zona_id_sposta"] = ""; st.session_state["zona_nome_sposta"] = ""

    # --- 8. SEZIONE INGRESSO ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Registrazione Nuova Vettura")
        if st.session_state.camera_attiva:
            foto_z = st.camera_input("Scansiona QR della Zona", key="cam_in")
            if foto_z:
                z_id = leggi_qr_zona(foto_z)
                if z_id:
                    st.session_state["zona_id"] = z_id
                    st.session_state["zona_nome"] = ZONE_INFO[z_id]
                    st.success(f"✅ Zona rilevata: {st.session_state['zona_nome']}")
                else: st.error("❌ QR non valido")
        else:
            st.warning("⚠️ Scanner disattivato dalla Sidebar. Attivalo per leggere la zona.")

        with st.form("f_ingresso", clear_on_submit=True):
            if not st.session_state['zona_id']: st.error("❌ Scansione QR Obbligatoria")
            else: st.info(f"📍 Zona selezionata: **{st.session_state['zona_nome']}**")
            
            targa = st.text_input("TARGA").upper().strip()
            marche = get_marche()
            m_sel = st.selectbox("Marca", ["Nuova..."] + marche)
            if m_sel == "Nuova...": m_sel = st.text_input("Inserisci Marca").upper()
            mod_sel = st.selectbox("Modello", ["Nuovo..."] + get_modelli(m_sel))
            if mod_sel == "Nuovo...": mod_sel = st.text_input("Inserisci Modello").upper()
            
            c_sug = suggerisci_colore(targa) if targa else None
            if c_sug: st.info(f"🎨 Suggerito: **{c_sug}**")
            colore = st.selectbox("Colore", ["Nuovo..."] + get_colori())
            if colore == "Nuovo...": colore = st.text_input("Specifica Colore")
            
            km = st.number_input("Chilometri", min_value=0, step=100)
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1)
            if n_chiave == 0: st.info("🤝 Valore 0 = Vetture destinate ai commercianti")
            note = st.text_area("Note")

            if st.form_submit_button("REGISTRA"):
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa): st.warning("Targa non valida")
                else:
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data: st.error("❌ Vettura già presente!")
                    else:
                        data = {"targa": targa, "marca_modello": f"{m_sel} {mod_sel}".strip(), "colore": colore.strip().capitalize(), "km": km, "numero_chiave": n_chiave, "zona_id": st.session_state["zona_id"], "zona_attuale": st.session_state["zona_nome"], "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
                        st.success("✅ Vettura registrata correttamente!")
                        st.session_state["zona_id"] = ""; st.session_state["zona_nome"] = ""
                        time.sleep(1); st.rerun()

    # --- 9. SEZIONE RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Spostamento")
        if st.session_state.camera_attiva:
            foto_sp = st.camera_input("Scansiona QR Nuova Zona", key="cam_sp")
            if foto_sp:
                z_id_sp = leggi_qr_zona(foto_sp)
                if z_id_sp:
                    st.session_state["zona_id_sposta"] = z_id_sp
                    st.session_state["zona_nome_sposta"] = ZONE_INFO[z_id_sp]
                    st.info(f"✅ Destinazione: {st.session_state['zona_nome_sposta']}")
                else: st.error("❌ QR non valido")
        else: st.warning("⚠️ Scanner disattivato dalla Sidebar.")

        tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
        q = st.text_input("Dato da cercare").strip()
        if q:
            col = "targa" if tipo == "Targa" else "numero_chiave"
            val = q.upper() if tipo == "Targa" else int(q) if q.isdigit() else None
            if val is not None:
                res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute()
                if res.data:
                    for v in res.data:
                        with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                            st.write(f"📍 Posizione attuale: **{v['zona_attuale']}**")
                            c1, c2 = st.columns(2)
                            if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not st.session_state['zona_id_sposta']):
                                supabase.table("parco_usato").update({"zona_id": st.session_state["zona_id_sposta"], "zona_attuale": st.session_state["zona_nome_sposta"]}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {st.session_state['zona_nome_sposta']}", utente_attivo)
                                st.session_state["zona_id_sposta"] = ""; st.session_state["zona_nome_sposta"] = ""
                                st.success("✅ Spostata!"); time.sleep(1); st.rerun()

                            with c2:
                                conf_key = f"conf_{v['targa']}_{v.get('zona_id', 'NA')}"
                                if conf_key not in st.session_state: st.session_state[conf_key] = False
                                st.checkbox("⚠️ Confermo CONSEGNA DEFINITIVA", key=conf_key)
                                if st.button("🔴 CONSEGNA DEFINITIVA", key=f"btn_{v['targa']}", disabled=not st.session_state[conf_key]):
                                    supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                    registra_log(v['targa'], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                    st.success("✅ CONSEGNA REGISTRATA"); time.sleep(1); st.rerun()

    # --- 10. MODIFICA ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("Correzione Dati")
        t_mod = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True, key="m_t")
        q_mod = st.text_input("Inserisci valore").strip()
        if q_mod:
            col_f = "targa" if t_mod == "Targa" else "numero_chiave"
            val_f = q_mod.upper() if t_mod == "Targa" else int(q_mod) if q_mod.isdigit() else None
            res = supabase.table("parco_usato").select("*").eq(col_f, val_f).eq("stato", "PRESENTE").execute()
            if res.data:
                v = res.data[0]
                with st.form("f_mod"):
                    z_nome_sel = st.selectbox("Zona", list(ZONE_INFO.values()), index=list(ZONE_INFO.values()).index(v['zona_attuale']) if v['zona_attuale'] in ZONE_INFO.values() else 0)
                    z_id_sel = next(k for k, val in ZONE_INFO.items() if val == z_nome_sel)
                    upd = {"targa": st.text_input("Targa", value=v['targa']).upper().strip(), "marca_modello": st.text_input("Modello", value=v['marca_modello']).upper(), "colore": st.text_input("Colore", value=v['colore']).strip().capitalize(), "km": st.number_input("KM", value=int(v['km'])), "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])), "zona_id": z_id_sel, "zona_attuale": z_nome_sel, "note": st.text_area("Note", value=v['note'])}
                    if st.form_submit_button("SALVA"):
                        supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                        registra_log(upd["targa"], "Modifica", "Correzione", utente_attivo); st.success("✅ Salvato!"); time.sleep(1); st.rerun()

    # --- 11. ALTRE FUNZIONI & CORREZIONE DATA ---
    elif scelta == "📊 Dashboard Zone":
        st.subheader("📍 Movimenti per Zona")
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        if z_sel:
            res = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[z_sel]}%").order("created_at", desc=True).limit(100).execute()
            if res.data:
                df = pd.DataFrame(res.data)
                df["Ora"] = pd.to_datetime(df["created_at"]).dt.strftime("%d/%m/%Y %H:%M") # FORMATO DATA CORRETTO
                st.metric("Movimenti", len(df))
                st.dataframe(df[["Ora", "targa", "azione", "utente"]], use_container_width=True)

    elif scelta == "📊 Export":
        aggiorna_attivita()
        try:
            res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
            if res.data:
                df = pd.DataFrame(res.data)
                df["Data Inserimento"] = pd.to_datetime(df["created_at"]).dt.strftime("%d/%m/%Y %H:%M") # FORMATO DATA CORRETTO
                df = df.drop(columns=["id", "stato", "created_at"], errors="ignore")
                out = BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as w: df.to_excel(w, index=False)
                st.download_button("📥 Scarica Report", out.getvalue(), f"Piazzale_{datetime.now().strftime('%d_%m')}.xlsx")
        except: st.error("❌ Errore Export")

    elif scelta == "📜 Log":
        st_autorefresh(interval=10000, key="log_ref")
        logs = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(50).execute()
        if logs.data:
            df_l = pd.DataFrame(logs.data)
            df_l['Ora'] = pd.to_datetime(df_l['created_at']).dt.strftime('%d/%m/%Y %H:%M') # FORMATO DATA CORRETTO
            st.dataframe(df_l[["Ora", "targa", "azione", "utente"]], use_container_width=True)

    elif scelta == "🖨️ Stampa QR":
        z_pr = st.selectbox("Zona QR", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        if z_pr:
            qr_img = qrcode.make(f"ZONA|{z_pr}"); buf = BytesIO(); qr_img.save(buf, format="PNG")
            st.image(buf.getvalue(), width=300); st.download_button("Scarica QR", buf.getvalue(), f"QR_{z_pr}.png")

    elif scelta == "♻️ Ripristina":
        st.subheader("♻️ Ripristino Vetture Consegnate")
        targa_back = st.text_input("Targa da ripristinare").upper().strip()
        if targa_back:
            res = supabase.table("parco_usato").select("*").eq("targa", targa_back).eq("stato", "CONSEGNATO").execute()
            if res.data:
                v = res.data[0]
                st.warning(f"Trovata: {v['marca_modello']} consegnata da {v['zona_attuale']}")
                if st.button(f"RIPRISTINA {targa_back} NEL PIAZZALE"):
                    supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", targa_back).execute()
                    registra_log(targa_back, "Ripristino", "Riportata in PRESENTE", utente_attivo)
                    st.success(f"✅ Vettura {targa_back} ripristinata!"); time.sleep(1); st.rerun()
            else: st.error("Nessuna vettura 'CONSEGNATA' trovata.")
