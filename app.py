import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO
import re
import cv2
import numpy as np
import pytesseract

# --- CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CREDENZIALI ---
CREDENZIALI = {
    "Luca": "luca2026", "Ivan": "ivan2026"
}

# --- CONFIGURAZIONE ZONE (Limite 100) ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1", layout="centered")

# --- SESSION STATE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None

# --- FUNZIONI CORE ---
def registra_log(targa, azione, dettaglio, utente):
    supabase.table("log_movimenti").insert({
        "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente
    }).execute()

def get_colori():
    res = supabase.table("parco_usato").select("colore").execute()
    colori = list(set([str(r['colore']).capitalize() for r in res.data if r['colore']]))
    return sorted(colori) if colori else ["Bianco", "Nero", "Grigio"]

def leggi_targa_da_foto(image_file):
    try:
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        testo = pytesseract.image_to_string(gray, config='--psm 7')
        return re.sub(r'[^A-Z0-9]', '', testo.upper())
    except: return ""

# --- LOGICA ACCESSO ---
if st.session_state['user_autenticato'] is None:
    st.title("🔐 Login Autoclub Center")
    u = st.selectbox("Utente", list(CREDENZIALI.keys()))
    p = st.text_input("Password", type="password")
    if st.button("Entra"):
        if p == CREDENZIALI[u]:
            st.session_state['user_autenticato'] = u
            st.rerun()
        else: st.error("Password errata")
else:
    utente_attivo = st.session_state['user_autenticato']
    st.sidebar.info(f"Utente: {utente_attivo}")
    if st.sidebar.button("Logout"):
        st.session_state['user_autenticato'] = None
        st.rerun()

    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export & Log"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")

    # --- 1. INGRESSO ---
    if scelta == "➕ Ingresso":
        st.subheader("Registrazione Nuova Vettura")
        attiva_cam = st.toggle("📸 Attiva Scanner Targa")
        t_letta = ""
        if attiva_cam:
            foto = st.camera_input("Inquadra targa")
            if foto: t_letta = leggi_targa_da_foto(foto)

        with st.form("f_ingresso", clear_on_submit=True):
            targa = st.text_input("TARGA", value=t_letta).upper().strip()
            modello = st.text_input("Marca e Modello")
            
            colori_sugg = get_colori()
            colore_scelto = st.selectbox("Colore (Auto-apprendimento)", ["Nuovo..."] + colori_sugg)
            if colore_scelto == "Nuovo...": colore_scelto = st.text_input("Scrivi Colore")
            
            km = st.number_input("Chilometri", min_value=0)
            n_chiave = st.number_input("N° Chiave (0=Commerciante)", min_value=0)
            zona = st.selectbox("Zona Iniziale", list(ZONE_INFO.keys()))
            note = st.text_area("Note")

            if st.form_submit_button("REGISTRA"):
                # CONTROLLO FORMATO TARGA (Tua richiesta)
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("⚠️ Formato targa non valido (Esempio corretto: AA123BB)")
                elif targa and modello:
                    # Blocco duplicati rigoroso [cite: 2025-12-30, 2026-01-02]
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data: 
                        st.error("ERRORE: Vettura già presente in piazzale!")
                    else:
                        data = {"targa": targa, "marca_modello": modello, "colore": colore_scelto, "km": km,
                                "numero_chiave": n_chiave, "zona_attuale": zona, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"Inserita in {zona}", utente_attivo)
                        st.success("Registrato con successo!")
                else: 
                    st.error("Targa e Modello sono campi obbligatori")

    # --- LE ALTRE SEZIONI (Ricerca, Verifica, Export) RIMANGONO INVARIATE ---
    elif scelta == "🔍 Ricerca/Sposta":
        # ... (Codice ricerca smart per targa/chiave)
        st.subheader("Cerca e Gestisci Vettura")
        tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
        q = st.text_input(f"Inserisci {tipo}")
        if q:
            if tipo == "Targa":
                res = supabase.table("parco_usato").select("*").eq("targa", q.upper()).eq("stato", "PRESENTE").execute()
            else:
                try: res = supabase.table("parco_usato").select("*").eq("numero_chiave", int(q)).eq("stato", "PRESENTE").execute()
                except: res = None
            
            if res and res.data:
                for v in res.data:
                    with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                        st.write(f"📍 Zona: **{v['zona_attuale']}** | 🔑 Chiave: **{v['numero_chiave']}**")
                        n_z = st.selectbox("Sposta in:", list(ZONE_INFO.keys()), key=f"z_{v['targa']}")
                        c1, c2 = st.columns(2)
                        if c1.button("Aggiorna Posizione", key=f"b_{v['targa']}"):
                            supabase.table("parco_usato").update({"zona_attuale": n_z}).eq("targa", v['targa']).execute()
                            registra_log(v['targa'], "Spostamento", f"In {n_z}", utente_attivo)
                            st.rerun()
                        if c2.button("🔴 CONSEGNA", key=f"d_{v['targa']}"):
                            supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                            registra_log(v['targa'], "Consegna", "Uscita", utente_attivo)
                            st.rerun()
            else: st.warning("Nessun risultato")

    elif scelta == "📋 Verifica Zone":
        # ... (Codice verifica zone e capacità)
        st.subheader("Stato Zone")
        z_sel = st.selectbox("Scegli Zona", list(ZONE_INFO.keys()))
        res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
        st.metric(f"Posti {z_sel}", f"{len(res.data)} / 100")
        if res.data:
            df = pd.DataFrame(res.data)[["targa", "marca_modello", "numero_chiave", "data_ingresso"]]
            df['data_ingresso'] = pd.to_datetime(df['data_ingresso']).dt.strftime('%d/%m/%Y %H:%M')
            st.dataframe(df, use_container_width=True)

    elif scelta == "📊 Export & Log":
        # ... (Codice export excel e log movimenti)
        st.subheader("Esportazione Parco Usato")
        res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        if res.data:
            df_ex = pd.DataFrame(res.data).drop(columns=['stato'], errors='ignore')
            df_ex['data_ingresso'] = pd.to_datetime(df_ex['data_ingresso']).dt.strftime('%d/%m/%Y %H:%M')
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_ex.to_excel(writer, index=False, sheet_name='Piazzale')
                ws = writer.sheets['Piazzale']
                for i, col in enumerate(df_ex.columns):
                    ws.set_column(i, i, 20)
            st.download_button("📥 Scarica Excel", output.getvalue(), "Piazzale_Autoclub.xlsx")
