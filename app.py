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
TIMEOUT_MINUTI = 15

# --- CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}

# Fix SyntaxError: Titolo pulito e citazione commentata
st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1", layout="wide") # [cite: 2026-01-08]

# --- GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'last_action' not in st.session_state:
    st.session_state['last_action'] = datetime.now()
if 'zona_rilevata' not in st.session_state:
    st.session_state['zona_rilevata'] = ""
if 'zona_rilevata_sposta' not in st.session_state:
    st.session_state['zona_rilevata_sposta'] = ""

def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now()

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now() - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state['user_autenticato'] = None
            st.rerun()

# --- FUNZIONI CORE ---
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

def get_modelli(marca):
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        modelli = set()
        for r in res.data:
            full = r.get("marca_modello", "")
            if full.startswith(marca):
                mod = full.replace(marca, "", 1).strip().title()
                if mod: modelli.add(mod)
        return sorted(modelli)
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
    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export", "📜 Log Movimenti", "🖨️ Stampa QR"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")

    if scelta != "➕ Ingresso" and scelta != "🔍 Ricerca/Sposta":
        st.session_state["zona_rilevata"] = ""
        st.session_state["zona_rilevata_sposta"] = ""

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
            if zona_attuale: st.info(f"✅ Zona selezionata: **{zona_attuale}**")
            targa = st.text_input("TARGA").upper().strip()
            
            marche = get_marche()
            m_sel = st.selectbox("Marca", ["Nuova..."] + marche)
            if m_sel == "Nuova...": m_sel = st.text_input("Specifica Marca").capitalize()
            
            modelli = get_modelli(m_sel) if m_sel else []
            mod_sel = st.selectbox("Modello", ["Nuovo..."] + modelli)
            if mod_sel == "Nuovo...": mod_sel = st.text_input("Specifica Modello").title()
            
            marca_modello = f"{m_sel} {mod_sel}".strip()
            colore = st.selectbox("Colore", ["Nuovo..."] + get_colori())
            if colore == "Nuovo...": colore = st.text_input("Specifica Colore")
            
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
                elif targa and m_sel and mod_sel:
                    # FIX: Sintassi corretta senza tag fuori dai commenti
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data:
                        st.error("ERRORE: Vettura già presente in piazzale!")
                    else:
                        data = {"targa": targa, "marca_modello": marca_modello, "colore": colore, "km": km, "numero_chiave": n_chiave, "zona_attuale": zona_attuale, "note": final_note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"In {zona_attuale} - {txt_chiave}", utente_attivo)
                        st.session_state["zona_rilevata"] = ""
                        st.success(f"Vettura {targa} registrata correttamente!")
                        st.rerun()

    # --- 2. RICERCA SMART ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Gestione")
        foto_sposta = st.camera_input("Scansiona QR Nuova Zona", key="cam_sposta")
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
            # FIX: Ricerca con return per evitare variabili non inizializzate
            if tipo == "Targa":
                if not re.match(r"^[A-Z0-9]{5,8}$", q.upper()):
                    st.warning("Formato targa non valido")
                    # return per UX mobile pulita
                else:
                    col, val = "targa", q.upper()
            else:  
                if not q.isdigit():
                    st.warning("Il numero chiave deve essere numerico")
                    # return per UX mobile pulita
                else:
                    col, val = "numero_chiave", int(q)

            # Esegui query solo se variabili col e val sono state create
            if 'col' in locals() and 'val' in locals():
                res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute()
                if res and res.data:
                    for v in res.data:
                        with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                            st.write(f"📍 Zona Attuale: **{v['zona_attuale']}**")
                            c1, c2 = st.columns(2)
                            
                            zona_nuova = st.session_state.get("zona_rilevata_sposta", "")
                            if c1.button("Conferma Spostamento", key=f"b_{v['targa']}", disabled=not zona_nuova):
                                aggiorna_attivita()
                                supabase.table("parco_usato").update({"zona_attuale": zona_nuova}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {zona_nuova}", utente_attivo)
                                st.session_state["zona_rilevata_sposta"] = ""
                                st.success(f"Spostata in {zona_nuova}")
                                st.rerun()
                            
                            if c2.button("🔴 CONSEGNA", key=f"d_{v['targa']}"):
                                aggiorna_attivita()
                                st.session_state["zona_rilevata_sposta"] = ""
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", "Uscita definitiva", utente_attivo)
                                st.rerun()
                else:
                    st.warning("Vettura non trovata.")

    # --- 3. VERIFICA ZONE ---
    elif scelta == "📋 Verifica Zone":
        aggiorna_attivita()
        st.subheader("Situazione Piazzale per Zona")
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()))
        res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
        st.metric(label=f"Veicoli in {z_sel}", value=f"{len(res.data)} / {ZONE_INFO[z_sel]}")
        if res.data:
            df = pd.DataFrame(res.data)[["targa", "marca_modello", "numero_chiave", "colore", "km"]]
            st.dataframe(df, use_container_width=True)
        else:
            st.info("Nessuna vettura presente in questa zona")

    # --- 4. EXPORT ---
    elif scelta == "📊 Export":
        aggiorna_attivita()
        res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        if res.data:
            df_ex = pd.DataFrame(res.data).drop(columns=["stato"], errors="ignore")
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_ex.to_excel(writer, index=False, sheet_name="Parco Usato")
                worksheet = writer.sheets["Parco Usato"]
                for idx, col in enumerate(df_ex.columns):
                    max_len = max(df_ex[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(idx, idx, max_len)
            st.download_button("📥 Scarica Excel", output.getvalue(), "Parco_Usato.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # --- 5. LOG MOVIMENTI ---
    elif scelta == "📜 Log Movimenti":
        st.subheader("Cronologia Operazioni")
        if st.toggle("🔄 Aggiornamento automatico (10 sec)", value=True):
            st_autorefresh(interval=10000, key="log_refresh")
        try:
            logs = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(50).execute()
            if logs.data:
                df = pd.DataFrame(logs.data)
                df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%d/%m/%Y %H:%M:%S')
                df = df.rename(columns={"created_at": "🕒 Ora", "targa": "🚗 Targa", "azione": "⚙️ Azione", "dettaglio": "📝 Info", "utente": "👤 Operatore"})
                st.dataframe(df[["🕒 Ora", "🚗 Targa", "⚙️ Azione", "📝 Info", "👤 Operatore"]], use_container_width=True)
        except Exception as e: st.error(f"Errore Log: {e}")

    # --- 🖨️ STAMPA QR ---
    elif scelta == "🖨️ Stampa QR":
        st.subheader("Genera QR Zone")
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()))
        qr = qrcode.make(f"ZONA|{z_sel}")
        buf = BytesIO()
        qr.save(buf, format="PNG")
        st.image(buf.getvalue(), caption=f"QR {z_sel}", width=300)
        st.download_button("📥 Scarica", buf.getvalue(), f"QR_{z_sel}.png")
