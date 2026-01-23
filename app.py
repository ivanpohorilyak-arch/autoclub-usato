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
# Inserisci qui i tuoi dati da Supabase Settings -> API
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CONFIGURAZIONE ZONE (Capacità base 100) ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}
UTENTI = ["Luca", "Ivan"]

st.set_page_config(page_title="AUTOCLUB MASTER 1.2.1", layout="centered")

# --- FUNZIONI DI SUPPORTO ---
def registra_log(targa, azione, dettaglio, utente):
    supabase.table("log_movimenti").insert({
        "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente
    }).execute()

def leggi_targa_da_foto(image_file):
    try:
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        testo = pytesseract.image_to_string(gray, config='--psm 7')
        return re.sub(r'[^A-Z0-9]', '', testo.upper())
    except:
        return ""

def get_colori():
    res = supabase.table("parco_usato").select("colore").execute()
    colori = list(set([str(r['colore']).capitalize() for r in res.data if r['colore']]))
    return sorted(colori) if colori else ["Bianco", "Nero", "Grigio"]

# --- INTERFACCIA PRINCIPALE ---
st.title("🚗 AUTOCLUB MASTER 1.2.1")
utente_attivo = st.sidebar.selectbox("Operatore:", UTENTI)
menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export & Log"]
scelta = st.sidebar.radio("Menu", menu)

# --- 1. INGRESSO CON ATTIVAZIONE CAMERA ---
if scelta == "➕ Ingresso":
    st.subheader("Registrazione Nuova Entrata")
    
    # Tasto attivazione Camera
    attiva_camera = st.toggle("📸 Attiva Scanner Targa")
    targa_letta = ""
    
    if attiva_camera:
        foto_targa = st.camera_input("Inquadra la targa")
        if foto_targa:
            targa_letta = leggi_targa_da_foto(foto_targa)
            if targa_letta:
                st.success(f"Targa rilevata: {targa_letta}")
            else:
                st.warning("Lettura non riuscita, inserisci a mano.")

    with st.form("form_ingresso", clear_on_submit=True):
        targa = st.text_input("TARGA", value=targa_letta).upper().strip()
        modello = st.text_input("Marca e Modello")
        
        colore_sugg = get_colori()
        colore_scelto = st.selectbox("Colore (Auto-apprendimento)", ["Nuovo..."] + colore_sugg)
        if colore_scelto == "Nuovo...":
            colore_scelto = st.text_input("Scrivi colore")
            
        km = st.number_input("Chilometri", min_value=0)
        n_chiave = st.number_input("N° Chiave (0=Commerciante)", min_value=0)
        zona = st.selectbox("Zona iniziale", list(ZONE_INFO.keys()))
        note = st.text_area("Note")

        if st.form_submit_button("REGISTRA VETTURA"):
            if targa:
                # Blocco duplicati
                check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                if check.data:
                    st.error(f"ATTENZIONE: La targa {targa} è già registrata in piazzale!")
                else:
                    data = {
                        "targa": targa, "marca_modello": modello, "colore": colore_scelto,
                        "km": km, "numero_chiave": n_chiave, "zona_attuale": zona, 
                        "note": note, "utente_ultimo_invio": utente_attivo, "stato": "PRESENTE"
                    }
                    supabase.table("parco_usato").insert(data).execute()
                    registra_log(targa, "Ingresso", f"Inserita in {zona} (Chiave {n_chiave})", utente_attivo)
                    st.success("Registrazione completata!")
            else:
                st.error("La targa è obbligatoria")

# --- 2. RICERCA SMART E SPOSTA (CORRETTO) ---
elif scelta == "🔍 Ricerca/Sposta":
    st.subheader("Ricerca e Gestione")
    criterio = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
    query = st.text_input(f"Inserisci {criterio}").strip()

    if query:
        if criterio == "Targa":
            res = supabase.table("parco_usato").select("*").eq("targa", query.upper()).eq("stato", "PRESENTE").execute()
        else:
            try:
                res = supabase.table("parco_usato").select("*").eq("numero_chiave", int(query)).eq("stato", "PRESENTE").execute()
            except:
                res = None

        if res and res.data:
            for v in res.data:
                with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                    st.write(f"📍 Posizione: **{v['zona_attuale']}** | 🔑 Chiave: **{v['numero_chiave']}**")
                    nuova_zona = st.selectbox("Sposta in:", list(ZONE_INFO.keys()), key=f"z_{v['targa']}")
                    
                    c1, c2 = st.columns(2)
                    if c1.button("Conferma Spostamento", key=f"btn_{v['targa']}"):
                        supabase.table("parco_usato").update({"zona_attuale": nuova_zona}).eq("targa", v['targa']).execute()
                        registra_log(v['targa'], "Spostamento", f"Da {v['zona_attuale']} a {nuova_zona}", utente_attivo)
                        st.success("Spostata!")
                        st.rerun()
                    
                    if c2.button("🔴 CONSEGNA", key=f"del_{v['targa']}"):
                        supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                        registra_log(v['targa'], "Consegna", "Uscita dal piazzale", utente_attivo)
                        st.rerun()
        else:
            st.warning("Vettura non trovata.")

# --- 3. VERIFICA ZONE E CAPACITÀ ---
elif scelta == "📋 Verifica Zone":
    z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()))
    res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
    
    occ = len(res.data)
    tot = ZONE_INFO[z_sel]
    st.metric(label=f"Capacità {z_sel}", value=f"{occ} / {tot}", delta=f"{tot-occ} liberi")
    
    if res.data:
        df = pd.DataFrame(res.data)[["targa", "marca_modello", "numero_chiave", "data_ingresso"]]
        df['data_ingresso'] = pd.to_datetime(df['data_ingresso']).dt.strftime('%d/%m/%Y %H:%M')
        st.table(df)

# --- 4. EXPORT EXCEL FORMATTATO ---
elif scelta == "📊 Export & Log":
    res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
    if res.data:
        df_ex = pd.DataFrame(res.data).drop(columns=['stato'], errors='ignore')
        df_ex['data_ingresso'] = pd.to_datetime(df_ex['data_ingresso']).dt.strftime('%d/%m/%Y %H:%M')
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_ex.to_excel(writer, index=False, sheet_name='Piazzale')
            ws = writer.sheets['Piazzale']
            for i, col in enumerate(df_ex.columns):
                ws.set_column(i, i, max(len(col), 15))
        
        st.download_button("📥 Scarica Excel Parco Usato", output.getvalue(), "Parco_Usato.xlsx")
