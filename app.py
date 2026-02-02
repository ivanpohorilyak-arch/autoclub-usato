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

# ================== CACHE ==================
st.cache_data.clear()
st.cache_resource.clear()

# ================== DATABASE ==================
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

# ================== ZONE ==================
ZONE_INFO = {
    "Z01": "Deposito N.9", "Z02": "Deposito N.7", "Z03": "Deposito N.6 (Lavaggisti)",
    "Z04": "Deposito unificato 1 e 2", "Z05": "Showroom", "Z06": "Vetture vendute",
    "Z07": "Piazzale Lavaggio", "Z08": "Commercianti senza telo",
    "Z09": "Commercianti con telo", "Z10": "Lavorazioni esterni", "Z11": "Verso altre sedi"
}

TIMEOUT_MINUTI = 20

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1 Master", layout="wide")

# ================== SESSIONE ==================
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

# --- CAMPI INGRESSO ---
for k in ["i_marca", "i_modello", "i_colore", "i_km", "i_chiave", "i_note"]:
    if k not in st.session_state:
        st.session_state[k] = "" if k not in ["i_km", "i_chiave"] else 0

# ================== FUNZIONI ==================
def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now(timezone.utc)

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now(timezone.utc) - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state.clear()
            st.rerun()

def login_db(nome, pin):
    try:
        res = supabase.table("utenti").select("nome, ruolo").eq("nome", nome).eq("pin", pin).eq("attivo", True).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Errore login: {e}")
        return None

def get_lista_utenti_login():
    try:
        res = supabase.table("utenti").select("nome").eq("attivo", True).order("nome").execute()
        return [u["nome"] for u in res.data] if res.data else []
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
    except: pass

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

# ================== INTERFACCIA LOGIN ==================
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
        else: st.error("Accesso negato")
    st.stop()

# ================== NAVIGAZIONE ==================
utente_attivo = st.session_state['user_autenticato']
menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", "📋 Verifica Zone", 
        "📊 Dashboard Zone", "📊 Dashboard Generale", "📊 Export", "📜 Log", "🖨️ Stampa QR", "♻️ Ripristina"]

if st.session_state["ruolo"] == "admin":
    menu.append("👥 Gestione Utenti")

scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
st.markdown("---")

# ================== SIDEBAR ==================
with st.sidebar:
    st.info(f"👤 {utente_attivo} ({st.session_state['ruolo']})")
    st.checkbox("📷 Attiva scanner QR", key="camera_attiva")
    st_autorefresh(interval=30000, key="presence_heartbeat")
    if st.button("Log-out"):
        st.session_state.clear()
        st.rerun()

# ================== INGRESSO ==================
if scelta == "➕ Ingresso":
    aggiorna_attivita()
    st.subheader("Registrazione Nuova Vettura")
    
    if st.session_state.camera_attiva and not st.session_state.zona_id:
        foto_z = st.camera_input("Inquadra QR Zona", key="cam_in")
        if foto_z:
            z_id = leggi_qr_zona(foto_z)
            if z_id:
                st.session_state["zona_id"] = z_id
                st.session_state["zona_nome"] = ZONE_INFO[z_id]
                st.success(f"✅ Zona rilevata: {ZONE_INFO[z_id]}")
                time.sleep(0.5)
                st.rerun()
            else: st.error("❌ QR non valido")

    with st.form("f_ingresso"):
        if not st.session_state['zona_id']: st.error("❌ Scansiona prima il QR della zona")
        else: st.info(f"📍 Zona: **{st.session_state['zona_nome']}**")
        
        targa = st.text_input("TARGA").upper().strip()
        marca = st.text_input("Marca").upper().strip()
        modello = st.text_input("Modello").upper().strip()
        colore = st.text_input("Colore").capitalize().strip()
        km = st.number_input("Chilometri", min_value=0, step=100)
        n_chiave = st.number_input("N. Chiave", min_value=0, step=1)
        note = st.text_area("Note")
        submit = st.form_submit_button("REGISTRA LA VETTURA", disabled=not st.session_state['zona_id'])

        if submit:
            if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa): st.error("Targa non valida"); st.stop()
            check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
            if check.data: st.error("Targa già presente"); st.stop()
            
            supabase.table("parco_usato").insert({
                "targa": targa, "marca_modello": f"{marca} {modello}", "colore": colore, "km": int(km),
                "numero_chiave": int(n_chiave), "zona_id": st.session_state["zona_id"], 
                "zona_attuale": st.session_state["zona_nome"], "data_ingresso": datetime.now(timezone.utc).isoformat(),
                "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo
            }).execute()
            registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
            st.session_state["zona_id"] = ""
            st.success("✅ Registrata correttamente")
            time.sleep(1)
            st.rerun()

