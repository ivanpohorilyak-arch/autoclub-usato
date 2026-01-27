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

# --- 1. CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. CREDENZIALI & TIMEOUT ---
CREDENZIALI = {"Luca Simonini": "2026", "Ivan Pohorilyak": "1234", "Abdul": "0000"}
TIMEOUT_MINUTI = 15

# --- 3. CONFIGURAZIONE ZONE BLINDATE ---
ZONE_INFO = {
    "Z01": "Deposito N.9", "Z02": "Deposito N.7", "Z03": "Deposito N.6 (Lavaggisti)",
    "Z04": "Deposito unificato 1 e 2", "Z05": "Showroom", "Z06": "Vetture vendute",
    "Z07": "Piazzale Lavaggio", "Z08": "Commercianti senza telo",
    "Z09": "Commercianti con telo", "Z10": "Lavorazioni esterni", "Z11": "Verso altre sedi"
}

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1 Master", layout="wide")

# --- 7. STYLE PREMIUM (CSS) ---
st.markdown("""
    <style>
    .stApp { background-color: #f8f9fa; }
    .stButton > button {
        width: 100%; border-radius: 12px !important; height: 3.5em !important;
        font-weight: 700 !important; transition: all 0.3s ease !important;
        border: none !important; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-transform: uppercase;
    }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 8px 15px rgba(0,0,0,0.2); }
    div[data-testid="stForm"] button[kind="primary"], .stButton button:contains("REGISTRA") {
        background: linear-gradient(135deg, #28a745, #218838) !important; color: white !important;
    }
    .stButton button:contains("SPOSTA") {
        background: linear-gradient(135deg, #007bff, #0056b3) !important; color: white !important;
    }
    .stButton button:contains("CONSEGNA") {
        background: linear-gradient(135deg, #dc3545, #c82333) !important; color: white !important;
    }
    .stButton button:contains("SALVA") {
        background: linear-gradient(135deg, #fd7e14, #e36209) !important; color: white !important;
    }
    .stButton button:contains("ACCEDI") { background: #343a40 !important; color: white !important; }
    .stCheckbox { background-color: #fff3cd; padding: 10px; border-radius: 10px; border-left: 5px solid #ffc107; }
    </style>
    """, unsafe_allow_html=True)

# --- 4. GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state: st.session_state['user_autenticato'] = None
if 'last_action' not in st.session_state: st.session_state['last_action'] = datetime.now()
if 'zona_id' not in st.session_state: st.session_state['zona_id'] = ""
if 'zona_nome' not in st.session_state: st.session_state['zona_nome'] = ""
if 'zona_id_sposta' not in st.session_state: st.session_state['zona_id_sposta'] = ""
if 'zona_nome_sposta' not in st.session_state: st.session_state['zona_nome_sposta'] = ""
if 'camera_attiva' not in st.session_state: st.session_state['camera_attiva'] = False

def aggiorna_attivita(): st.session_state['last_action'] = datetime.now()

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now() - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state['user_autenticato'] = None
            st.rerun()

# --- 5. FUNZIONI CORE ---
def registra_log(targa, azione, d, u):
    try: supabase.table("log_movimenti").insert({"targa": targa, "azione": azione, "dettaglio": d, "utente": u}).execute()
    except Exception as e: st.error(f"Errore Log: {e}")

def get_marche():
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        marche = {r["marca_modello"].split()[0].upper() for r in res.data if r.get("marca_modello")}
        return sorted(list(marche))
    except: return []

def get_modelli(marca):
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        modelli = {r["marca_modello"].upper().replace(marca.upper(), "").strip() for r in res.data if r.get("marca_modello") and r["marca_modello"].upper().startswith(marca.upper())}
        return sorted([m for m in modelli if m])
    except: return []

def get_colori():
    try:
        res = supabase.table("parco_usato").select("colore").execute()
        colori = {str(r['colore']).capitalize() for r in res.data if r.get('colore')}
        return sorted(list(colori)) if colori else ["Bianco", "Nero", "Grigio"]
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
        if not data or not data.startswith("ZONA|"): return None
        z_id = data.replace("ZONA|", "").strip()
        return z_id if z_id in ZONE_INFO else None
    except: return None

controllo_timeout()

# --- 6. LOGIN ---
if st.session_state['user_autenticato'] is None:
    st.title("🔐 Accesso Autoclub Center Usato")
    u = st.selectbox("Operatore", ["- Seleziona -"] + list(CREDENZIALI.keys()))
    p = st.text_input("PIN", type="password")
    if st.button("ACCEDI"):
        if u != "- Seleziona -" and p == CREDENZIALI.get(u):
            st.session_state['user_autenticato'] = u
            aggiorna_attivita(); st.rerun()
        else: st.error("Accesso negato")
