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
from qrcode import make as make_qr
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

# --- 2. CREDENZIALI ---
CREDENZIALI = {
    "Luca Simonini": "2026", 
    "Ivan Pohorilyak": "1234", 
    "Abdul": "0000", 
    "Tommaso Zani": "1111", 
    "Andrea Sachetti": "2345", 
    "Roberto Gozzi": "3412" 
}

# --- 3. CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Z01": "Deposito N.9", "Z02": "Deposito N.7", "Z03": "Deposito N.6 (Lavaggisti)",
    "Z04": "Deposito unificato 1 e 2", "Z05": "Showroom", "Z06": "Vetture vendute",
    "Z07": "Piazzale Lavaggio", "Z08": "Commercianti senza telo",
    "Z09": "Commercianti con telo", "Z10": "Lavorazioni esterni", "Z11": "Verso altre sedi"
}

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1 Master", layout="wide")

# --- 4. GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
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
            st.rerun()

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
    u = st.selectbox("Operatore", ["- Seleziona -"] + list(CREDENZIALI.keys()))
    p = st.text_input("PIN", type="password")
    if st.button("ACCEDI", use_container_width=True):
        if u != "- Seleziona -" and p == CREDENZIALI.get(u):
            st.session_state['user_autenticato'] = u
            aggiorna_attivita()
            st.rerun()
        else: st.error("Accesso negato")
