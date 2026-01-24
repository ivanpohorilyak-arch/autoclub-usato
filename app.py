import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime, timedelta
import time
from io import BytesIO
import re
import cv2
import numpy as np
import pytesseract
from streamlit_autorefresh import st_autorefresh
import qrcode
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CREDENZIALI E CONFIG ---
CREDENZIALI = {"Luca Simonini": "luca2026", "Ivan Pohorilyak": "ivan2026"}
TIMEOUT_MINUTI = 15 
st.set_page_config(page_title="1.1 Master", layout="wide")

ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}

# --- SESSION STATE & TIMEOUT ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'last_action' not in st.session_state:
    st.session_state['last_action'] = datetime.now()

def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now()

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now() - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state['user_autenticato'] = None
            st.rerun()

# --- FUNZIONI SCANNER ---
def leggi_targa_da_foto(image_file):
    try:
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        testo = pytesseract.image_to_string(gray, config='--psm 7')
        return re.sub(r'[^A-Z0-9]', '', testo.upper())
    except: return ""

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

# --- FUNZIONE GENERAZIONE CARTELLI A4 ---
def genera_cartello_a4(nome_zona):
    # Crea un'immagine bianca formato A4 (approx 300dpi: 2480x3508)
    img = Image.new('RGB', (2480, 3508), color='white')
    draw = ImageDraw.Draw(img)
    
    # QR Code
    qr = qrcode.QRCode(version=1, box_size=40, border=4)
    qr.add_data(f"ZONA|{nome_zona}")
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    qr_img = qr_img.resize((1800, 1800))
    
    # Posizionamento
    img.paste(qr_img, (340, 800))
    
    # Testo (usa font di sistema o default)
    try:
        font_titolo = ImageFont.truetype("arial.ttf", 200)
        font_sub = ImageFont.truetype("arial.ttf", 80)
    except:
        font_titolo = ImageFont.load_default()
        font_sub = ImageFont.load_default()

    draw.text((1240, 400), "AUTO CLUB PRO", fill="black", font=font_sub, anchor="mm")
    draw.text((1240, 600), nome_zona.upper(), fill="black", font=font_titolo, anchor="mm")
    draw.text((1240, 2800), "SCANSIONA PER ASSEGNARE LA ZONA", fill="red", font=font_sub, anchor="mm")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

controllo_timeout()

# --- INTERFACCIA ---
if st.session_state['user_autenticato'] is None:
    st.title("🔐 Accesso Autoclub")
    u = st.selectbox("Operatore", list(CREDENZIALI.keys()))
    p = st.text_input("Password", type="password")
    if st.button("Entra"):
        if p == CREDENZIALI[u]:
            st.session_state['user_autenticato'] = u
            aggiorna_attivita()
            st.rerun()
else:
    utente_attivo = st.session_state['user_autenticato']
    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📊 Export", "📜 Log", "🖨️ Gestione QR"]
    scelta = st.radio("Menu", menu, horizontal=True)

    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Nuovo Ingresso")
        
        # Scanner Targa
        t_letta = ""
        if st.toggle("📸 Scanner Targa"):
            foto_t = st.camera_input("Foto Targa")
            if foto_t: t_letta = leggi_targa_da_foto(foto_t)

        with st.form("f_ingresso"):
            targa = st.text_input("TARGA", value=t_letta).upper().strip()
            # ... (campi marca/modello/colore/km come prima) ...
            
            st.markdown("### 📍 Scanner Zona Obbligatorio")
            zona_rilevata = ""
            foto_z = st.camera_input("Inquadra QR Zona")
            if foto_z:
                zona_rilevata = leggi_qr_zona(foto_z)
                if zona_rilevata in ZONE_INFO:
                    st.success(f"Zona: {zona_rilevata}")
                else:
                    st.error("QR non valido")
            
            if st.form_submit_button("REGISTRA"):
                if not zona_rilevata:
                    st.error("ERRORE: Devi scansionare il QR della zona!")
                elif targa:
                    # Logica inserimento DB Supabase
                    st.success("Registrato!")
                    st.rerun()

    elif scelta == "🖨️ Gestione QR":
        st.subheader("Stampa Cartelli Zone")
        st.info("Genera i QR in formato A4 da stampare e appendere al muro.")
        
        col1, col2 = st.columns(2)
        z_da_stampare = col1.selectbox("Seleziona Zona", list(ZONE_INFO.keys()))
        
        if col1.button("Genera Cartello"):
            cartello = genera_cartello_a4(z_da_stampare)
            st.image(cartello, caption=f"Anteprima Cartello {z_da_stampare}", width=400)
            st.download_button(
                label="📥 Scarica cartello per stampa",
                data=cartello,
                file_name=f"Cartello_{z_da_stampare}.png",
                mime="image/png"
            )