# ================== RICERCA / SPOSTA ==================
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
            if res.data:
                for v in res.data:
                    with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                        st.write(f"📍 Posizione attuale: **{v['zona_attuale']}**")
                        
                        if not st.session_state.camera_attiva:
                            st.warning("⚠️ Per spostare la vettura, attiva lo **Scanner QR** nella Sidebar e inquadra la zona di destinazione.")
                        
                        if st.session_state.camera_attiva and not st.session_state["zona_id_sposta"]:
                            foto_sp = st.camera_input("📷 Inquadra QR zona di destinazione", key=f"cam_{v['targa']}")
                            if foto_sp:
                                z_id_sp = leggi_qr_zona(foto_sp)
                                if z_id_sp:
                                    st.session_state["zona_id_sposta"] = z_id_sp
                                    st.session_state["zona_nome_sposta"] = ZONE_INFO[z_id_sp]
                                    st.success(f"🎯 Destinazione rilevata: {ZONE_INFO[z_id_sp]}")
                                    time.sleep(0.5); st.rerun()
                                else: st.warning("❌ QR non valido")
                        
                        c1, c2 = st.columns(2)
                        if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not st.session_state['zona_id_sposta'], use_container_width=True):
                            supabase.table("parco_usato").update({"zona_id": st.session_state["zona_id_sposta"], "zona_attuale": st.session_state["zona_nome_sposta"]}).eq("targa", v['targa']).execute()
                            registra_log(v['targa'], "Spostamento", f"In {st.session_state['zona_nome_sposta']}", utente_attivo)
                            st.session_state["zona_id_sposta"] = ""; st.success("✅ Spostata!"); time.sleep(1); st.rerun()
                        
                        with c2:
                            conf = st.checkbox("Confermo CONSEGNA", key=f"conf_{v['targa']}")
                            if st.button("🔴 CONSEGNA", key=f"btn_{v['targa']}", disabled=not conf, use_container_width=True):
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                st.success("✅ CONSEGNATA"); time.sleep(1); st.rerun()

# ================== DASHBOARD GENERALE (KPI & LOGS) ==================
elif scelta == "📊 Dashboard Generale":
    st.subheader("📊 Dashboard Generale")
    c1, c2 = st.columns(2)
    with c1: period = st.selectbox("📅 Periodo", ["Oggi", "Ieri", "Ultimi 7 giorni", "Ultimi 30 giorni"])
    res_ut = supabase.table("utenti").select("nome").eq("attivo", True).order("nome").execute()
    lista_op = ["Tutti"] + [u["nome"] for u in res_ut.data] if res_ut.data else ["Tutti"]
    with c2: op_sel = st.selectbox("👤 Operatore", lista_op)

    now = datetime.now(timezone.utc)
    if period == "Oggi": data_inizio = now.replace(hour=0, minute=0, second=0, microsecond=0); data_fine = None
    elif period == "Ieri": data_fine = now.replace(hour=0, minute=0, second=0, microsecond=0); data_inizio = data_fine - timedelta(days=1)
    elif period == "Ultimi 7 giorni": data_inizio = now - timedelta(days=7); data_fine = None
    elif period == "Ultimi 30 giorni": data_inizio = now - timedelta(days=30); data_fine = None

    q = supabase.table("log_movimenti").select("*").gte("created_at", data_inizio.isoformat())
    if data_fine: q = q.lt("created_at", data_fine.isoformat())
    if op_sel != "Tutti": q = q.eq("utente", op_sel)
    logs = q.order("created_at", desc=True).execute().data or []

    res_p = supabase.table("parco_usato").select("targa").eq("stato", "PRESENTE").execute()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("🚗 In Piazzale", len(res_p.data or []))
    azioni = [r["azione"] for r in logs]
    k2.metric("➕ Ingressi", azioni.count("Ingresso"))
    k3.metric("🔄 Spostamenti", azioni.count("Spostamento"))
    k4.metric("🔴 Consegne", azioni.count("Consegna"))

    st.markdown("### 📍 KPI per Zona")
    kpi_z = []
    for zid, znome in ZONE_INFO.items():
        z_in, z_sp, z_out = 0, 0, 0
        for r in logs:
            if znome in (r.get("dettaglio") or ""):
                if r["azione"] == "Ingresso": z_in += 1
                elif r["azione"] == "Spostamento": z_sp += 1
                elif r["azione"] == "Consegna": z_out += 1
        kpi_z.append({"Zona": f"{zid} - {znome}", "➕ In": z_in, "🔄 Sposta": z_sp, "🔴 Out": z_out})
    st.dataframe(pd.DataFrame(kpi_z), use_container_width=True)

