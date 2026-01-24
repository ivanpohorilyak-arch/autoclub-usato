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

# --- CREDENZIALI (PIN A 4 CIFRE) ---
CREDENZIALI = {
    "Luca Simonini": "2026", 
    "Ivan Pohorilyak": "1234"
}
TIMEOUT_MINUTI = 10

# --- CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1", layout="wide")

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

def suggerisci_colore(targa_input):
    try:
        if len(targa_input) >= 7:
            res = supabase.table("parco_usato").select("colore").eq("targa", targa_input).order("data_ingresso", desc=True).limit(1).execute()
            if res.data:
                return str(res.data[0]['colore']).capitalize()
        return None
    except: return None

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
    lista_utenti = list(CREDENZIALI.keys())
    u = st.selectbox("Seleziona Operatore", lista_utenti)
    p = st.text_input("Inserisci PIN (4 cifre)", type="password")
    if st.button("ACCEDI"):
        if p == CREDENZIALI[u]:
            st.session_state['user_autenticato'] = u
            aggiorna_attivita()
            st.rerun()
        else: st.error("PIN non corretto")
else:
    utente_attivo = st.session_state['user_autenticato']
    st.sidebar.info(f"Operatore: {utente_attivo}")
    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", "📋 Verifica Zone", "📊 Export", "📜 Log", "🖨️ Stampa QR"]
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
                st.error("QR non valido")
        
        zona_attuale = st.session_state.get("zona_rilevata", "")
        with st.form("f_ingresso", clear_on_submit=True):
            if zona_attuale: st.info(f"✅ Zona selezionata: **{zona_attuale}**")
            targa = st.text_input("TARGA").upper().strip()
            colore_suggerito = suggerisci_colore(targa) if targa else None
            lista_colori = get_colori()
            idx_colore = 0
            if colore_suggerito in lista_colori:
                idx_colore = lista_colori.index(colore_suggerito) + 1

            marche = get_marche()
            m_sel = st.selectbox("Marca", ["Nuova..."] + marche)
            if m_sel == "Nuova...": m_sel = st.text_input("Specifica Marca").capitalize()
            modelli = get_modelli(m_sel) if m_sel else []
            mod_sel = st.selectbox("Modello", ["Nuovo..."] + modelli)
            if mod_sel == "Nuovo...": mod_sel = st.text_input("Specifica Modello").title()
            
            marca_modello = f"{m_sel} {mod_sel}".strip()
            colore = st.selectbox("Colore", ["Nuovo..."] + lista_colori, index=idx_colore)
            if colore == "Nuovo...": colore = st.text_input("Specifica Colore")
            km = st.number_input("Chilometri", min_value=0)
            n_chiave = st.number_input("N. Chiave (0=Commerciante)", min_value=0)
            note = st.text_area("Note")

            if st.form_submit_button("REGISTRA VETTURA", disabled=not zona_attuale):
                aggiorna_attivita()
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("⚠️ Formato targa non valido")
                else:
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data:
                        st.error("ERRORE: Vettura già presente!")
                    else:
                        data = {"targa": targa, "marca_modello": marca_modello, "colore": colore, "km": km, "numero_chiave": n_chiave, "zona_attuale": zona_attuale, "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"In {zona_attuale}", utente_attivo)
                        st.success("Vettura registrata!")
                        st.rerun()

    # --- 2. RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Spostamento")
        foto_sposta = st.camera_input("Scansiona QR Nuova Zona", key="cam_sposta")
        if foto_sposta:
            n_z_letta = leggi_qr_zona(foto_sposta)
            if n_z_letta in ZONE_INFO:
                st.session_state["zona_rilevata_sposta"] = n_z_letta
                st.info(f"Nuova zona rilevata: {n_z_letta}")

        tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
        q = st.text_input(f"Inserisci {tipo}").strip()
        if q:
            col = "targa" if tipo == "Targa" else "numero_chiave"
            val = q.upper() if tipo == "Targa" else int(q) if q.isdigit() else None
            if val is not None:
                res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute()
                if res.data:
                    for v in res.data:
                        with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                            st.write(f"📍 Zona Attuale: **{v['zona_attuale']}**")
                            c1, c2 = st.columns(2)
                            zona_nuova = st.session_state.get("zona_rilevata_sposta", "")
                            if c1.button("SPOSTA IN NUOVA ZONA", key=f"b_{v['targa']}", disabled=not zona_nuova):
                                supabase.table("parco_usato").update({"zona_attuale": zona_nuova}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {zona_nuova}", utente_attivo)
                                st.session_state["zona_rilevata_sposta"] = ""
                                st.success("Spostata!")
                                st.rerun()
                            if c2.button("🔴 CONSEGNA", key=f"d_{v['targa']}"):
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", "Uscita definitiva", utente_attivo)
                                st.rerun()
                else: st.warning("Vettura non trovata.")

    # --- 3. MODIFICA (FIX FEEDBACK SALVATAGGIO) ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("Correzione Dati Vettura")
        tipo_mod = st.radio("Cerca per correggere:", ["Targa", "Numero Chiave"], horizontal=True, key="search_mod_type")
        q_mod = st.text_input(f"Inserisci {tipo_mod} da correggere").strip()
        
        if q_mod:
            col_f = "targa" if tipo_mod == "Targa" else "numero_chiave"
            val_f = q_mod.upper() if tipo_mod == "Targa" else int(q_mod) if q_mod.isdigit() else None
            if val_f is not None:
                res = supabase.table("parco_usato").select("*").eq(col_f, val_f).eq("stato", "PRESENTE").execute()
                if res.data:
                    v = res.data[0]
                    with st.form("f_modifica"):
                        st.info(f"Modifica dati per: {v['targa']}")
                        nuova_targa = st.text_input("Targa", value=v['targa']).upper().strip()
                        nuova_marca_mod = st.text_input("Marca/Modello", value=v['marca_modello'])
                        nuovo_colore = st.text_input("Colore", value=v['colore'])
                        nuovi_km = st.number_input("KM", value=int(v['km']))
                        nuova_chiave = st.number_input("N. Chiave", value=int(v['numero_chiave']))
                        nuova_zona = st.selectbox("Zona", list(ZONE_INFO.keys()), index=list(ZONE_INFO.keys()).index(v['zona_attuale']))
                        nuove_note = st.text_area("Note", value=v['note'])
                        
                        if st.form_submit_button("SALVA CORREZIONI"):
                            upd = {"targa": nuova_targa, "marca_modello": nuova_marca_mod, "colore": nuovo_colore, "km": nuovi_km, "numero_chiave": nuova_chiave, "zona_attuale": nuova_zona, "note": nuove_note}
                            supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                            registra_log(nuova_targa, "Modifica", f"Dati corretti da {utente_attivo}", utente_attivo)
                            
                            # --- FEEDBACK SALVATAGGIO ---
                            st.success("✅ Salvataggio avvenuto con successo!")
                            time.sleep(1) # Pausa per permettere la lettura
                            st.rerun()
                else: st.warning("Vettura non trovata.")

    # --- 4. VERIFICA ZONE ---
    elif scelta == "📋 Verifica Zone":
        aggiorna_attivita()
        st.subheader("Situazione Piazzale")
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()))
        res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
        st.metric(label=f"Veicoli in {z_sel}", value=f"{len(res.data)} / {ZONE_INFO[z_sel]}")
        if res.data:
            df = pd.DataFrame(res.data)[["targa", "marca_modello", "numero_chiave", "colore", "km"]]
            st.dataframe(df, use_container_width=True)

    # --- 5. EXPORT ---
    elif scelta == "📊 Export":
        aggiorna_attivita()
        res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        if res.data:
            df_ex = pd.DataFrame(res.data).drop(columns=["stato"], errors="ignore")
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_ex.to_excel(writer, index=False, sheet_name="Parco Usato")
            st.download_button("📥 Scarica Excel", output.getvalue(), "Parco_Usato.xlsx")

    # --- 6. LOG ---
    elif scelta == "📜 Log":
        st_autorefresh(interval=10000, key="log_refresh")
        logs = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(50).execute()
        if logs.data:
            df = pd.DataFrame(logs.data)
            df['created_at'] = pd.to_datetime(df['created_at']).dt.strftime('%d/%m/%Y %H:%M:%S')
            st.dataframe(df[["created_at", "targa", "azione", "dettaglio", "utente"]], use_container_width=True)

    # --- 🖨️ STAMPA QR ---
    elif scelta == "🖨️ Stampa QR":
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()))
        qr = qrcode.make(f"ZONA|{z_sel}")
        buf = BytesIO()
        qr.save(buf, format="PNG")
        st.image(buf.getvalue(), caption=f"QR {z_sel}", width=300)
        st.download_button("📥 Scarica QR", buf.getvalue(), f"QR_{z_sel}.png")
