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
    "Z09": "Commercianti con telo", "Z10": "Lavorazioni esterni", "Z11": "Verso altre sedi",
    "Z12": "Deposito N.10", "Z13": "Deposito N.8","Z14": "Esterno (Con o Senza telo Motorsclub)" 
}

TIMEOUT_MINUTI = 20

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1 Master", layout="wide")

# --- 3. GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'ruolo' not in st.session_state:
    st.session_state['ruolo'] = None
if 'can_consegna' not in st.session_state:
    st.session_state['can_consegna'] = False
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

# --- GESTIONE RESET FORM E PERSISTENZA RICERCA ---
if "form_ingresso_ver" not in st.session_state:
    st.session_state["form_ingresso_ver"] = 0
if "form_ricerca_ver" not in st.session_state:
    st.session_state["form_ricerca_ver"] = 0
if "ricerca_attiva" not in st.session_state:
    st.session_state["ricerca_attiva"] = False
if "ricerca_query" not in st.session_state:
    st.session_state["ricerca_query"] = None
if "ricerca_tipo" not in st.session_state:
    st.session_state["ricerca_tipo"] = None
if "ricerca_feedback_ok" not in st.session_state:
    st.session_state["ricerca_feedback_ok"] = False

def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now(timezone.utc)

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now(timezone.utc) - st.session_state['last_action']
        if trascorso > timedelta(minutes=TIMEOUT_MINUTI):
            st.session_state['user_autenticato'] = None
            st.session_state['ruolo'] = None
            st.session_state['can_consegna'] = False
            st.rerun()

# --- 4. FUNZIONI LOGIN & DATABASE ---
def login_db(nome, pin):
    try:
        res = supabase.table("utenti").select("nome, ruolo, can_consegna").eq("nome", nome).eq("pin", pin).eq("attivo", True).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Errore login: {e}")
        return None

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
    st.title("🔐 Accesso Autoclub Center Usato 1.1 Master")
    lista_u = get_lista_utenti_login()
    u = st.selectbox("Operatore", ["- Seleziona -"] + lista_u)
    p = st.text_input("PIN", type="password")
    if st.button("ACCEDI", use_container_width=True):
        user = login_db(u, p)
        if user:
            st.session_state['user_autenticato'] = user["nome"]
            st.session_state['ruolo'] = user["ruolo"]
            st.session_state['can_consegna'] = user.get("can_consegna", False)
            aggiorna_attivita()
            st.rerun()
        else: st.error("Accesso negato: PIN errato o utente non attivo")
