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
from PIL import Image, ImageDraw

# --- 1. CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. CREDENZIALI & TIMEOUT ---
CREDENZIALI = {"Luca Simonini": "2026", "Ivan Pohorilyak": "1234", "Abdul": "0000"}
TIMEOUT_MINUTI = 15

# --- 3. CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}
ZONE_INFO_NORM = {k.strip().upper(): v for k, v in ZONE_INFO.items()}

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1", layout="wide")

# --- 4. GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'last_action' not in st.session_state:
    st.session_state['last_action'] = datetime.now()
if 'zona_rilevata' not in st.session_state:
    st.session_state['zona_rilevata'] = ""
if 'zona_rilevata_sposta' not in st.session_state:
    st.session_state['zona_rilevata_sposta'] = ""
if 'camera_attiva' not in st.session_state:
    st.session_state['camera_attiva'] = False

def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now()

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now() - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state['user_autenticato'] = None
            st.rerun()

# --- 5. FUNZIONI CORE (CON APPRENDIMENTO) ---
def registra_log(targa, azione, dettaglio, utente):
    try:
        supabase.table("log_movimenti").insert({
            "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente
        }).execute()
    except Exception as e:
        st.error(f"Errore Log: {e}")

# Auto-apprendimento Marche/Modelli [cite: 2026-01-02]
def get_marche():
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        marche = set()
        for r in res.data:
            if r.get("marca_modello"): 
                marche.add(r["marca_modello"].split()[0].upper())
        return sorted(list(marche))
    except: return []

def get_modelli(marca):
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        modelli = set()
        for r in res.data:
            full = r.get("marca_modello", "").upper()
            if full.startswith(marca.upper()):
                mod = full.replace(marca.upper(), "", 1).strip()
                if mod: modelli.add(mod)
        return sorted(list(modelli))
    except: return []

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

def leggi_qr_zona(image_file):
    try:
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if not data: return ""
        if data.startswith("ZONA|"):
            return data.replace("ZONA|", "").strip().upper()
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
        if u != "- Seleziona -" and p == CREDENZIALI.get(u):
            st.session_state['user_autenticato'] = u
            aggiorna_attivita(); st.rerun()
        else: st.error("PIN non corretto")
