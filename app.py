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

# --- 1. CONFIGURAZIONE DATABASE ---
# [cite: 2026-01-02]
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. CREDENZIALI & TIMEOUT ---
# [cite: 2026-01-02]
CREDENZIALI = {
    "Luca Simonini": "2026", 
    "Ivan Pohorilyak": "1234"
}
TIMEOUT_MINUTI = 10

# --- 3. CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1", layout="wide")

# --- 4. GESTIONE SESSIONE & STATO ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'last_action' not in st.session_state:
    st.session_state['last_action'] = datetime.now()
if 'zona_rilevata' not in st.session_state:
    st.session_state['zona_rilevata'] = ""
if 'zona_rilevata_sposta' not in st.session_state:
    st.session_state['zona_rilevata_sposta'] = ""
if 'camera_attiva' not in st.session_state:
    st.session_state['camera_attiva'] = True

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

def get_colori():
    try:
        res = supabase.table("parco_usato").select("colore").execute()
        colori = list(set([str(r['colore']).capitalize() for r in res.data if r['colore']]))
        return sorted(colori) if colori else ["Bianco", "Nero", "Grigio"]
    except: return ["Bianco", "Nero", "Grigio"]

def suggerisci_colore(targa_input):
    try:
        if len(targa_input) >= 7:
            res = supabase.table("parco_usato").select("colore").eq("targa", targa_input).order("created_at", desc=True).limit(1).execute()
            if res.data: return str(res.data[0]['colore']).capitalize()
        return None
    except: return None

def get_marche():
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        marche = set()
        for r in res.data:
            if r.get("marca_modello"): marche.add(r["marca_modello"].split()[0].capitalize())
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
        if data.startswith("ZONA|"): return data.replace("ZONA|", "").strip()
        return ""
    except: return ""

controllo_timeout()

# --- 6. LOGIN ---
if st.session_state['user_autenticato'] is None:
    st.title("🔐 Accesso Autoclub Center")
    opzioni_utenti = ["- Seleziona -"] + list(CREDENZIALI.keys())
    u = st.selectbox("Seleziona Operatore", opzioni_utenti)
    p = st.text_input("Inserisci PIN (4 cifre)", type="password")
    if st.button("ACCEDI"):
        if u == "- Seleziona -":
            st.warning("⚠️ Per favore, seleziona un operatore.")
        elif p == CREDENZIALI.get(u):
            st.session_state['user_autenticato'] = u
            aggiorna_attivita()
            st.rerun()
        else: st.error("PIN non corretto")