else:
    utente_attivo = st.session_state['user_autenticato']
    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", 
            "📋 Verifica Zone", "📊 Dashboard Zone", "📊 Dashboard Generale", 
            "📊 Export", "📜 Log", "🖨️ Stampa QR", "♻️ Ripristina"]
    
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.session_state["pagina_attuale"] = scelta
    st.markdown("---")

    # --- 7. SIDEBAR ---
    with st.sidebar:
        st.info(f"👤 {utente_attivo}")
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

        # --- 8. SEZIONE INGRESSO (Aggiornata 1.1 Master) ---
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        st.subheader("Registrazione Nuova Vettura")
        
        # Logica Scanner QR
        if st.session_state.camera_attiva:
            foto_z = st.camera_input("Scansiona QR della Zona", key="cam_in")
            if foto_z:
                z_id = leggi_qr_zona(foto_z)
                if z_id:
                    st.session_state["zona_id"] = z_id
                    st.session_state["zona_nome"] = ZONE_INFO[z_id]
                    st.success(f"✅ Zona rilevata: {st.session_state['zona_nome']}")
                else: st.error("❌ QR non valido")
        else: st.warning("⚠️ Scanner disattivato dalla Sidebar.")

        # Form di inserimento
        with st.form("f_ingresso"):
            if not st.session_state['zona_id']: 
                st.error("❌ Scansione QR Obbligatoria per abilitare la registrazione")
            else: 
                st.info(f"📍 Zona selezionata: **{st.session_state['zona_nome']}**")
           
            targa = st.text_input("TARGA", key="ing_targa").upper().strip()
            marca = st.text_input("Marca", key="marca_input").upper().strip()
            modello = st.text_input("Modello", key="modello_input").upper().strip()
            
            c_sug = suggerisci_colore(targa) if targa else None
            if c_sug: st.info(f"🎨 Colore suggerito: **{c_sug}**")
            colore = st.text_input("Colore", key="colore_input").capitalize().strip()

            km = st.number_input("Chilometri", min_value=0, step=100, key="ing_km")
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1, key="ing_chiave")
            st.caption("ℹ️ Chiave = 0 → vettura destinata ai commercianti")
            note = st.text_area("Note", key="ing_note")

            submit = st.form_submit_button("REGISTRA LA VETTURA", disabled=not st.session_state['zona_id'])

            if submit:
                # Validazioni
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("❌ Targa non valida (formato AA123BB richiesto)"); st.stop()
                if not marca or not modello or not colore:
                    st.error("❌ Marca, Modello e Colore sono obbligatori"); st.stop()
                
                # Controllo Duplicati
                check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                if check.data: 
                    st.error(f"❌ La targa {targa} è già presente in piazzale!"); st.stop()
                
                # Salvataggio
                data_ora_attuale = datetime.now(timezone.utc)
                data_payload = {
                    "targa": targa, "marca_modello": f"{marca} {modello}",
                    "colore": colore, "km": int(km), "numero_chiave": int(n_chiave),
                    "zona_id": st.session_state["zona_id"], "zona_attuale": st.session_state["zona_nome"],
                    "data_ingresso": data_ora_attuale.isoformat(), "note": note, 
                    "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo
                }
                
                supabase.table("parco_usato").insert(data_payload).execute()
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
                
                # SALVATAGGIO INFORMAZIONI NELLO STATE PER IL FUMETTO
                st.session_state["ingresso_salvato"] = {
                    "targa": targa,
                    "zona": st.session_state["zona_nome"],
                    "chiave": n_chiave,
                    "colore": colore,
                    "utente": utente_attivo,
                    "ora": data_ora_attuale
                }
                st.rerun()

        # Visualizzazione Fumetto Riepilogativo
        info = st.session_state.get("ingresso_salvato")
        if isinstance(info, dict):
            # Conversione ora locale per il display
            ora_loc = info["ora"].astimezone().strftime("%H:%M:%S")
            
            st.success(
                f"### 🚗 Vettura registrata correttamente\n"
                f"--- \n"
                f"**Targa:** `{info['targa']}`  \n"
                f"**Posizione:** {info['zona']}  \n"
                f"**Chiave:** {info['chiave']}  \n"
                f"**Colore:** {info['colore']}  \n"
                f"**Operatore:** {info['utente']}  \n"
                f"**Ora:** {ora_loc}"
            )
            
            if st.button("➕ REGISTRA UN'ALTRA VETTURA", use_container_width=True):
                # Reset campi e stato
                campi_da_resettare = [
                    "ing_targa", "ing_km", "ing_chiave", "ing_note", 
                    "marca_input", "modello_input", "colore_input"
                ]
                for k in campi_da_resettare:
                    st.session_state.pop(k, None)
                
                st.session_state["zona_id"] = ""
                st.session_state["zona_nome"] = ""
                st.session_state["ingresso_salvato"] = False
                st.rerun()


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
                if not feedback_ricerca(tipo, q, res.data): st.stop()
                for v in res.data:
                    with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                        st.write(f"📍 Posizione attuale: **{v['zona_attuale']}**")
                        if st.session_state.camera_attiva:
                            foto_sp = st.camera_input(f"Scanner QR Destinazione", key=f"cam_{v['targa']}")
                            if foto_sp:
                                z_id_sp = leggi_qr_zona(foto_sp)
                                if z_id_sp:
                                    st.session_state["zona_id_sposta"] = z_id_sp
                                    st.session_state["zona_nome_sposta"] = ZONE_INFO[z_id_sp]
                                    st.success(f"📍 Destinazione: **{st.session_state['zona_nome_sposta']}**")
                        
                        c1, c2 = st.columns(2)
                        if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not st.session_state['zona_id_sposta'], use_container_width=True):
                            supabase.table("parco_usato").update({"zona_id": st.session_state["zona_id_sposta"], "zona_attuale": st.session_state["zona_nome_sposta"]}).eq("targa", v['targa']).execute()
                            registra_log(v['targa'], "Spostamento", f"In {st.session_state['zona_nome_sposta']}", utente_attivo)
                            st.session_state["zona_id_sposta"] = ""; st.session_state["zona_nome_sposta"] = ""
                            st.success("✅ Spostata!"); time.sleep(1); st.rerun()
                        
                        with c2:
                            st.checkbox("⚠️ Confermo CONSEGNA", key=f"conf_{v['targa']}")
                            if st.button("🔴 CONSEGNA", key=f"btn_{v['targa']}", disabled=not st.session_state[f"conf_{v['targa']}"], use_container_width=True):
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                st.success("✅ CONSEGNATA"); time.sleep(1); st.rerun()

    # --- 10. SEZIONE MODIFICA ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("Correzione Dati")
        q_mod = st.text_input("Targa o Chiave da modificare").strip().upper()
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
                        st.success("✅ Dati aggiornati"); time.sleep(1); st.rerun()

    # --- 11. DASHBOARD GENERALE ---
    elif scelta == "📊 Dashboard Generale":
        st.subheader("📊 Dashboard Generale Piazzale")
        res_p = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        presenti = res_p.data or []
        
        giorni = []
        for v in presenti:
            if v.get("data_ingresso"):
                d_ing = pd.to_datetime(v["data_ingresso"], utc=True)
                giorni.append((datetime.now(timezone.utc) - d_ing).days)
        
        media = round(sum(giorni)/len(giorni), 1) if giorni else 0
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🚗 In Piazzale", len(presenti))
        c2.metric("⏱️ Media Giorni", media)
        c3.metric("⚠️ Critiche (+30gg)", len([g for g in giorni if g >= 30]))
        c4.metric("📍 Zone Occupate", len({v["zona_id"] for v in presenti}))

        # --- KPI OPERATORE (OGGI) ---
        st.markdown("---")
        st.markdown("### 👤 KPI Operatore (Oggi)")
        inizio_oggi = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)

        res_user = supabase.table("log_movimenti") \
            .select("azione") \
            .eq("utente", utente_attivo) \
            .gte("created_at", inizio_oggi.isoformat()) \
            .execute()

        azioni = [r["azione"] for r in res_user.data] if res_user.data else []

        k1, k2, k3 = st.columns(3)
        k1.metric("➕ Ingressi", azioni.count("Ingresso"))
        k2.metric("🔄 Spostamenti", azioni.count("Spostamento"))
        k3.metric("🔴 Consegne", azioni.count("Consegna"))

        # --- ATTIVITÀ DI OGGI (PER UTENTE) ---
        st.markdown("### 🕒 Le tue attività di oggi")
        res_log_user = supabase.table("log_movimenti") \
            .select("*") \
            .eq("utente", utente_attivo) \
            .gte("created_at", inizio_oggi.isoformat()) \
            .order("created_at", desc=True) \
            .execute()

        if res_log_user.data:
            df_u = pd.DataFrame(res_log_user.data)
            df_u["Ora"] = pd.to_datetime(df_u["created_at"], utc=True) \
                            .dt.tz_convert("Europe/Rome") \
                            .dt.strftime("%H:%M")
            st.dataframe(df_u[["Ora", "targa", "azione", "dettaglio"]], use_container_width=True)
        else:
            st.info("Nessuna attività registrata oggi")

        # --- KPI GLOBALI OGGI ---
        st.markdown("### 🏭 KPI Piazzale (Oggi)")
        res_all = supabase.table("log_movimenti") \
            .select("azione") \
            .gte("created_at", inizio_oggi.isoformat()) \
            .execute()

        azioni_all = [r["azione"] for r in res_all.data] if res_all.data else []

        g1, g2, g3 = st.columns(3)
        g1.metric("➕ Ingressi Totali", azioni_all.count("Ingresso"))
        g2.metric("🔄 Spostamenti Totali", azioni_all.count("Spostamento"))
        g3.metric("🔴 Consegne Totali", azioni_all.count("Consegna"))

    # --- 12. SEZIONE EXPORT AGGIORNATA ---
    elif scelta == "📊 Export":
        st.subheader("📊 Export Piazzale")
        z_exp = st.selectbox("Seleziona Zona", ["TUTTE"] + list(ZONE_INFO.keys()), 
                             format_func=lambda z: "TUTTE le zone" if z == "TUTTE" else f"{z} - {ZONE_INFO[z]}")
        
        q = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE")
        if z_exp != "TUTTE": q = q.eq("zona_id", z_exp)
        res = q.execute()
        
        if res.data:
            df = pd.DataFrame(res.data)
            df["Zona"] = df.apply(lambda x: f"{x.get('zona_id','')} - {x.get('zona_attuale','')}", axis=1)
            
            # Fix conversione date con gestione errori e pulizia NaT
            df["Data Inserimento"] = (
                pd.to_datetime(df["data_ingresso"], errors="coerce", utc=True)
                  .dt.tz_convert("Europe/Rome")
                  .dt.strftime("%d/%m/%Y %H:%M")
            ).fillna("—")
            
            cols = ["targa", "marca_modello", "colore", "km", "numero_chiave", "Zona", "Data Inserimento", "note"]
            st.dataframe(df[cols], use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as w: df[cols].to_excel(w, index=False)
            st.download_button("📥 SCARICA EXCEL", out.getvalue(), f"Piazzale_{z_exp}.xlsx", use_container_width=True)

    # --- 13. VERIFICA ZONE ---
    elif scelta == "📋 Verifica Zone":
        st.subheader("📋 Analisi per Zona")
        z_v = st.selectbox("Scegli Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("parco_usato").select("*").eq("zona_id", z_v).eq("stato", "PRESENTE").execute()
        if res.data:
            st.metric("Vetture presenti", len(res.data))
            st.dataframe(pd.DataFrame(res.data)[["targa", "marca_modello", "colore", "numero_chiave", "note"]], use_container_width=True)
        else: st.warning("Zona vuota")

    # --- 14. LOG ---
    elif scelta == "📜 Log":
        st_autorefresh(interval=30000, key="log_auto")
        st.subheader("📜 Registro Movimenti")
        res = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(100).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df["Data/Ora"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert("Europe/Rome").dt.strftime("%d/%m/%Y %H:%M:%S")
            st.dataframe(df[["Data/Ora", "targa", "azione", "utente", "numero_chiave", "dettaglio"]], use_container_width=True)

    # --- 15. STAMPA QR ---
    elif scelta == "🖨️ Stampa QR":
        st.subheader("🖨️ Generatore QR Zone")
        z_qr = st.selectbox("Zona da stampare", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        qr_obj = qrcode.make(f"ZONA|{z_qr}")
        buf = BytesIO()
        qr_obj.save(buf, format="PNG")
        st.image(buf.getvalue(), width=250)
        st.download_button("DOWNLOAD QR", buf.getvalue(), f"QR_{z_qr}.png")

    # --- 16. RIPRISTINA ---
    elif scelta == "♻️ Ripristina":
        st.subheader("♻️ Ripristino Vetture Consegnate")
        t_r = st.text_input("Targa da riportare in presente").upper().strip()
        if t_r:
            res = supabase.table("parco_usato").select("*").eq("targa", t_r).eq("stato", "CONSEGNATO").execute()
            if feedback_ricerca("Targa", t_r, res.data):
                if st.button(f"RIPRISTINA {t_r}", use_container_width=True):
                    supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", t_r).execute()
                    registra_log(t_r, "Ripristino", "Riportata in stock", utente_attivo)
                    st.success("✅ Vettura ripristinata"); time.sleep(1); st.rerun()

    # --- 17. DASHBOARD ZONE ---
    elif scelta == "📊 Dashboard Zone":
        st.subheader("📍 Storico Movimenti Zona")
        z_sel = st.selectbox("Filtra per Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[z_sel]}%").order("created_at", desc=True).limit(50).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df["Data/Ora"] = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert("Europe/Rome").dt.strftime("%d/%m/%Y %H:%M:%S")
            st.dataframe(df[["Data/Ora", "targa", "azione", "utente", "numero_chiave"]], use_container_width=True)
