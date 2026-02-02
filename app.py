import streamlit as st
import os
from supabase import create_client
import pandas as pd
from datetime import datetime, timedelta, timezone
import time
from io import BytesIO
import re
import cv2
import numpy as np
import qrcode
from PIL import Image
from streamlit_autorefresh import st_autorefresh

# Pulizia cache all'avvio
st.cache_data.clear()
st.cache_resource.clear()

# --- 1. CONFIGURAZIONE DATABASE ---
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

# --- 2. CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Z01": "Deposito N.9", "Z02": "Deposito N.7", "Z03": "Deposito N.6 (Lavaggisti)",
    "Z04": "Deposito unificato 1 e 2", "Z05": "Showroom", "Z06": "Vetture vendute",
    "Z07": "Piazzale Lavaggio", "Z08": "Commercianti senza telo",
    "Z09": "Commercianti con telo", "Z10": "Lavorazioni esterni", "Z11": "Verso altre sedi"
}

TIMEOUT_MINUTI = 20

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1 Master", layout="wide")

# --- 3. GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'ruolo' not in st.session_state:
    st.session_state['ruolo'] = None
if 'last_action' not in st.session_state:
    st.session_state['last_action'] = datetime.now(timezone.utc)
if 'zona_id' not in st.session_state: st.session_state['zona_id'] = ""
if 'zona_nome' not in st.session_state: st.session_state['zona_nome'] = ""
if 'zona_id_sposta' not in st.session_state: st.session_state['zona_id_sposta'] = ""
if 'zona_nome_sposta' not in st.session_state: st.session_state['zona_nome_sposta'] = ""
if 'camera_attiva' not in st.session_state:
    st.session_state['camera_attiva'] = False
if "ingresso_salvato" not in st.session_state:
    st.session_state["ingresso_salvato"] = False

def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now(timezone.utc)

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now(timezone.utc) - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state['user_autenticato'] = None
            st.session_state['ruolo'] = None
            st.rerun()

# --- 4. FUNZIONI LOGIN & DATABASE ---
def login_db(nome, pin):
    try:
        res = supabase.table("utenti").select("nome, ruolo").eq("nome", nome).eq("pin", pin).eq("attivo", True).limit(1).execute()
        return res.data[0] if res.data else None
    except: return None

def get_lista_utenti_login():
    try:
        res = supabase.table("utenti").select("nome").eq("attivo", True).order("nome").execute()
        return [u["nome"] for u in res.data] if res.data else []
    except: return []

# --- 5. FUNZIONI CORE ---
def feedback_ricerca(tipo, valore, risultati):
    if valore is None or valore == "":
        st.info("⌨️ Inserisci un valore per iniziare la ricerca")
        return False
    with st.spinner("🔍 Ricerca in corso..."):
        time.sleep(0.3)
    if not risultati:
        st.error(f"❌ Nessun risultato trovato per {tipo}: {valore}")
        return False
    st.success(f"✅ {len(risultati)} risultato/i trovato/i per {tipo}: {valore}")
    return True

def aggiorna_presenza(utente, pagina=""):
    try:
        supabase.table("sessioni_attive").upsert({
            "utente": utente,
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "pagina": pagina
        }).execute()
    except: pass

def get_operatori_attivi(minuti=5):
    try:
        limite = (datetime.now(timezone.utc) - timedelta(minutes=minuti)).isoformat()
        res = supabase.table("sessioni_attive").select("*").gte("last_seen", limite).execute()
        return res.data if res.data else []
    except: return []

