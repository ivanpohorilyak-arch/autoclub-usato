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

# --- CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CREDENZIALI ---
CREDENZIALI = {"Luca": "luca2026", "Ivan": "ivan2026"}
TIMEOUT_MINUTI = 10  # Tempo di inattività prima del logout

# --- CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}

st.set_page_config(page_title="1.1 Master", layout="wide")

# --- GESTIONE SESSIONE E TIMEOUT ---
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
            st.warning("Sessione scaduta per inattività. Effettua di nuovo il login.")
            time.sleep(2)
            st.rerun()

# --- FUNZIONI CORE ---
def registra_log(targa, azione, dettaglio, utente):
    supabase.table("log_movimenti").insert({
        "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente
    }).execute()

def get_colori():
    res = supabase.table("parco_usato").select("colore").execute()
    colori = list(set([str(r['colore']).capitalize() for r in res.data if r['colore']]))
    return sorted(colori) if colori else ["Bianco", "Nero", "Grigio"]

def get_marche():
    res = supabase.table("parco_usato").select("marca_modello").execute()
    marche = set()
    for r in res.data:
        if r.get("marca_modello"):
            marca = r["marca_modello"].split()[0].capitalize()
            marche.add(marca)
    return sorted(marche)

def get_modelli(marca):
    res = supabase.table("parco_usato").select("marca_modello").execute()
    modelli = set()
    for r in res.data:
        if r.get("marca_modello", "").startswith(marca):
            mod = r["marca_modello"].replace(marca, "", 1).strip().title()
            if mod: modelli.add(mod)
    return sorted(modelli)

def leggi_targa_da_foto(image_file):
    try:
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, 1)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        testo = pytesseract.image_to_string(gray, config='--psm 7')
        return re.sub(r'[^A-Z0-9]', '', testo.upper())
    except: return ""

# Esegui controllo timeout all'avvio di ogni ciclo
controllo_timeout()

# --- LOGICA ACCESSO ---
if st.session_state['user_autenticato'] is None:
    st.title("🔐 Accesso Autoclub Center")
    u = st.selectbox("Seleziona Operatore", list(CREDENZIALI.keys()))
    p = st.text_input("Inserisci Password", type="password")
    if st.button("Entra"):
        if p == CREDENZIALI[u]:
            st.session_state['user_autenticato'] = u
            aggiorna_attivita()
            st.rerun()
        else: st.error("Password errata")