else:
    utente_attivo = st.session_state['user_autenticato']
    menu = ["➕ Ingresso", "🔍 Ricerca", 
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
        if st.session_state.camera_attiva:
            foto_z = st.camera_input("Scansiona QR della Zona", key="cam_in")
            if foto_z:
                z_id = leggi_qr_zona(foto_z)
                if z_id:
                    st.session_state["zona_id"] = z_id
                    st.session_state["zona_nome"] = ZONE_INFO[z_id]
                    st.success(f"✅ Zona rilevata: {st.session_state['zona_nome']}")
                else: st.error("❌ QR non valido")

        with st.form(key=f"f_ingresso_{st.session_state['form_ingresso_ver']}"):
            if not st.session_state['zona_id']: st.error("❌ Scansione QR Obbligatoria per abilitare i campi")
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
                
                payload = {
                    "targa": targa, "marca_modello": f"{marca} {modello}", "colore": colore, "km": int(km),
                    "numero_chiave": int(n_chiave), "zona_id": st.session_state["zona_id"], 
                    "zona_attuale": st.session_state["zona_nome"], "data_ingresso": datetime.now(timezone.utc).isoformat(),
                    "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo
                }
                supabase.table("parco_usato").insert(payload).execute()
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
                
                st.session_state["ingresso_salvato"] = {
                    "targa": targa, "modello": f"{marca} {modello}", "colore": colore, 
                    "km": int(km), "chiave": int(n_chiave), "zona": st.session_state["zona_nome"]
                }
                st.rerun()

        if st.session_state.get("ingresso_salvato"):
            info = st.session_state["ingresso_salvato"]
            st.markdown(f"""
                <div style="background-color:#d4edda; border:1px solid #28a745; padding:16px; border-radius:10px; color:#155724;">
                    <h4>✅ Vettura registrata correttamente</h4>
                    <b>🚗 Targa:</b> {info['targa']}<br>
                    <b>📦 Modello:</b> {info['modello']}<br>
                    <b>🎨 Colore:</b> {info['colore']}<br>
                    <b>📏 Chilometri:</b> {info['km']}<br>
                    <b>🔑 Numero chiave:</b> {info['chiave']}<br>
                    <b>📍 Zona:</b> {info['zona']}
                </div>
                """, unsafe_allow_html=True)
            
            if st.button("🆕 NUOVA REGISTRAZIONE", use_container_width=True):
                st.session_state["ingresso_salvato"] = False
                st.session_state["zona_id"] = ""
                st.session_state["zona_nome"] = ""
                st.session_state["form_ingresso_ver"] += 1
                st.rerun()

    # --- 9. SEZIONE RICERCA (UNIFICATA) ---
    elif scelta == "🔍 Ricerca":
        aggiorna_attivita()
        st.subheader("🔍 Ricerca Vettura")

        with st.form("f_ricerca_unica"):
            tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
            q = st.text_input("Valore da cercare").strip().upper()
            cerca = st.form_submit_button("🔍 CERCA")

        if cerca and q:
            col = "targa" if tipo == "Targa" else "numero_chiave"
            val = q if tipo == "Targa" else int(q) if q.isdigit() else None
            
            if val is None:
                st.error("Valore non valido")
            else:
                res = supabase.table("parco_usato") \
                    .select("*") \
                    .eq(col, val) \
                    .eq("stato", "PRESENTE") \
                    .execute()

                if feedback_ricerca(tipo, q, res.data):
                    # 🔽 MULTI RISULTATO SU CHIAVE
                    if len(res.data) > 1:
                        v = st.selectbox(
                            "Seleziona vettura",
                            res.data,
                            format_func=lambda x: f"{x['targa']} | {x['marca_modello']} | Chiave {x['numero_chiave']}"
                        )
                    else:
                        v = res.data[0]

                    # --- DATI VETTURA ---
                    st.markdown("## 🚗 Dati Vettura")
                    c_info1, c_info2 = st.columns(2)
                    with c_info1:
                        st.write(f"**Targa:** {v['targa']}")
                        st.write(f"**Marca / Modello:** {v['marca_modello']}")
                        st.write(f"**Colore:** {v['colore']}")
                    with c_info2:
                        st.write(f"**Chilometri:** {v['km']}")
                        st.write(f"**Numero Chiave:** {v['numero_chiave']}")
                        st.info(f"📍 **Zona Attuale:** {v['zona_attuale']}")
                    
                    if v["note"]:
                        st.warning(f"📝 **Note:** {v['note']}")

                    # --- STORICO ---
                    st.markdown("### 📜 Storico Movimenti")
                    log = supabase.table("log_movimenti") \
                        .select("*") \
                        .eq("targa", v["targa"]) \
                        .order("created_at", desc=True) \
                        .execute()

                    if log.data:
                        df_log = pd.DataFrame(log.data)
                        df_log["Ora"] = pd.to_datetime(df_log["created_at"]) \
                            .dt.tz_convert("Europe/Rome") \
                            .dt.strftime("%d/%m/%Y %H:%M")
                        st.dataframe(df_log[["Ora", "azione", "utente", "dettaglio"]], use_container_width=True)
                    else:
                        st.info("Nessuno storico disponibile")

                    st.markdown("---")

                    abilita_spost = st.checkbox("🔄 Abilita Spostamento")
                    abilita_mod = st.checkbox("✏️ Abilita Modifica")
                    abilita_consegna = st.checkbox("🔴 Abilita Consegna")

                    # --- SPOSTAMENTO ---
                    if abilita_spost:
                        if not st.session_state.camera_attiva:
                            st.warning("📷 Per spostare la vettura devi **attivare lo Scanner QR** dalla sidebar")
                        else:
                            foto = st.camera_input("QR Zona Destinazione", key=f"qr_{v['targa']}")
                            if foto:
                                z_id = leggi_qr_zona(foto)
                                if z_id:
                                    z_nome = ZONE_INFO[z_id]
                                    if st.button(f"SPOSTA IN {z_nome}", use_container_width=True):
                                        supabase.table("parco_usato").update({
                                            "zona_id": z_id,
                                            "zona_attuale": z_nome
                                        }).eq("targa", v["targa"]).execute()
                                        registra_log(v["targa"], "Spostamento", f"In {z_nome}", utente_attivo)
                                        st.success("✅ Spostamento effettuato")
                                        time.sleep(0.5)
                                        st.rerun()

                    # --- MODIFICA ---
                    if abilita_mod:
                        with st.form("f_modifica_unica"):
                            upd = {
                                "marca_modello": st.text_input("Marca / Modello", v["marca_modello"]).upper(),
                                "colore": st.text_input("Colore", v["colore"]).capitalize(),
                                "km": st.number_input("KM", value=int(v["km"])),
                                "numero_chiave": st.number_input("Numero Chiave", value=int(v["numero_chiave"])),
                                "note": st.text_area("Note", v["note"])
                            }
                            if st.form_submit_button("💾 SALVA MODIFICHE"):
                                supabase.table("parco_usato").update(upd).eq("targa", v["targa"]).execute()
                                registra_log(v["targa"], "Modifica", "Correzione dati", utente_attivo)
                                st.success("✅ Dati aggiornati")
                                time.sleep(0.5)
                                st.rerun()

                    # --- CONSEGNA ---
                    if abilita_consegna:
                        if not st.session_state.get("can_consegna", False):
                            st.info("🔒 Non sei autorizzato alla CONSEGNA di vetture")
                        else:
                            conferma = st.checkbox(
                                f"Confermo la CONSEGNA della vettura {v['targa']}",
                                key=f"conf_consegna_{v['targa']}"
                            )
                            if st.button(
                                "🔴 CONSEGNA DEFINITIVA",
                                disabled=not conferma,
                                use_container_width=True
                            ):
                                supabase.table("parco_usato") \
                                    .update({"stato": "CONSEGNATO"}) \
                                    .eq("targa", v["targa"]) \
                                    .execute()
                                registra_log(v["targa"], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                st.success("✅ Vettura CONSEGNATA")
                                time.sleep(0.5)
                                st.rerun()

    # --- 11. DASHBOARD GENERALE ---
    elif scelta == "📊 Dashboard Generale":
        st.subheader("📊 Dashboard Generale")
        c1, c2 = st.columns(2)
        with c1:
            periodo_dash = st.selectbox("📅 Periodo", ["Oggi", "Ieri", "Ultimi 7 giorni", "Ultimi 30 giorni"], key="dash_period")
        res_ut = supabase.table("utenti").select("nome").eq("attivo", True).order("nome").execute()
        lista_operatori = ["Tutti"] + [u["nome"] for u in res_ut.data] if res_ut.data else ["Tutti"]
        with c2:
            operatore_sel = st.selectbox("👤 Operatore", lista_operatori, key="dash_op")

        now = datetime.now(timezone.utc)
        if periodo_dash == "Oggi":
            data_inizio = now.replace(hour=0, minute=0, second=0, microsecond=0)
            data_fine = None
        elif periodo_dash == "Ieri":
            data_fine = now.replace(hour=0, minute=0, second=0, microsecond=0)
            data_inizio = data_fine - timedelta(days=1)
        elif periodo_dash == "Ultimi 7 giorni":
            data_inizio = now - timedelta(days=7)
            data_fine = None
        elif periodo_dash == "Ultimi 30 giorni":
            data_inizio = now - timedelta(days=30)
            data_fine = None

        query = supabase.table("log_movimenti").select("*").gte("created_at", data_inizio.isoformat())
        if data_fine: query = query.lt("created_at", data_fine.isoformat())
        if operatore_sel != "Tutti": query = query.eq("utente", operatore_sel)
        res_log = query.order("created_at", desc=True).execute()
        log_data = res_log.data or []

        azioni = [r["azione"] for r in log_data]
        res_p = supabase.table("parco_usato").select("targa").eq("stato", "PRESENTE").execute()
        tot_piazzale = len(res_p.data or [])

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🚗 In Piazzale", tot_piazzale)
        k2.metric("➕ Ingressi", azioni.count("Ingresso"))
        k3.metric("🔄 Spostamenti", azioni.count("Spostamento"))
        k4.metric("🔴 Consegne", azioni.count("Consegna"))

        if operatore_sel != "Tutti":
            st.markdown("### 👤 Attività Operatore")
            azioni_op = [r["azione"] for r in log_data if r["utente"] == operatore_sel]
            o1, o2, o3 = st.columns(3)
            o1.metric("➕ Ingressi", azioni_op.count("Ingresso"))
            o2.metric("🔄 Spostamenti", azioni_op.count("Spostamento"))
            o3.metric("🔴 Consegne", azioni_op.count("Consegna"))

        st.markdown("---")
        st.markdown("### 📍 KPI per Zona")
        kpi_zona = []
        for z_id, z_nome in ZONE_INFO.items():
            z_in, z_sp, z_out = 0, 0, 0
            for r in log_data:
                if z_nome in (r.get("dettaglio") or ""):
                    if r["azione"] == "Ingresso": z_in += 1
                    elif r["azione"] == "Spostamento": z_sp += 1
                    elif r["azione"] == "Consegna": z_out += 1
            kpi_zona.append({"Zona": f"{z_id} - {z_nome}", "➕ Ingressi": z_in, "🔄 Spostamenti": z_sp, "🔴 Consegne": z_out})
        st.dataframe(pd.DataFrame(kpi_zona), use_container_width=True)

    # --- 12. EXPORT ---
    elif scelta == "📊 Export":
        st.subheader("📊 Export Piazzale")
        zone_export = ["Tutte le zone"] + list(ZONE_INFO.keys())
        zona_sel = st.selectbox("📍 Zona", zone_export, format_func=lambda x: x if x == "Tutte le zone" else f"{x} - {ZONE_INFO[x]}")
        query = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE")
        if zona_sel != "Tutte le zone": query = query.eq("zona_id", zona_sel)
        res = query.execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.dataframe(df[["targa", "marca_modello", "colore", "zona_attuale", "numero_chiave"]], use_container_width=True)
            out = BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Piazzale")
            st.download_button("📥 SCARICA EXCEL", out.getvalue(), "Piazzale.xlsx", use_container_width=True)

    # --- 13. VERIFICA ZONE ---
    elif scelta == "📋 Verifica Zone":
        st.subheader("📋 Analisi per Zona")
        z_v = st.selectbox("Scegli Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("parco_usato").select("targa, marca_modello, colore").eq("zona_id", z_v).eq("stato", "PRESENTE").execute()
        totale_zona = len(res.data) if res.data else 0
        st.metric(label=f"🚗 Totale vetture in {ZONE_INFO[z_v]}", value=totale_zona)
        st.markdown("---")
        if res.data: st.dataframe(pd.DataFrame(res.data), use_container_width=True)
        else: st.warning("Zona vuota")

    # --- 14. SEZIONE LOG ---
    elif scelta == "📜 Log":
        st.subheader("📜 Registro Movimenti")
        periodo = st.selectbox("📅 Periodo", ["Oggi", "Ieri", "Settimana", "Mese", "Anno", "Tutto"], index=0)
        now = datetime.now(timezone.utc)
        if periodo == "Oggi":
            data_inizio = now.replace(hour=0, minute=0, second=0, microsecond=0)
            data_fine = None
        elif periodo == "Ieri":
            data_fine = now.replace(hour=0, minute=0, second=0, microsecond=0)
            data_inizio = data_fine - timedelta(days=1)
        elif periodo == "Settimana":
            data_inizio = now - timedelta(days=7)
            data_fine = None
        elif periodo == "Mese":
            data_inizio = now - timedelta(days=30)
            data_fine = None
        elif periodo == "Anno":
            data_inizio = now - timedelta(days=365)
            data_fine = None
        else:
            data_inizio = None
            data_fine = None

        res_ut = supabase.table("utenti").select("nome").execute()
        utenti_attuali = {u["nome"] for u in res_ut.data} if res_ut.data else set()
        query = supabase.table("log_movimenti").select("*")
        if data_inizio: query = query.gte("created_at", data_inizio.isoformat())
        if data_fine: query = query.lt("created_at", data_fine.isoformat())
        res = query.order("created_at", desc=True).limit(2000).execute()

        if res.data:
            df = pd.DataFrame(res.data)
            df["Ora"] = pd.to_datetime(df["created_at"]).dt.tz_convert("Europe/Rome").dt.strftime("%d/%m/%Y %H:%M:%S")
            df["Utente"] = df["utente"].apply(lambda u: u if u in utenti_attuali else f"{u} ⚠️")
            df_view = df[["Ora", "targa", "azione", "Utente", "dettaglio"]]
            st.caption(f"📌 Periodo selezionato: **{periodo}** — ⚠️ utenti rinominati o non più attivi")
            st.dataframe(df_view, use_container_width=True)
            out = BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
                df_view.to_excel(writer, index=False, sheet_name="Log Movimenti")
            st.download_button("📥 SCARICA LOG IN EXCEL", out.getvalue(), f"Log_Movimenti_{periodo}.xlsx", use_container_width=True)
        else: st.info("Nessun movimento registrato.")

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
        if st.session_state["ruolo"] != "admin": st.error("Accesso non autorizzato"); st.stop()
        res_all = supabase.table("utenti").select("*").order("nome").execute()
        if res_all.data:
            df_ut = pd.DataFrame(res_all.data)
            st.dataframe(df_ut[["nome", "ruolo", "attivo", "can_consegna"]], use_container_width=True)
        with st.form("add_user"):
            st.markdown("### ➕ Aggiungi Utente")
            n = st.text_input("Nome e Cognome"); p = st.text_input("PIN", type="password"); r = st.selectbox("Ruolo", ["operatore", "admin"])
            c_cons = st.checkbox("Autorizzato alla CONSEGNA")
            if st.form_submit_button("CREA"):
                supabase.table("utenti").insert({"nome": n, "pin": p, "ruolo": r, "attivo": True, "can_consegna": c_cons}).execute()
                st.success("Creato"); time.sleep(1); st.rerun()
        st.markdown("---")
        st.markdown("### ✏️ Modifica / Disattiva Utente")
        nomi_utenti = [u["nome"] for u in res_all.data]
        u_sel = st.selectbox("Seleziona utente", nomi_utenti)
        ut = next(u for u in res_all.data if u["nome"] == u_sel)
        with st.form("edit_user"):
            new_pin = st.text_input("Nuovo PIN (lascia vuoto per non cambiare)", type="password")
            new_ruolo = st.selectbox("Ruolo", ["operatore", "admin"], index=0 if ut["ruolo"] == "operatore" else 1)
            can_consegna = st.checkbox("🔴 Autorizzato alla CONSEGNA", value=ut.get("can_consegna", False))
            attivo = st.checkbox("Utente attivo", value=ut["attivo"])
            if st.form_submit_button("SALVA MODIFICHE"):
                upd = {"ruolo": new_ruolo, "attivo": attivo, "can_consegna": can_consegna}
                if new_pin:
                    upd["pin"] = new_pin
                supabase.table("utenti").update(upd).eq("nome", u_sel).execute()
                if u_sel == st.session_state.get("user_autenticato"):
                    st.session_state["can_consegna"] = can_consegna
                st.success("✅ Utente aggiornato"); time.sleep(1); st.rerun()