else:
    # --- 7. SIDEBAR ---
    utente_attivo = st.session_state['user_autenticato']
    with st.sidebar:
        st.info(f"👤 Operatore: {utente_attivo}")
        st.sidebar.markdown("### 📷 Scanner QR")
        st.checkbox("Attiva scanner fotocamera", key="camera_attiva")
        if st.button("Log-out"):
            st.session_state.clear(); st.rerun()

    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", "📋 Verifica Zone", "📊 Export", "📜 Log", "🖨️ Stampa QR"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")

    if scelta not in ["➕ Ingresso", "🔍 Ricerca/Sposta"]:
        st.session_state["zona_rilevata"] = ""; st.session_state["zona_rilevata_sposta"] = ""

    # --- 8. SEZIONE INGRESSO ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Registrazione Nuova Vettura")
        foto_z = None
        if st.session_state.camera_attiva:
            foto_z = st.camera_input("Scansiona QR della Zona (OBBLIGATORIO)", key="cam_in")
            if foto_z:
                z_letta = leggi_qr_zona(foto_z)
                if not z_letta: st.error("❌ QR non leggibile.")
                elif z_letta in ZONE_INFO_NORM:
                    orig = next(k for k in ZONE_INFO.keys() if k.strip().upper() == z_letta)
                    st.session_state["zona_rilevata"] = orig; st.success(f"Zona rilevata: {orig}")
                else: st.error(f"Zona '{z_letta}' non censita.")
        else: st.warning("⚠️ Scanner disattivato dalla Sidebar.")

        zona_attuale = st.session_state.get("zona_rilevata", "") if st.session_state.camera_attiva else ""
        with st.form("f_ingresso", clear_on_submit=True):
            if not zona_attuale: st.error("❌ Scansione QR Obbligatoria")
            else: st.info(f"📍 Zona: **{zona_attuale}**")
            targa = st.text_input("TARGA").upper().strip()
            
            # --- AUTO-APPRENDIMENTO MARCA/MODELLO/COLORE --- [cite: 2026-01-02]
            marche_esistenti = get_marche()
            m_sel = st.selectbox("Marca", ["Nuova..."] + marche_esistenti)
            if m_sel == "Nuova...": m_sel = st.text_input("Inserisci Marca").upper()
            
            modelli_esistenti = get_modelli(m_sel) if m_sel != "Nuova..." else []
            mod_sel = st.selectbox("Modello", ["Nuovo..."] + modelli_esistenti)
            if mod_sel == "Nuovo...": mod_sel = st.text_input("Inserisci Modello").upper()
            
            colore_suggerito = suggerisci_colore(targa) if targa else None
            if colore_suggerito: st.info(f"🎨 Suggerito: **{colore_suggerito}**")
            colore = st.selectbox("Colore", ["Nuovo..."] + get_colori(), index=0)
            if colore == "Nuovo...": colore = st.text_input("Specifica Colore")
            colore = colore.strip().capitalize()
            
            km = st.number_input("Chilometri", min_value=0, step=100)
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1)
            if n_chiave == 0: st.info("🤝 Valore 0 = Vettura destinata a COMMERCIANTE")
            note = st.text_area("Note")

            if st.form_submit_button("REGISTRA VETTURA", disabled=not zona_attuale):
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa): st.warning("Targa non valida")
                else:
                    check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                    if check.data: st.error("Vettura già presente!")
                    else:
                        data = {"targa": targa, "marca_modello": f"{m_sel} {mod_sel}".strip(), "colore": colore, "km": km, "numero_chiave": n_chiave, "zona_attuale": zona_attuale, "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                        supabase.table("parco_usato").insert(data).execute()
                        registra_log(targa, "Ingresso", f"In {zona_attuale}", utente_attivo)
                        st.success("✅ Registrata!"); st.session_state["zona_rilevata"] = ""; time.sleep(1); st.rerun()

    # --- 9. SEZIONE RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Spostamento")
        if st.session_state.camera_attiva:
            foto_sp = st.camera_input("Scansiona QR Nuova Zona", key="cam_sp")
            if foto_sp:
                n_z_letta = leggi_qr_zona(foto_sp)
                if n_z_letta in ZONE_INFO_NORM:
                    orig_sp = next(k for k in ZONE_INFO.keys() if k.strip().upper() == n_z_letta)
                    st.session_state["zona_rilevata_sposta"] = orig_sp; st.info(f"Destinazione: {orig_sp}")
        else: st.warning("⚠️ Scanner disattivato.")

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
                            st.write(f"📍 Posizione: **{v['zona_attuale']}**")
                            c1, c2 = st.columns(2)
                            zn = st.session_state.get("zona_rilevata_sposta", "") if st.session_state.camera_attiva else ""
                            if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not zn):
                                supabase.table("parco_usato").update({"zona_attuale": zn}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {zn}", utente_attivo)
                                st.session_state["zona_rilevata_sposta"] = ""; st.success("Spostata!"); time.sleep(1); st.rerun()
                            conf = st.checkbox("⚠️ Confermo CONSEGNA", key=f"conf_{v['targa']}")
                            if c2.button("🔴 CONSEGNA", key=f"d_{v['targa']}", disabled=not conf):
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", "Uscita", utente_attivo); st.rerun()

    # --- 10. MODIFICA ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("Correzione Dati")
        t_mod = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True, key="m_t")
        q_mod = st.text_input("Dato da cercare").strip()
        if q_mod:
            col_f = "targa" if t_mod == "Targa" else "numero_chiave"
            val_f = q_mod.upper() if t_mod == "Targa" else int(q_mod) if q_mod.isdigit() else None
            res = supabase.table("parco_usato").select("*").eq(col_f, val_f).eq("stato", "PRESENTE").execute()
            if res.data:
                v = res.data[0]
                with st.form("f_mod"):
                    upd = {
                        "targa": st.text_input("Targa", value=v['targa']).upper().strip(),
                        "marca_modello": st.text_input("Marca/Modello", value=v['marca_modello']).upper(),
                        "colore": st.text_input("Colore", value=v['colore']).strip().capitalize(),
                        "km": st.number_input("KM", value=int(v['km'])),
                        "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])),
                        "zona_attuale": st.selectbox("Zona", list(ZONE_INFO.keys()), index=list(ZONE_INFO.keys()).index(v['zona_attuale'])),
                        "note": st.text_area("Note", value=v['note'])
                    }
                    if st.form_submit_button("SALVA"):
                        if upd["targa"] != v["targa"]:
                            dup = supabase.table("parco_usato").select("targa").eq("targa", upd["targa"]).eq("stato", "PRESENTE").execute()
                            if dup.data: st.error("❌ Targa esistente!"); st.stop()
                        supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                        registra_log(upd["targa"], "Modifica", "Correzione", utente_attivo); st.success("✅ Salvato!"); time.sleep(1); st.rerun()

    # --- 11. ALTRE FUNZIONI ---
    elif scelta == "📋 Verifica Zone":
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()))
        res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
        st.metric("Veicoli", len(res.data))
        if res.data: st.dataframe(pd.DataFrame(res.data)[["targa", "marca_modello", "colore"]], use_container_width=True)

    elif scelta == "📊 Export":
        aggiorna_attivita()
        try:
            res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
            if res.data:
                df = pd.DataFrame(res.data)
                if "created_at" in df.columns: df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%d/%m/%Y %H:%M")
                df = df.drop(columns=["id", "stato"], errors="ignore")
                out = BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as w: df.to_excel(w, index=False)
                st.download_button("📥 Scarica Report", out.getvalue(), f"Piazzale_{datetime.now().strftime('%d_%m')}.xlsx")
        except: st.error("❌ Errore durante l'export.")

    elif scelta == "📜 Log":
        st_autorefresh(interval=10000, key="log_ref")
        logs = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(50).execute()
        if logs.data:
            df_l = pd.DataFrame(logs.data); df_l['Ora'] = pd.to_datetime(df_l['created_at']).dt.strftime('%d/%m/%Y %H:%M')
            st.dataframe(df_l[["Ora", "targa", "azione", "utente"]], use_container_width=True)

    elif scelta == "🖨️ Stampa QR":
        z = st.selectbox("Zona QR", list(ZONE_INFO.keys()))
        if z:
            qr_img = qrcode.make(f"ZONA|{z}"); buf = BytesIO(); qr_img.save(buf, format="PNG")
            st.image(buf.getvalue(), width=300); st.download_button("Scarica QR", buf.getvalue(), f"QR_{z}.png")