else:
    # --- 7. APP PRINCIPALE & FIX TOGGLE ---
    utente_attivo = st.session_state['user_autenticato']
    st.sidebar.info(f"Operatore: {utente_attivo}")

    def toggle_camera():
        if not st.session_state.camera_attiva:
            st.session_state["zona_rilevata"] = ""
            st.session_state["zona_rilevata_sposta"] = ""
            st.session_state.pop("cam_zona", None)
            st.session_state.pop("cam_sposta", None)

    st.sidebar.markdown("### 📷 Gestione Scanner")
    st.sidebar.toggle("Attiva scanner QR", key="camera_attiva", on_change=toggle_camera)

    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", "📋 Verifica Zone", "📊 Export", "📜 Log", "🖨️ Stampa QR"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")

    if scelta != "➕ Ingresso" and scelta != "🔍 Ricerca/Sposta":
        st.session_state["zona_rilevata"] = ""
        st.session_state["zona_rilevata_sposta"] = ""

    # --- 8. INGRESSO ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Registrazione Nuova Vettura")
        foto_z = st.camera_input("Scanner Zona QR (OBBLIGATORIO)", key="cam_zona") if st.session_state['camera_attiva'] else st.warning("📷 Scanner disattivato")
        if foto_z:
            z_letta = leggi_qr_zona(foto_z)
            if z_letta in ZONE_INFO:
                st.session_state["zona_rilevata"] = z_letta
                st.success(f"Zona rilevata: {z_letta}")
            else: st.error("QR non valido")
        
        zona_attuale = st.session_state.get("zona_rilevata", "")
        with st.form("f_ingresso", clear_on_submit=True):
            if not zona_attuale: st.error("❌ Scansione QR Obbligatoria")
            else: st.info(f"✅ Zona: **{zona_attuale}**")
            targa = st.text_input("TARGA").upper().strip()
            colore_suggerito = suggerisci_colore(targa) if targa else None
            lista_colori = get_colori()
            idx_colore = lista_colori.index(colore_suggerito) + 1 if colore_suggerito in lista_colori else 0
            
            marche = get_marche()
            m_sel = st.selectbox("Marca", ["Nuova..."] + marche)
            if m_sel == "Nuova...": m_sel = st.text_input("Specifica Marca").capitalize()
            mod_sel = st.selectbox("Modello", ["Nuovo..."] + get_modelli(m_sel))
            if mod_sel == "Nuovo...": mod_sel = st.text_input("Specifica Modello").title()
            
            colore = st.selectbox("Colore", ["Nuovo..."] + lista_colori, index=idx_colore)
            if colore == "Nuovo...": colore = st.text_input("Specifica Colore")
            km = st.number_input("Chilometri", min_value=0, step=100)
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1)
            note = st.text_area("Note")

            if st.form_submit_button("REGISTRA VETTURA", disabled=not zona_attuale):
                aggiorna_attivita()
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa): st.warning("⚠️ Targa non valida")
                else:
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data: st.error("ERRORE: Vettura già presente!")
                    else:
                        data = {"targa": targa, "marca_modello": f"{m_sel} {mod_sel}", "colore": colore, "km": km, "numero_chiave": n_chiave, "zona_attuale": zona_attuale, "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"In {zona_attuale}", utente_attivo)
                        st.success("✅ Vettura registrata!")
                        st.session_state["zona_rilevata"] = ""
                        time.sleep(1)
                        st.rerun()

    # --- 9. RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Movimentazione")
        foto_sposta = st.camera_input("Scannerizza QR Nuova Zona", key="cam_sposta") if st.session_state['camera_attiva'] else st.warning("📷 Scanner disattivato")
        if foto_sposta:
            n_z_letta = leggi_qr_zona(foto_sposta)
            if n_z_letta in ZONE_INFO:
                st.session_state["zona_rilevata_sposta"] = n_z_letta
                st.info(f"Nuova zona: {n_z_letta}")

        tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
        q = st.text_input(f"Digita {tipo}").strip()
        if q:
            col = "targa" if tipo == "Targa" else "numero_chiave"
            val = q.upper() if tipo == "Targa" else int(q) if q.isdigit() else None
            if val is not None:
                res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute()
                if res.data:
                    for v in res.data:
                        with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                            st.write(f"📍 Posizione: **{v['zona_attuale']}**")
                            c1, c2 = st.columns(2)
                            z_nuova = st.session_state.get("zona_rilevata_sposta", "")
                            if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not z_nuova):
                                supabase.table("parco_usato").update({"zona_attuale": z_nuova}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {z_nuova}", utente_attivo)
                                st.success(f"Spostata in {z_nuova}")
                                st.session_state["zona_rilevata_sposta"] = ""
                                time.sleep(1)
                                st.rerun()
                            if c2.button("🔴 CONSEGNA", key=f"d_{v['targa']}"):
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", "Uscita", utente_attivo)
                                st.rerun()
                else: st.warning("Nessuna vettura trovata.")

    # --- 10. MODIFICA ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("Correzione Dati")
        tipo_mod = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True, key="m_type")
        q_mod = st.text_input("Dato da cercare").strip()
        if q_mod:
            col_f = "targa" if tipo_mod == "Targa" else "numero_chiave"
            val_f = q_mod.upper() if tipo_mod == "Targa" else int(q_mod) if q_mod.isdigit() else None
            res = supabase.table("parco_usato").select("*").eq(col_f, val_f).eq("stato", "PRESENTE").execute()
            if res.data:
                v = res.data[0]
                with st.form("f_modifica"):
                    st.info(f"Modifica: {v['targa']}")
                    upd_data = {
                        "targa": st.text_input("Targa", value=v['targa']).upper().strip(),
                        "marca_modello": st.text_input("Marca/Modello", value=v['marca_modello']),
                        "colore": st.text_input("Colore", value=v['colore']),
                        "km": st.number_input("KM", value=int(v['km'])),
                        "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])),
                        "zona_attuale": st.selectbox("Zona", list(ZONE_INFO.keys()), index=list(ZONE_INFO.keys()).index(v['zona_attuale'])),
                        "note": st.text_area("Note", value=v['note'])
                    }
                    if st.form_submit_button("SALVA CORREZIONI"):
                        supabase.table("parco_usato").update(upd_data).eq("targa", v['targa']).execute()
                        registra_log(upd_data["targa"], "Modifica", "Dati corretti", utente_attivo)
                        st.success("✅ Salvataggio avvenuto con successo!")
                        time.sleep(1)
                        st.rerun()
            else: st.error("Veicolo non trovato.")

    # --- ALTRI MENU (VERIFICA, EXPORT, LOG, QR) ---
    elif scelta == "📋 Verifica Zone":
        aggiorna_attivita()
        z_sel = st.selectbox("Zona", list(ZONE_INFO.keys()))
        res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
        st.metric("Veicoli", len(res.data), delta_color="off")
        if res.data: st.dataframe(pd.DataFrame(res.data)[["targa", "marca_modello", "numero_chiave", "colore", "km"]], use_container_width=True)

    elif scelta == "📊 Export":
        aggiorna_attivita()
        res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        if res.data:
            df = pd.DataFrame(res.data).drop(columns=["id", "created_at", "stato"], errors="ignore")
            output = BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer: df.to_excel(writer, index=False, sheet_name="Piazzale")
            st.download_button("📥 Scarica Excel", output.getvalue(), "Report.xlsx")

    elif scelta == "📜 Log":
        st_autorefresh(interval=10000, key="log_refresh")
        logs = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(50).execute()
        if logs.data: st.dataframe(pd.DataFrame(logs.data)[["created_at", "targa", "azione", "dettaglio", "utente"]], use_container_width=True)

    elif scelta == "🖨️ Stampa QR":
        z_stampa = st.selectbox("Scegli Zona", list(ZONE_INFO.keys()))
        if z_stampa:
            qr = qrcode.QRCode(box_size=10, border=4)
            qr.add_data(f"ZONA|{z_stampa}")
            qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
            w, h = qr_img.size
            new_img = Image.new('RGB', (w, h + 60), 'white')
            new_img.paste(qr_img, (0, 0))
            ImageDraw.Draw(new_img).text((w/2 - 80, h + 20), f"ZONA: {z_stampa.upper()}", fill="black")
            buf = BytesIO()
            new_img.save(buf, format="PNG")
            st.image(buf.getvalue(), width=350)
            st.download_button("📥 Scarica QR", buf.getvalue(), f"QR_{z_stampa}.png")