else:
    utente_attivo = st.session_state['user_autenticato']
    with st.sidebar:
        st.info(f"👤 Operatore: **{utente_attivo}**")
        st.sidebar.markdown("### 📷 Scanner QR")
        st.checkbox("Attiva fotocamera", key="camera_attiva")
        if st.button("Log-out"): st.session_state.clear(); st.rerun()

    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", "📋 Verifica Zone", "📊 Dashboard Zone", "📊 Export", "📜 Log", "🖨️ Stampa QR", "♻️ Ripristina"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")

    # --- 8. SEZIONE INGRESSO ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("➕ Registrazione Nuova Vettura")
        if st.session_state.camera_attiva:
            foto_z = st.camera_input("Scansiona QR della Zona", key="cam_in")
            if foto_z:
                z_id = leggi_qr_zona(foto_z)
                if z_id:
                    st.session_state["zona_id"] = z_id
                    st.session_state["zona_nome"] = ZONE_INFO[z_id]
                    st.success(f"✅ Zona rilevata: {st.session_state['zona_nome']}")
                else: st.error("❌ QR non valido")

        with st.form("f_ingresso", clear_on_submit=True):
            if not st.session_state['zona_id']: st.error("❌ Scansione QR Obbligatoria")
            else: st.info(f"📍 Zona: **{st.session_state['zona_nome']}**")
           
            targa = st.text_input("TARGA").upper().strip()
            marche = get_marche()
            m_sel = st.selectbox("Marca", ["Nuova..."] + marche)
            if m_sel == "Nuova...": m_sel = st.text_input("Inserisci Marca").upper()
            mod_sel = st.selectbox("Modello", ["Nuovo..."] + get_modelli(m_sel))
            if mod_sel == "Nuovo...": mod_sel = st.text_input("Inserisci Modello").upper()
            
            c_sug = suggerisci_colore(targa) if targa else None
            colore = st.selectbox("Colore", ["Nuovo..."] + get_colori())
            if colore == "Nuovo...": colore = st.text_input("Specifica Colore")
            km = st.number_input("Chilometri", min_value=0, step=100)
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1)
            note = st.text_area("Note")

            if st.form_submit_button("💾 REGISTRA LA VETTURA", disabled=not st.session_state['zona_id']):
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa): st.warning("❌ Targa non valida"); st.stop()
                if not m_sel.strip() or not mod_sel.strip(): st.warning("❌ Marca e Modello obbligatori"); st.stop()
                check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                if check.data: st.error("❌ Vettura già presente!"); st.stop()

                data = {"targa": targa, "marca_modello": f"{m_sel.strip()} {mod_sel.strip()}", "colore": colore.strip().capitalize(), "km": int(km), "numero_chiave": int(n_chiave), "zona_id": st.session_state["zona_id"], "zona_attuale": st.session_state["zona_nome"], "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo}
                supabase.table("parco_usato").insert(data).execute()
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
                st.success("✅ Vettura registrata!"); st.session_state["zona_id"] = ""; time.sleep(1); st.rerun()

    # --- 9. SEZIONE RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("🔍 Ricerca e Spostamento")
        if st.session_state.camera_attiva:
            foto_sp = st.camera_input("Scansiona QR della Zona di DESTINAZIONE", key="cam_sp")
            if foto_sp:
                z_id_sp = leggi_qr_zona(foto_sp)
                if z_id_sp:
                    st.session_state["zona_id_sposta"] = z_id_sp
                    st.session_state["zona_nome_sposta"] = ZONE_INFO[z_id_sp]
                    st.info(f"✅ Destinazione rilevata: {st.session_state['zona_nome_sposta']}")

        tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
        q = st.text_input("Inserisci dato").strip().upper()
       
        if q:
            col = "targa" if tipo == "Targa" else "numero_chiave"
            val = q if tipo == "Targa" else int(q) if q.isdigit() else None
            if val is not None:
                res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute()
                if res.data:
                    for v in res.data:
                        with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                            st.write(f"📍 Posizione: **{v['zona_attuale']}**")
                            c1, c2 = st.columns(2)
                            if c1.button("📍 SPOSTA QUI", key=f"b_{v['targa']}", disabled=not st.session_state['zona_id_sposta']):
                                supabase.table("parco_usato").update({"zona_id": st.session_state["zona_id_sposta"], "zona_attuale": st.session_state["zona_nome_sposta"]}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {st.session_state['zona_nome_sposta']}", utente_attivo)
                                st.session_state["zona_id_sposta"] = ""; st.success("✅ Spostata!"); time.sleep(1); st.rerun()
                            with c2:
                                conf_key = f"conf_{v['targa']}"
                                st.checkbox("⚠️ Confermo CONSEGNA", key=conf_key)
                                if st.button("🔴 CONSEGNA DEFINITIVA", key=f"btn_{v['targa']}", disabled=not st.session_state[conf_key]):
                                    supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                    registra_log(v['targa'], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                    st.success("✅ CONSEGNA REGISTRATA"); time.sleep(1); st.rerun()
                else: st.error("❌ Nessun veicolo trovato.")

    # --- 10. MODIFICA ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("✏️ Correzione Dati")
        q_mod = st.text_input("Inserisci Targa da modificare").strip().upper()
        if q_mod:
            res = supabase.table("parco_usato").select("*").eq("targa", q_mod).eq("stato", "PRESENTE").execute()
            if res.data:
                v = res.data[0]
                with st.form("f_mod"):
                    z_nome_sel = st.selectbox("Zona", list(ZONE_INFO.values()), index=list(ZONE_INFO.values()).index(v['zona_attuale']) if v['zona_attuale'] in ZONE_INFO.values() else 0)
                    z_id_sel = next(k for k, val in ZONE_INFO.items() if val == z_nome_sel)
                    upd = {"targa": st.text_input("Targa", value=v['targa']).upper().strip(), "marca_modello": st.text_input("Modello", value=v['marca_modello']).upper(), "colore": st.text_input("Colore", value=v['colore']).capitalize(), "km": st.number_input("KM", value=int(v['km'])), "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])), "zona_id": z_id_sel, "zona_attuale": z_nome_sel, "note": st.text_area("Note", value=v['note'])}
                    if st.form_submit_button("💾 SALVA MODIFICHE"):
                        supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                        registra_log(upd["targa"], "Modifica", "Correzione", utente_attivo); st.success("✅ Salvato!"); time.sleep(1); st.rerun()
            else: st.error("❌ Veicolo non trovato.")

    # --- 11. ANALISI & UTILITY ---
    elif scelta == "📊 Dashboard Zone":
        st.subheader("📍 Movimenti per Zona")
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        if z_sel:
            res = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[z_sel]}%").order("created_at", desc=True).limit(100).execute()
            if res.data:
                df = pd.DataFrame(res.data)
                df["Ora"] = pd.to_datetime(df["created_at"]).dt.strftime("%d/%m/%Y %H:%M")
                st.metric("Movimenti Totali", len(df))
                st.dataframe(df[["Ora", "targa", "azione", "utente"]], use_container_width=True)

    elif scelta == "📋 Verifica Zone":
        st.subheader("📋 Analisi Capienza")
        z_id_v = st.selectbox("Zona da analizzare", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        if z_id_v:
            res = supabase.table("parco_usato").select("*").eq("zona_id", z_id_v).eq("stato", "PRESENTE").execute()
            occupati = len(res.data) if res.data else 0
            st.metric("Posti Occupati", f"{occupati}/100")
            st.progress(min(occupati / 100, 1.0))
            if res.data: st.dataframe(pd.DataFrame(res.data)[["targa", "marca_modello", "colore"]], use_container_width=True)

    elif scelta == "📊 Export":
        st.subheader("📊 Export Piazzale")
        z_exp = st.selectbox("Zona da esportare", ["TUTTE"] + list(ZONE_INFO.keys()), format_func=lambda x: "TUTTE LE ZONE" if x == "TUTTE" else f"{x} - {ZONE_INFO[x]}")
        try:
            q = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE")
            if z_exp != "TUTTE": q = q.eq("zona_id", z_exp)
            res = q.execute()
            if res.data:
                df = pd.DataFrame(res.data)
                df["Data Inserimento"] = pd.to_datetime(df["created_at"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M") if "created_at" in df.columns else ""
                df_out = df[["targa", "marca_modello", "colore", "km", "numero_chiave", "zona_attuale", "Data Inserimento", "note"]].copy()
                st.dataframe(df_out, use_container_width=True)
                out = BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as w: df_out.to_excel(w, index=False)
                st.download_button("📥 SCARICA REPORT EXCEL", out.getvalue(), f"Piazzale_{z_exp}.xlsx")
        except Exception as e: st.error(f"❌ Errore: {e}")

    elif scelta == "📜 Log":
        st_autorefresh(interval=10000, key="log_ref")
        logs = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(50).execute()
        if logs.data:
            df_l = pd.DataFrame(logs.data)
            df_l['Ora'] = pd.to_datetime(df_l['created_at']).dt.strftime('%d/%m/%Y %H:%M')
            st.dataframe(df_l[["Ora", "targa", "azione", "utente"]], use_container_width=True)

    elif scelta == "🖨️ Stampa QR":
        z_pr = st.selectbox("Zona QR", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        if z_pr:
            qr_img = qrcode.make(f"ZONA|{z_pr}"); buf = BytesIO(); qr_img.save(buf, format="PNG")
            st.image(buf.getvalue(), width=300); st.download_button("📥 SCARICA QR", buf.getvalue(), f"QR_{z_pr}.png")

    elif scelta == "♻️ Ripristina":
        targa_back = st.text_input("Targa da ripristinare").upper().strip()
        if targa_back:
            res = supabase.table("parco_usato").select("*").eq("targa", targa_back).eq("stato", "CONSEGNATO").execute()
            if res.data:
                if st.button(f"♻️ RIPRISTINA {targa_back}"):
                    supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", targa_back).execute()
                    registra_log(targa_back, "Ripristino", "Riportata in PRESENTE", utente_attivo)
                    st.success("✅ Ripristinata!"); time.sleep(1); st.rerun()
