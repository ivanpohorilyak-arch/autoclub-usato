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

# --- CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CREDENZIALI ---
CREDENZIALI = {"Luca Simonini": "luca2026", "Ivan Pohorilyak": "ivan2026"}
TIMEOUT_MINUTI = 10 

# --- CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}

# 1️⃣ FIX: SyntaxError rimosso (citazione spostata in commento)
st.set_page_config(page_title="1.1 Master", layout="wide") # [cite: 2026-01-08]

# --- GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'last_action' not in st.session_state:
    st.session_state['last_action'] = datetime.now()
if 'zona_rilevata' not in st.session_state:
    st.session_state['zona_rilevata'] = ""

def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now()

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now() - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state['user_autenticato'] = None
            st.warning("Sessione scaduta. Effettua il login.")
            time.sleep(2)
            st.rerun()

# --- FUNZIONI CORE ---
# 2️⃣ FIX: Corretto "azione": azione (era "action")
def registra_log(targa, azione, dettaglio, utente):
    try:
        supabase.table("log_movimenti").insert({
            "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente
        }).execute()
    except Exception as e:
        st.error(f"Errore Log: {e}")

def get_colori():
    try:
        res = supabase.table("parco_usato").select("colore").execute()
        colori = list(set([str(r['colore']).capitalize() for r in res.data if r['colore']]))
        return sorted(colori) if colori else ["Bianco", "Nero", "Grigio"]
    except: return ["Bianco", "Nero", "Grigio"]

def get_marche():
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        marche = set()
        for r in res.data:
            if r.get("marca_modello"):
                marche.add(r["marca_modello"].split()[0].capitalize())
        return sorted(marche)
    except: return []

def leggi_qr_zona(image_file):
    try:
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if data.startswith("ZONA|"):
            return data.replace("ZONA|", "").strip()
        return ""
    except: return ""

controllo_timeout()

# --- LOGICA ACCESSO ---
if st.session_state['user_autenticato'] is None:
    st.title("🔐 Accesso Autoclub")
    u = st.selectbox("Operatore", list(CREDENZIALI.keys()))
    p = st.text_input("Password", type="password")
    if st.button("Entra"):
        if p == CREDENZIALI[u]:
            st.session_state['user_autenticato'] = u
            aggiorna_attivita()
            st.rerun()
        else: st.error("Password errata")
else:
    utente_attivo = st.session_state['user_autenticato']
    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export", "📜 Log Movimenti", "🖨️ Stampa QR"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    
    # Reset zona se si cambia menu
    if scelta != "➕ Ingresso" and scelta != "🔍 Ricerca/Sposta":
        st.session_state["zona_rilevata"] = ""

    # --- 1. INGRESSO ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Registrazione Nuova Vettura")
        foto_z = st.camera_input("Scanner Zona QR", key="cam_zona")
        
        if foto_z:
            z_letta = leggi_qr_zona(foto_z)
            if z_letta in ZONE_INFO:
                st.session_state["zona_rilevata"] = z_letta
                st.success(f"Zona rilevata: {z_letta}")
            else:
                st.session_state["zona_rilevata"] = ""
                st.error("QR non valido o zona sconosciuta")
        
        zona_attuale = st.session_state.get("zona_rilevata", "")

        with st.form("f_ingresso", clear_on_submit=True):
            if zona_attuale: 
                st.info(f"✅ Zona selezionata: **{zona_attuale}**")
            else:
                st.warning("⚠️ Scansiona il QR della zona sopra per abilitare il tasto Registra")

            targa = st.text_input("TARGA").upper().strip()
            marca = st.text_input("Marca/Modello").capitalize()
            colore = st.selectbox("Colore", ["Nuovo..."] + get_colori())
            km = st.number_input("Chilometri", min_value=0)
            n_chiave = st.number_input("N. Chiave (0=Commerciante)", min_value=0)
            note = st.text_area("Note")

            submit = st.form_submit_button("REGISTRA VETTURA", disabled=not zona_attuale)

            if submit:
                aggiorna_attivita()
                txt_chiave = f"CHIAVE: {n_chiave}" if n_chiave > 0 else "CHIAVE: COMMERCIANTE"
                final_note = f"[AUTO COMMERCIANTE] {note}".strip() if n_chiave == 0 else note

                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("⚠️ Formato targa non valido (Esempio: AA123BB)")
                elif targa and marca:
                    # 3️⃣ FIX: SyntaxError rimosso da check.data
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data: # [cite: 2025-12-30]
                        st.error("ERRORE: Vettura già presente in piazzale!")
                    else:
                        data = {"targa": targa, "marca_modello": marca, "colore": colore, "km": km, "numero_chiave": n_chiave, "zona_attuale": zona_attuale, "note": final_note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"In {zona_attuale} - {txt_chiave}", utente_attivo)
                        st.session_state["zona_rilevata"] = ""
                        st.success(f"Vettura {targa} registrata correttamente!")
                        st.rerun()

    # --- 5. LOG MOVIMENTI ---
    elif scelta == "📜 Log Movimenti":
        st.subheader("Cronologia Operazioni in Tempo Reale")
        auto_refresh = st.toggle("🔄 Aggiornamento automatico (10 sec)", value=True)
        if auto_refresh:
            st_autorefresh(interval=10000, key="log_refresh")
        
        try:
            logs = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(50).execute()
            if logs.data:
                df = pd.DataFrame(logs.data)
                df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%d/%m/%Y %H:%M:%S')
                df = df.rename(columns={"created_at": "🕒 Data/Ora", "targa": "🚗 Targa", "azione": "⚙️ Azione", "dettaglio": "📝 Dettaglio", "utente": "👤 Operatore"})
                st.dataframe(df[["🕒 Data/Ora", "🚗 Targa", "⚙️ Azione", "📝 Dettaglio", "👤 Operatore"]], use_container_width=True)
        except Exception as e:
            st.error(f"Errore caricamento log: {e}")

    # --- 🖨️ STAMPA QR ---
    elif scelta == "🖨️ Stampa QR":
        st.subheader("Genera QR per le Zone")
        z_sel_qr = st.selectbox("Seleziona Zona da stampare", list(ZONE_INFO.keys()))
        qr = qrcode.make(f"ZONA|{z_sel_qr}")
        buf = BytesIO()
        qr.save(buf, format="PNG")
        st.image(buf.getvalue(), caption=f"QR per {z_sel_qr}", width=300)
        st.download_button("📥 Scarica QR da stampare", buf.getvalue(), f"QR_{z_sel_qr}.png")
