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
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CREDENZIALI ---
CREDENZIALI = {"Luca Simonini ": "luca2026", "Ivan Pohorilyak": "ivan2026"}
TIMEOUT_MINUTI = 10 

# --- CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}

st.set_page_config(page_title="1.1 Master", layout="wide") [cite: 2026-01-08]

# --- GESTIONE SESSIONE E TIMEOUT ---
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
            st.warning("Sessione scaduta per inattività. Effettua di nuovo il login.")
            time.sleep(2)
            st.rerun()

# --- FUNZIONI CORE ---
def registra_log(targa, azione, dettaglio, utente):
    supabase.table("log_movimenti").insert({
        "targa": targa, "azione": action, "dettaglio": dettaglio, "utente": utente
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
    st.title("🔐 Accesso Autoclub Center")
    u = st.selectbox("Seleziona Operatore", list(CREDENZIALI.keys()))
    p = st.text_input("Password", type="password")
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

    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export", "📜 Log Movimenti", "🖨️ Stampa QR"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")

    # 1️⃣ Reset QR se l’utente cambia menu [cite: 2026-01-02]
    if scelta != "➕ Ingresso" and scelta != "🔍 Ricerca/Sposta":
        st.session_state["zona_rilevata"] = ""
        st.session_state["zona_rilevata_sposta"] = ""

    # --- 1. INGRESSO ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Registrazione Nuova Vettura")

        st.markdown("### 📍 Scanner Zona (Obbligatorio)")
        foto_z = st.camera_input("Inquadra QR-CODE della zona", key="cam_zona")

        if foto_z:
            zona_letta = leggi_qr_zona(foto_z)
            if zona_letta in ZONE_INFO:
                st.session_state["zona_rilevata"] = zona_letta
                st.success(f"Zona rilevata: {zona_letta}")
            else:
                st.session_state["zona_rilevata"] = ""
                st.error("QR non valido o zona sconosciuta")
        
        zona_attuale = st.session_state.get("zona_rilevata", "")

        with st.form("f_ingresso", clear_on_submit=True):
            # 2️⃣ Mostrare zona selezionata in chiaro nel form [cite: 2026-01-02]
            if zona_attuale:
                st.info(f"✅ Zona scansionata: **{zona_attuale}**")
            else:
                st.warning("⚠️ Scansiona il QR della zona sopra per abilitare la registrazione")

            targa = st.text_input("TARGA").upper().strip()
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
            n_chiave = st.number_input("N° Chiave (0=Commerciante)", min_value=0)
            note = st.text_area("Note")

            submit = st.form_submit_button(
                "REGISTRA VETTURA",
                disabled=not st.session_state.get("zona_rilevata")
            )

            if submit:
                aggiorna_attivita()
                zona_finale = st.session_state.get("zona_rilevata", "")
                testo_chiave = f"CHIAVE: {n_chiave}" if n_chiave > 0 else "CHIAVE: COMMERCIANTE"
                final_note = f"[AUTO COMMERCIANTE] {note}".strip() if n_chiave == 0 else note

                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("⚠️ Formato targa non valido (Esempio: AA123BB)")
                elif targa and marca_sel and modello_sel:
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data: [cite: 2025-12-30]
                        st.error("ERRORE: Vettura già presente!")
                    else:
                        data = {"targa": targa, "marca_modello": modello_completo, "colore": colore, "km": km, "numero_chiave": n_chiave, "zona_attuale": zona_finale, "note": final_note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"Inserita in {zona_finale} - {testo_chiave}", utente_attivo)
                        st.session_state["zona_rilevata"] = ""
                        st.success(f"Vettura {targa} registrata correttamente!")
                        st.rerun()

    # --- 2. RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Gestione")
        
        st.markdown("### 🔄 Scansiona QR Nuova Zona per Spostare")
        foto_sposta = st.camera_input("Inquadra QR Nuova Zona", key="cam_sposta")
        if foto_sposta:
            n_z_letta = leggi_qr_zona(foto_sposta)
            if n_z_letta in ZONE_INFO:
                st.session_state["zona_rilevata_sposta"] = n_z_letta
                st.info(f"Nuova zona rilevata: {n_z_letta}")
            else:
                st.session_state["zona_rilevata_sposta"] = ""
                st.error("QR non valido")

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
                            st.write(f"📍 Zona Attuale: **{v['zona_attuale']}**")
                            
                            zona_nuova = st.session_state.get("zona_rilevata_sposta", "")
                            if zona_nuova:
                                st.info(f"👉 Destinazione: **{zona_nuova}**")

                            c1, c2 = st.columns(2)
                            sposta_disabilitato = not zona_nuova
                            if c1.button("Conferma Spostamento", key=f"b_{v['targa']}", disabled=sposta_disabilitato):
                                aggiorna_attivita()
                                supabase.table("parco_usato").update({"zona_attuale": zona_nuova}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {zona_nuova}", utente_attivo)
                                st.session_state["zona_rilevata_sposta"] = ""
                                st.success(f"Spostata in {zona_nuova}")
                                st.rerun()
                            
                            if c2.button("🔴 CONSEGNA", key=f"d_{v['targa']}"):
                                aggiorna_attivita()
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", "Uscita definitiva", utente_attivo)
                                st.rerun()
                else:
                    st.warning("Vettura non trovata.")

    # --- 📋 SEZIONI RESTANTI RIMANGONO INVARIATE ---
    elif scelta == "📋 Verifica Zone":
        aggiorna_attivita()
        z_sel = st.selectbox("Zona", list(ZONE_INFO.keys()))
        res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
        st.metric(f"Stato {z_sel}", f"{len(res.data)} / 100")
        if res.data:
            df = pd.DataFrame(res.data)[["targa", "marca_modello", "numero_chiave", "data_ingresso"]]
            df['data_ingresso'] = pd.to_datetime(df['data_ingresso']).dt.strftime('%d/%m/%Y %H:%M')
            st.dataframe(df, use_container_width=True)

    elif scelta == "📊 Export":
        aggiorna_attivita()
        res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        if res.data:
            df_ex = pd.DataFrame(res.data).drop(columns=['stato'], errors='ignore')
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_ex.to_excel(writer, index=False)
            st.download_button("📥 Scarica Excel", output.getvalue(), "Piazzale.xlsx")

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

    elif scelta == "🖨️ Stampa QR":
        st.subheader("Genera QR per le Zone")
        z_sel_qr = st.selectbox("Seleziona Zona da stampare", list(ZONE_INFO.keys()))
        qr = qrcode.make(f"ZONA|{z_sel_qr}")
        buf = BytesIO()
        qr.save(buf, format="PNG")
        st.image(buf.getvalue(), caption=f"QR per {z_sel_qr}", width=300)
        st.download_button("📥 Scarica QR da stampare", buf.getvalue(), f"QR_{z_sel_qr}.png")