def registra_log(targa, azione, d, u):
    try:
        n_chiave = 0
        v_info = supabase.table("parco_usato").select("numero_chiave").eq("targa", targa).limit(1).execute()
        if v_info.data: n_chiave = v_info.data[0]["numero_chiave"]
        supabase.table("log_movimenti").insert({
            "targa": targa, "azione": azione, "dettaglio": d, "utente": u, 
            "numero_chiave": n_chiave, "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e: st.error(f"Errore Log: {e}")

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

# --- 6. LOGIN & MENU PRINCIPALE ---
if st.session_state['user_autenticato'] is None:
    st.title("🔐 Accesso Autoclub Center Usato 1.1")
    lista_u = get_lista_utenti_login()
    u = st.selectbox("Operatore", ["- Seleziona -"] + lista_u)
    p = st.text_input("PIN", type="password")
    if st.button("ACCEDI", use_container_width=True):
        user = login_db(u, p)
        if user:
            st.session_state['user_autenticato'] = user["nome"]
            st.session_state['ruolo'] = user["ruolo"]
            aggiorna_attivita()
            st.rerun()
        else: st.error("Accesso negato: PIN errato o utente non attivo")
else:
    utente_attivo = st.session_state['user_autenticato']
    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", 
            "📋 Verifica Zone", "📊 Dashboard Zone", "📊 Dashboard Generale", 
            "📊 Export", "📜 Log", "🖨️ Stampa QR", "♻️ Ripristina"]
    
    if st.session_state["ruolo"] == "admin":
        menu.append("👥 Gestione Utenti")
    
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.session_state["pagina_attuale"] = scelta
    st.markdown("---")

    # --- 7. SIDEBAR ---
    with st.sidebar:
        st.info(f"👤 {utente_attivo} ({st.session_state['ruolo']})")
        st_autorefresh(interval=30000, key="presence_heartbeat")
        aggiorna_presenza(utente_attivo, st.session_state["pagina_attuale"])
        
        st.markdown("### 👥 Operatori attivi")
        attivi = get_operatori_attivi(minuti=15)
        if attivi:
            for o in attivi:
                stato = "🟡" if o["utente"] == utente_attivo else "🟢"
                st.caption(f"{stato} **{o['utente']}**\n_{o.get('pagina','')}_")
        else:
            st.caption("Nessun altro operatore collegato")
        
        st.markdown("---")
        st.markdown("### 📷 Scanner QR")
        st.checkbox("Attiva scanner", key="camera_attiva")
        if st.button("Log-out"):
            st.session_state.clear()
            st.rerun()

    # --- 8. SEZIONE INGRESSO ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Registrazione Nuova Vettura")
        
        if not st.session_state.camera_attiva:
            st.warning("⚠️ Per registrare una nuova vettura è necessario **attivare lo scanner QR code** nella Sidebar.")
        
        if st.session_state.camera_attiva:
            foto_z = st.camera_input("Scansiona QR della Zona", key="cam_in")
            if foto_z:
                z_id = leggi_qr_zona(foto_z)
                if z_id:
                    st.session_state["zona_id"] = z_id
                    st.session_state["zona_nome"] = ZONE_INFO[z_id]
                    st.success(f"✅ Zona rilevata: {st.session_state['zona_nome']}")
                else: st.error("❌ QR non valido")

        with st.form("f_ingresso"):
            if not st.session_state['zona_id']: st.error("❌ Scansione QR Obbligatoria per abilitare i campi")
            else: st.info(f"📍 Zona: **{st.session_state['zona_nome']}**")
           
            targa = st.text_input("TARGA").upper().strip()
            marca = st.text_input("Marca").upper().strip()
            modello = st.text_input("Modello").upper().strip()
            colore = st.text_input("Colore").capitalize().strip()
            km = st.number_input("Chilometri", min_value=0, step=100)
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1)
            st.caption("ℹ️ Nota: Il valore **Chiave = 0** indica vetture destinate ai commercianti.")
            note = st.text_area("Note")
            submit = st.form_submit_button("REGISTRA LA VETTURA", disabled=not st.session_state['zona_id'])

            if submit:
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa): st.error("Targa non valida"); st.stop()
                check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                if check.data: st.error("Targa già presente"); st.stop()
                
                payload = {
                    "targa": targa, "marca_modello": f"{marca} {modello}", "colore": colore, "km": int(km),
                    "numero_chiave": int(n_chiave), "zona_id": st.session_state["zona_id"], 
                    "zona_attuale": st.session_state["zona_nome"], "data_ingresso": datetime.now(timezone.utc).isoformat(),
                    "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo
                }
                supabase.table("parco_usato").insert(payload).execute()
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
                st.session_state["ingresso_salvato"] = {"targa": targa, "zona": st.session_state["zona_nome"], "ora": datetime.now(timezone.utc)}
                st.rerun()

        info = st.session_state.get("ingresso_salvato")
        if info:
            st.success(f"✅ Vettura {info['targa']} registrata in {info['zona']}")
            if st.button("PULISCI E NUOVO INSERIMENTO"):
                st.session_state["zona_id"] = ""; st.session_state["ingresso_salvato"] = False; st.rerun()

    # --- 9. SEZIONE RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Spostamento")
        tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
        q = st.text_input("Dato da cercare").strip().upper()
        if q:
            col = "targa" if tipo == "Targa" else "numero_chiave"
            val = q if tipo == "Targa" else int(q) if q.isdigit() else None
            if val is not None:
                res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute()
                if feedback_ricerca(tipo, q, res.data):
                    for v in res.data:
                        with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                            st.write(f"📍 Posizione attuale: **{v['zona_attuale']}**")
                            
                            if not st.session_state.camera_attiva:
                                st.info("ℹ️ Per spostare la vettura, **attiva lo scanner QR code** nella Sidebar per inquadrare la destinazione.")
                            
                            if st.session_state.camera_attiva:
                                foto_sp = st.camera_input(f"Scanner QR Destinazione", key=f"cam_{v['targa']}")
                                if foto_sp:
                                    z_id_sp = leggi_qr_zona(foto_sp)
                                    if z_id_sp:
                                        st.session_state["zona_id_sposta"] = z_id_sp
                                        st.session_state["zona_nome_sposta"] = ZONE_INFO[z_id_sp]
                                        st.success(f"🎯 Destinazione rilevata: {st.session_state['zona_nome_sposta']}")
                            
                            c1, c2 = st.columns(2)
                            if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not st.session_state['zona_id_sposta'], use_container_width=True):
                                supabase.table("parco_usato").update({"zona_id": st.session_state["zona_id_sposta"], "zona_attuale": st.session_state["zona_nome_sposta"]}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {st.session_state['zona_nome_sposta']}", utente_attivo)
                                st.session_state["zona_id_sposta"] = ""; st.success("✅ Spostata!"); time.sleep(1); st.rerun()
                            
                            with c2:
                                st.write("---")
                                conferma_consegna = st.checkbox("Confermo la CONSEGNA definitiva", key=f"conf_{v['targa']}")
                                if st.button("🔴 CONSEGNA", key=f"btn_{v['targa']}", disabled=not conferma_consegna, use_container_width=True):
                                    supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                    registra_log(v['targa'], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                    st.success("✅ CONSEGNATA"); time.sleep(1); st.rerun()

    # --- 10. SEZIONE MODIFICA ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("Correzione Dati")
        q_mod = st.text_input("Targa o Chiave").strip().upper()
        if q_mod:
            col_m = "targa" if not q_mod.isdigit() else "numero_chiave"
            val_m = q_mod if not q_mod.isdigit() else int(q_mod)
            res = supabase.table("parco_usato").select("*").eq(col_m, val_m).eq("stato", "PRESENTE").execute()
            if feedback_ricerca("Dato", q_mod, res.data):
                v = res.data[0]
                with st.form("f_mod"):
                    upd = {
                        "marca_modello": st.text_input("Modello", value=v['marca_modello']).upper(),
                        "colore": st.text_input("Colore", value=v['colore']).capitalize(),
                        "km": st.number_input("KM", value=int(v['km'])),
                        "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])),
                        "note": st.text_area("Note", value=v['note'])
                    }
                    if st.form_submit_button("SALVA MODIFICHE"):
                        supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                        registra_log(v['targa'], "Modifica", "Correzione manuale", utente_attivo)
                        st.success("✅ Aggiornato"); time.sleep(1); st.rerun()

    # --- 11. DASHBOARD GENERALE ---
    elif scelta == "📊 Dashboard Generale":
        st.subheader("📊 Dashboard Generale")
        res_p = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        presenti = res_p.data or []
        st.metric("🚗 In Piazzale", len(presenti))
        # Logica KPI rapida
        inizio_oggi = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        res_log = supabase.table("log_movimenti").select("azione").gte("created_at", inizio_oggi.isoformat()).execute()
        azioni = [r["azione"] for r in res_log.data] if res_log.data else []
        g1, g2, g3 = st.columns(3)
        g1.metric("➕ Ingressi Oggi", azioni.count("Ingresso"))
        g2.metric("🔄 Spostamenti Oggi", azioni.count("Spostamento"))
        g3.metric("🔴 Consegne Oggi", azioni.count("Consegna"))

    # --- 12. EXPORT ---
    elif scelta == "📊 Export":
        st.subheader("📊 Export Piazzale")
        res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.dataframe(df[["targa", "marca_modello", "zona_attuale", "numero_chiave"]], use_container_width=True)
            out = BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as w: df.to_excel(w, index=False)
            st.download_button("📥 SCARICA EXCEL", out.getvalue(), "Piazzale.xlsx", use_container_width=True)

    # --- 13. VERIFICA ZONE ---
    elif scelta == "📋 Verifica Zone":
        st.subheader("📋 Analisi per Zona")
        z_v = st.selectbox("Scegli Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("parco_usato").select("*").eq("zona_id", z_v).eq("stato", "PRESENTE").execute()
        if res.data: st.dataframe(pd.DataFrame(res.data)[["targa", "marca_modello", "colore"]], use_container_width=True)
        else: st.warning("Zona vuota")

    # --- 14. LOG ---
    elif scelta == "📜 Log":
        st.subheader("📜 Registro Movimenti")
        res = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(50).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df["Ora"] = pd.to_datetime(df["created_at"]).dt.tz_convert("Europe/Rome").dt.strftime("%H:%M:%S")
            st.dataframe(df[["Ora", "targa", "azione", "utente", "dettaglio"]], use_container_width=True)

    # --- 15. STAMPA QR ---
    elif scelta == "🖨️ Stampa QR":
        st.subheader("🖨️ Generatore QR Zone")
        z_qr = st.selectbox("Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        qr_obj = qrcode.make(f"ZONA|{z_qr}")
        buf = BytesIO(); qr_obj.save(buf, format="PNG")
        st.image(buf.getvalue(), width=250)
        st.download_button("DOWNLOAD QR", buf.getvalue(), f"QR_{z_qr}.png")

    # --- 16. RIPRISTINA ---
    elif scelta == "♻️ Ripristina":
        st.subheader("♻️ Ripristino")
        t_r = st.text_input("Targa Consegnata").upper().strip()
        if t_r and st.button(f"RIPRISTINA {t_r}"):
            supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", t_r).execute()
            registra_log(t_r, "Ripristino", "Riportata in stock", utente_attivo)
            st.success("✅ Ripristinata"); time.sleep(1); st.rerun()

    # --- 17. DASHBOARD ZONE ---
    elif scelta == "📊 Dashboard Zone":
        st.subheader("📍 Storico Zona")
        z_sel = st.selectbox("Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[z_sel]}%").limit(50).execute()
        if res.data: st.dataframe(pd.DataFrame(res.data)[["targa", "azione", "utente"]], use_container_width=True)

    # --- 18. GESTIONE UTENTI (ADMIN ONLY) ---
    elif scelta == "👥 Gestione Utenti":
        st.subheader("👥 Gestione Utenti (Admin)")
        if st.session_state["ruolo"] != "admin":
            st.error("Accesso non autorizzato"); st.stop()

        res = supabase.table("utenti").select("*").order("nome").execute()
        if res.data:
            df_ut = pd.DataFrame(res.data)
            st.dataframe(df_ut[["nome", "ruolo", "attivo"]], use_container_width=True)

        st.markdown("### ➕ Aggiungi Utente")
        with st.form("add_user"):
            n = st.text_input("Nome e Cognome")
            p = st.text_input("PIN (4-6 cifre)", type="password")
            r = st.selectbox("Ruolo", ["operatore", "admin"])
            if st.form_submit_button("CREA"):
                if n and p:
                    supabase.table("utenti").insert({"nome": n, "pin": p, "ruolo": r, "attivo": True}).execute()
                    st.success("Utente creato"); time.sleep(1); st.rerun()

        st.markdown("### ✏️ Modifica/Disattiva")
        u_mod = st.selectbox("Utente da modificare", [u["nome"] for u in res.data])
        ut_data = next(u for u in res.data if u["nome"] == u_mod)
        with st.form("edit_user"):
            new_p = st.text_input("Nuovo PIN (vuoto per mantenere)", type="password")
            new_r = st.selectbox("Ruolo", ["operatore", "admin"], index=0 if ut_data["ruolo"]=="operatore" else 1)
            is_active = st.checkbox("Attivo", value=ut_data["attivo"])
            if st.form_submit_button("SALVA"):
                upd = {"ruolo": new_r, "attivo": is_active}
                if new_p: upd["pin"] = new_p
                supabase.table("utenti").update(upd).eq("nome", u_mod).execute()
                st.success("Aggiornato"); time.sleep(1); st.rerun()
