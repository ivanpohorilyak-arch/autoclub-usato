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

# --- CONFIGURAZIONE ZONE (Capacità 100) ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}
UTENTI = ["Luca", "Ivan"]

st.set_page_config(page_title="AUTOCLUB MASTER 1.2", layout="centered")

# --- FUNZIONE OCR (MODO SEMPLICE) ---
def leggi_targa_da_foto(image_file):
    file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, 1)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Pulizia immagine per migliorare lettura
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    testo = pytesseract.image_to_string(gray, config='--psm 7')
    # Filtra solo caratteri alfanumerici
    return re.sub(r'[^A-Z0-9]', '', testo.upper())

# --- INTERFACCIA ---
st.title("🚗 AUTOCLUB MASTER 1.2")
utente_attivo = st.sidebar.selectbox("Operatore:", UTENTI)
menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export & Log"]
scelta = st.sidebar.radio("Menu", menu)

if scelta == "➕ Ingresso":
    st.subheader("Registrazione Entrata")
    
    # OCR - MODO SEMPLICE
    foto_targa = st.camera_input("📸 Scansiona Targa")
    targa_letta = ""
    if foto_targa:
        targa_letta = leggi_targa_da_foto(foto_targa)
        st.success(f"Targa rilevata: {targa_letta}")

    with st.form("form_ingresso"):
        targa = st.text_input("TARGA", value=targa_letta).upper().strip()
        modello = st.text_input("Marca e Modello")
        
        # Auto-apprendimento colore (Logica 1.1)
        res_col = supabase.table("parco_usato").select("colore").execute()
        colori_sugg = list(set([r['colore'] for r in res_col.data if r['colore']]))
        colore = st.selectbox("Colore", ["Specifica..."] + colori_sugg)
        if colore == "Specifica...":
            colore = st.text_input("Scrivi nuovo colore")
            
        n_chiave = st.number_input("N° Chiave (0=Commerciante)", min_value=0)
        zona = st.selectbox("Zona", list(ZONE_INFO.keys()))
        
        if st.form_submit_button("REGISTRA"):
            # Blocco duplicati [cite: 2025-12-30]
            check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
            if check.data:
                st.error("ERRORE: Vettura già presente!")
            else:
                data = {
                    "targa": targa, "marca_modello": modello, "colore": colore,
                    "numero_chiave": n_chiave, "zona_attuale": zona, "stato": "PRESENTE",
                    "utente_ultimo_invio": utente_attivo
                }
                supabase.table("parco_usato").insert(data).execute()
                st.success("Vettura salvata!")

# (Le altre sezioni Ricerca, Verifica e Export rimangono identiche alla v1.1)