# ================== ALTRE SEZIONI (MODIFICA, LOG, UTENTI ECC.) ==================
elif scelta == "✏️ Modifica":
    st.subheader("✏️ Correzione Dati")
    q_mod = st.text_input("Targa o Chiave").strip().upper()
    if q_mod:
        col = "targa" if not q_mod.isdigit() else "numero_chiave"
        val = q_mod if not q_mod.isdigit() else int(q_mod)
        res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute()
        if res.data:
            v = res.data[0]
            with st.form("f_mod"):
                upd = {
                    "marca_modello": st.text_input("Modello", value=v['marca_modello']).upper(),
                    "colore": st.text_input("Colore", value=v['colore']).capitalize(),
                    "km": st.number_input("KM", value=int(v['km'])),
                    "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])),
                    "note": st.text_area("Note", value=v['note'])
                }
                if st.form_submit_button("SALVA"):
                    supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                    registra_log(v['targa'], "Modifica", "Correzione manuale", utente_attivo)
                    st.success("Aggiornato"); time.sleep(1); st.rerun()

elif scelta == "📜 Log":
    st.subheader("📜 Registro Movimenti")
    per = st.selectbox("Filtro Periodo", ["Oggi", "Settimana", "Tutto"])
    now = datetime.now(timezone.utc)
    data_log = now.replace(hour=0, minute=0, second=0) if per == "Oggi" else now - timedelta(days=7) if per == "Settimana" else None
    query = supabase.table("log_movimenti").select("*")
    if data_log: query = query.gte("created_at", data_log.isoformat())
    res = query.order("created_at", desc=True).limit(500).execute()
    if res.data:
        df = pd.DataFrame(res.data)
        df["Ora"] = pd.to_datetime(df["created_at"]).dt.tz_convert("Europe/Rome").dt.strftime("%d/%m %H:%M")
        st.dataframe(df[["Ora", "targa", "azione", "utente", "dettaglio"]], use_container_width=True)

elif scelta == "👥 Gestione Utenti":
    st.subheader("👥 Gestione Utenti (Admin)")
    res_all = supabase.table("utenti").select("*").order("nome").execute()
    st.dataframe(pd.DataFrame(res_all.data)[["nome", "ruolo", "attivo"]], use_container_width=True)
    with st.form("add"):
        st.write("➕ Aggiungi Utente")
        n = st.text_input("Nome")
        p = st.text_input("PIN", type="password")
        r = st.selectbox("Ruolo", ["operatore", "admin"])
        if st.form_submit_button("CREA"):
            supabase.table("utenti").insert({"nome": n, "pin": p, "ruolo": r, "attivo": True}).execute()
            st.success("Creato"); time.sleep(1); st.rerun()

elif scelta == "🖨️ Stampa QR":
    st.subheader("🖨️ Generatore QR Zone")
    z_qr = st.selectbox("Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
    qr_obj = qrcode.make(f"ZONA|{z_qr}")
    buf = BytesIO(); qr_obj.save(buf, format="PNG")
    st.image(buf.getvalue(), width=250)
    st.download_button("DOWNLOAD QR", buf.getvalue(), f"QR_{z_qr}.png")

elif scelta == "♻️ Ripristina":
    t_rip = st.text_input("Targa da ripristinare").upper().strip()
    if t_rip and st.button("RIPRISTINA"):
        supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", t_rip).execute()
        registra_log(t_rip, "Ripristino", "Riportata in piazzale", utente_attivo)
        st.success("Ripristinata!"); time.sleep(1); st.rerun()

elif scelta == "📋 Verifica Zone":
    zv = st.selectbox("Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
    res = supabase.table("parco_usato").select("*").eq("zona_id", zv).eq("stato", "PRESENTE").execute()
    if res.data: st.dataframe(pd.DataFrame(res.data)[["targa", "marca_modello", "colore"]], use_container_width=True)
    else: st.warning("Zona vuota")

elif scelta == "📊 Dashboard Zone":
    zs = st.selectbox("Filtra Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
    logs_z = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[zs]}%").limit(100).execute()
    if logs_z.data: st.dataframe(pd.DataFrame(logs_z.data)[["targa", "azione", "utente"]], use_container_width=True)

elif scelta == "📊 Export":
    res_e = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
    if res_e.data:
        df_e = pd.DataFrame(res_e.data)
        out = BytesIO()
        with pd.ExcelWriter(out, engine="xlsxwriter") as wr: df_e.to_excel(wr, index=False)
        st.download_button("SCARICA EXCEL COMPLETO", out.getvalue(), "Piazzale.xlsx")