else:
    utente_attivo = st.session_state['user_autenticato']
    st.sidebar.info(f"Operatore: {utente_attivo}")
    if st.sidebar.button("Logout Manuale"):
        st.session_state['user_autenticato'] = None
        st.rerun()

    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export", "📜 Log Movimenti"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")

    # --- 1. INGRESSO ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Registrazione Nuova Vettura")
        attiva_cam = st.toggle("📸 Scanner Targa (OCR)")
        t_letta = ""
        if attiva_cam:
            foto = st.camera_input("Scatta foto targa")
            if foto: t_letta = leggi_targa_da_foto(foto)

        with st.form("f_ingresso", clear_on_submit=True):
            targa = st.text_input("TARGA", value=t_letta).upper().strip()
            marche = get_marche()
            marca_sel = st.selectbox("Marca", ["Nuova..."] + marche)
            if marca_sel == "Nuova...": marca_sel = st.text_input("Scrivi Marca").capitalize()
            modelli = get_modelli(marca_sel) if marca_sel else []
            modello_sel = st.selectbox("Modello", ["Nuovo..."] + modelli)
            if modello_sel == "Nuovo...": modello_sel = st.text_input("Scrivi Modello").title()
            modello_completo = f"{marca_sel} {modello_sel}".strip()
            colore = st.selectbox("Colore", ["Nuovo..."] + get_colori())
            if colore == "Nuovo...": colore = st.text_input("Specifica Colore")
            km = st.number_input("Chilometri", min_value=0)
            n_chiave = st.number_input("N° Chiave", min_value=0)
            zona = st.selectbox("Assegna Zona", list(ZONE_INFO.keys()))
            note = st.text_area("Note")

            if st.form_submit_button("REGISTRA VETTURA"):
                aggiorna_attivita()
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("⚠️ Formato targa non valido (Esempio: AA123BB)")
                elif targa and marca_sel and modello_sel:
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data:
                        st.error("ERRORE: Vettura già presente!")
                    else:
                        data = {"targa": targa, "marca_modello": modello_completo, "colore": colore, "km": km, "numero_chiave": n_chiave, "zona_attuale": zona, "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"Inserita in {zona}", utente_attivo)
                        st.success(f"Vettura {targa} registrata!")
                        st.rerun()

    # --- 2. RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Gestione")
        tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
        q = st.text_input(f"Inserisci {tipo}").strip()
        if q:
            col = "targa" if tipo == "Targa" else "numero_chiave"
            val = q.upper() if tipo == "Targa" else int(q) if q.isdigit() else None
            if val is not None:
                res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute()
                if res and res.data:
                    for v in res.data:
                        with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                            st.write(f"📍 Zona: **{v['zona_attuale']}** | 🔑 Chiave: **{v['numero_chiave']}**")
                            n_z = st.selectbox("Sposta in:", list(ZONE_INFO.keys()), key=v['targa'])
                            c1, c2 = st.columns(2)
                            if c1.button("Sposta", key=f"b_{v['targa']}"):
                                aggiorna_attivita()
                                supabase.table("parco_usato").update({"zona_attuale": n_z}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {n_z}", utente_attivo)
                                st.rerun()
                            if c2.button("🔴 CONSEGNA", key=f"d_{v['targa']}"):
                                aggiorna_attivita()
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", "Uscita definitiva", utente_attivo)
                                st.rerun()
                else:
                    st.warning("Vettura non trovata o valore non valido.")

    # --- 3. VERIFICA ZONE ---
    elif scelta == "📋 Verifica Zone":
        aggiorna_attivita()
        z_sel = st.selectbox("Zona", list(ZONE_INFO.keys()))
        res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
        st.metric(f"Stato {z_sel}", f"{len(res.data)} / 100")
        if res.data:
            df = pd.DataFrame(res.data)[["targa", "marca_modello", "numero_chiave", "data_ingresso"]]
            df['data_ingresso'] = pd.to_datetime(df['data_ingresso']).dt.strftime('%d/%m/%Y %H:%M')
            st.dataframe(df, use_container_width=True)

    # --- 4. EXPORT ---
    elif scelta == "📊 Export":
        aggiorna_attivita()
        res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        if res.data:
            df_ex = pd.DataFrame(res.data).drop(columns=['stato'], errors='ignore')
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_ex.to_excel(writer, index=False)
            st.download_button("📥 Scarica Excel", output.getvalue(), "Piazzale.xlsx")

    # --- 5. LOG MOVIMENTI ---
    elif scelta == "📜 Log Movimenti":
        st.subheader("Cronologia Operazioni in Tempo Reale")
        auto_refresh = st.toggle("🔄 Aggiornamento automatico (10 sec)", value=True)
        if auto_refresh:
            st_autorefresh(interval=10000, key="log_refresh")
        
        c1, c2 = st.columns(2)
        f_targa = c1.text_input("Cerca Targa").upper()
        f_user = c2.selectbox("Operatore", ["Tutti"] + list(CREDENZIALI.keys()))
        
        query = supabase.table("log_movimenti").select("*").order("created_at", desc=True)
        if f_targa: query = query.eq("targa", f_targa)
        if f_user != "Tutti": query = query.eq("utente", f_user)
        
        logs = query.limit(100).execute()
        if logs.data:
            df_l = pd.DataFrame(logs.data)
            df_l['created_at'] = pd.to_datetime(df_l['created_at']).dt.strftime('%d/%m/%Y %H:%M:%S')
            df_l = df_l.rename(columns={"created_at": "🕒 Data/Ora", "targa": "🚗 Targa", "azione": "⚙️ Azione", "dettaglio": "📝 Dettaglio", "utente": "👤 Operatore"})
            st.dataframe(df_l[["🕒 Data/Ora","🚗 Targa","⚙️ Azione","📝 Dettaglio","👤 Operatore"]], use_container_width=True)
