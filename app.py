import streamlit as st
import os
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

st.cache_data.clear()
st.cache_resource.clear()

# --- 1. CONFIGURAZIONE DATABASE ---
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

# --- 2. CREDENZIALI & TIMEOUT ---
CREDENZIALI = {"Luca Simonini": "2026", "Ivan Pohorilyak": "1234", "Abdul": "0000", "Tommaso Zani": "1111", "Andrea Sachetti": "2345", "Roberto Gozzi": "3412" }
TIMEOUT_MINUTI = 15

# --- 3. CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Z01": "Deposito N.9", "Z02": "Deposito N.7", "Z03": "Deposito N.6 (Lavaggisti)",
    "Z04": "Deposito unificato 1 e 2", "Z05": "Showroom", "Z06": "Vetture vendute",
    "Z07": "Piazzale Lavaggio", "Z08": "Commercianti senza telo",
    "Z09": "Commercianti con telo", "Z10": "Lavorazioni esterni", "Z11": "Verso altre sedi"
}

st.set_page_config(page_title="AUTOCLUB CENTER USATO 1.1", layout="wide")

# --- 4. GESTIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None
if 'last_action' not in st.session_state:
    st.session_state['last_action'] = datetime.now()
if 'zona_id' not in st.session_state: st.session_state['zona_id'] = ""
if 'zona_nome' not in st.session_state: st.session_state['zona_nome'] = ""
if 'zona_id_sposta' not in st.session_state: st.session_state['zona_id_sposta'] = ""
if 'zona_nome_sposta' not in st.session_state: st.session_state['zona_nome_sposta'] = ""
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

# --- 5. FUNZIONI CORE ---
def aggiorna_presenza(utente, pagina=""):
    try:
        supabase.table("sessioni_attive").upsert({
            "utente": utente,
            "last_seen": datetime.now().isoformat(),
            "pagina": pagina
        }).execute()
    except: pass

def get_operatori_attivi(minuti=5):
    try:
        limite = (datetime.now() - timedelta(minutes=minuti)).isoformat()
        res = supabase.table("sessioni_attive").select("*").gte("last_seen", limite).execute()
        return res.data if res.data else []
    except: return []

def registra_log(targa, azione, d, u):
    try:
        supabase.table("log_movimenti").insert({"targa": targa, "azione": azione, "dettaglio": d, "utente": u}).execute()
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
    st.title("🔐 Accesso Autoclub Center Usato 1.1")
    u = st.selectbox("Operatore", ["- Seleziona -"] + list(CREDENZIALI.keys()))
    p = st.text_input("PIN", type="password")
    if st.button("ACCEDI"):
        if u != "- Seleziona -" and p == CREDENZIALI.get(u):
            st.session_state['user_autenticato'] = u
            aggiorna_attivita(); st.rerun()
        else: st.error("Accesso negato")
else:
    utente_attivo = st.session_state['user_autenticato']
    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "✏️ Modifica", "📋 Verifica Zone", "📊 Dashboard Zone", "📊 Dashboard Generale", "📊 Export", "📜 Log", "🖨️ Stampa QR", "♻️ Ripristina"]
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True)
    st.markdown("---")
    aggiorna_presenza(utente_attivo, scelta)

    with st.sidebar:
        st.info(f"👤 {utente_attivo}")
        st.markdown("### 👥 Operatori attivi")
        attivi = get_operatori_attivi(minuti=10)
        if attivi:
            for o in attivi:
                stato = "🟢" if o["utente"] != utente_attivo else "🟡"
                pagina = o.get("pagina", "")
                st.caption(f"{stato} **{o['utente']}** \n_{pagina}_")
        else: st.caption("Nessun altro operatore collegato")
        st.sidebar.markdown("---")
        st.sidebar.markdown("### 📷 Scanner QR")
        st.checkbox("Attiva scanner", key="camera_attiva")
        if st.button("Log-out"): st.session_state.clear(); st.rerun()

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
        else: st.warning("⚠️ Scanner disattivato dalla Sidebar.")

        with st.form("f_ingresso", clear_on_submit=True):
            if not st.session_state['zona_id']: st.error("❌ Scansione QR Obbligatoria per abilitare la registrazione")
            else: st.info(f"📍 Zona selezionata: **{st.session_state['zona_nome']}**")
           
            targa = st.text_input("TARGA").upper().strip()
            marche = get_marche()
            m_sel = st.selectbox("Marca", ["Nuova..."] + marche)
            if m_sel == "Nuova...": m_sel = st.text_input("Inserisci Marca").upper()
            mod_sel = st.selectbox("Modello", ["Nuovo..."] + get_modelli(m_sel))
            if mod_sel == "Nuovo...": mod_sel = st.text_input("Inserisci Modello").upper()
           
            c_sug = suggerisci_colore(targa) if targa else None
            if c_sug: st.info(f"🎨 Suggerito: **{c_sug}**")
            colore = st.selectbox("Colore", ["Nuovo..."] + get_colori())
            if colore == "Nuovo...": colore = st.text_input("Specifica Colore")
            km = st.number_input("Chilometri", min_value=0, step=100)
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1)
            note = st.text_area("Note")

            if st.form_submit_button("REGISTRA LA VETTURA", disabled=not st.session_state['zona_id']):
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("❌ Targa non valida"); st.stop()
                
                check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                if check.data:
                    st.error("❌ Vettura già presente!"); st.stop()

                data_pulita = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

                data = {
                    "targa": targa, "marca_modello": f"{m_sel.strip()} {mod_sel.strip()}",
                    "colore": colore.strip().capitalize(), "km": int(km), "numero_chiave": int(n_chiave),
                    "zona_id": st.session_state["zona_id"], "zona_attuale": st.session_state["zona_nome"],
                    "data_ingresso": data_pulita,
                    "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo
                }
                supabase.table("parco_usato").insert(data).execute()
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
                st.success("✅ Vettura registrata!"); st.session_state["zona_id"] = ""; st.session_state["zona_nome"] = ""
                time.sleep(1); st.rerun()

    # --- 9. SEZIONE RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Spostamento")
        if st.session_state.camera_attiva:
            foto_sp = st.camera_input("Scansiona QR della Zona di DESTINAZIONE", key="cam_sp")
            if foto_sp:
                z_id_sp = leggi_qr_zona(foto_sp)
                if z_id_sp:
                    st.session_state["zona_id_sposta"] = z_id_sp
                    st.session_state["zona_nome_sposta"] = ZONE_INFO[z_id_sp]
                    st.info(f"✅ Destinazione: {st.session_state['zona_nome_sposta']}")
        
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
                            c1, c2 = st.columns(2)
                            if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not st.session_state['zona_id_sposta']):
                                supabase.table("parco_usato").update({"zona_id": st.session_state["zona_id_sposta"], "zona_attuale": st.session_state["zona_nome_sposta"]}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Spostamento", f"In {st.session_state['zona_nome_sposta']}", utente_attivo)
                                st.session_state["zona_id_sposta"] = ""; st.session_state["zona_nome_sposta"] = ""
                                st.success("✅ Spostata!"); time.sleep(1); st.rerun()
                            with c2:
                                conf_key = f"conf_{v['targa']}"
                                if conf_key not in st.session_state: st.session_state[conf_key] = False
                                st.checkbox("⚠️ Confermo CONSEGNA", key=conf_key)
                                if st.button("🔴 CONSEGNA", key=f"btn_{v['targa']}", disabled=not st.session_state[conf_key]):
                                    supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                    registra_log(v['targa'], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                    st.success("✅ CONSEGNA REGISTRATA"); time.sleep(1); st.rerun()

    # --- 10. MODIFICA ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("Correzione Dati")
        tipo_m = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True, key="m_search_type")
        q_mod = st.text_input("Inserisci valore da cercare").strip().upper()
        
        if q_mod:
            col_m = "targa" if tipo_m == "Targa" else "numero_chiave"
            val_m = q_mod if tipo_m == "Targa" else int(q_mod) if q_mod.isdigit() else None
            
            if val_m is not None:
                res = supabase.table("parco_usato").select("*").eq(col_m, val_m).eq("stato", "PRESENTE").execute()
                if res.data:
                    v = res.data[0]
                    st.info(f"📝 Modificando: **{v['targa']}** | Chiave: **{v['numero_chiave']}**")
                    with st.form("f_mod"):
                        upd = {
                            "marca_modello": st.text_input("Modello", value=v['marca_modello']).upper(), 
                            "colore": st.text_input("Colore", value=v['colore']).strip().capitalize(), 
                            "km": st.number_input("KM", value=int(v['km'])), 
                            "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])), 
                            "note": st.text_area("Note", value=v['note'])
                        }
                        if st.form_submit_button("SALVA"):
                            supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                            registra_log(v['targa'], "Modifica", "Correzione", utente_attivo)
                            st.success("✅ Salvato!"); time.sleep(1); st.rerun()
                else:
                    st.error(f"❌ Nessun veicolo presente trovato con {tipo_m}: {q_mod}")

    # --- 11. DASHBOARD GENERALE ---
    elif scelta == "📊 Dashboard Generale":
        st.subheader("📊 Dashboard Generale Piazzale")
        presenti_res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        consegnati_res = supabase.table("parco_usato").select("*").eq("stato", "CONSEGNATO").execute()
        presenti = presenti_res.data or []
        consegnati = consegnati_res.data or []

        giorni = []
        for v in presenti:
            raw = v.get("data_ingresso")
            if not raw: continue
            try:
                data_ingresso = pd.to_datetime(raw, errors="coerce")
                if pd.isna(data_ingresso): continue
                giorni.append((datetime.now() - data_ingresso).days)
            except Exception: continue

        giorni_validi = [g for g in giorni if g >= 0]
        media = round(sum(giorni_validi) / len(giorni_validi), 1) if giorni_validi else 0
        critiche = len([g for g in giorni_validi if g >= 30])

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("🚗 Presenti", len(presenti))
        c2.metric("📦 Consegnate", len(consegnati))
        c3.metric("📍 Zone attive", len({v["zona_id"] for v in presenti if v.get("zona_id")}))
        c4.metric("⏱️ Giorni medi", media)
        c5.metric("⚠️ +30 giorni", critiche)

        st.markdown("---")
        st.subheader("📜 Attività di Oggi")
        oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        log_res = supabase.table("log_movimenti").select("*").gte("created_at", oggi.isoformat()).order("created_at", desc=True).execute()
        logs = log_res.data or []
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🔄 Movimenti", len(logs))
        k2.metric("👤 Operatori", len({l["utente"] for l in logs if l.get("utente")}))
        k3.metric("➕ Ingressi", sum(1 for l in logs if l.get("azione") == "Ingresso"))
        k4.metric("📦 Consegne", sum(1 for l in logs if l.get("azione") == "Consegna"))

        if logs:
            df_log = pd.DataFrame(logs)
            df_log["Ora"] = pd.to_datetime(df_log["created_at"]).dt.strftime("%H:%M")
            st.dataframe(df_log[["Ora", "targa", "azione", "utente"]], use_container_width=True)

    # --- 12. EXPORT ---
    elif scelta == "📊 Export":
        st.subheader("📊 Export Piazzale")
        z_exp = st.selectbox("Zona", ["TUTTE"] + list(ZONE_INFO.keys()))
        try:
            q = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE")
            if z_exp != "TUTTE": q = q.eq("zona_id", z_exp)
            res = q.execute()
            if res.data:
                df = pd.DataFrame(res.data)
                if "data_ingresso" in df.columns:
                    df["data_ingresso"] = pd.to_datetime(df["data_ingresso"], errors="coerce")
                    df["Data Inserimento"] = df["data_ingresso"].dt.strftime("%d/%m/%Y %H:%M")
                else: df["Data Inserimento"] = "N/D"
                
                cols = ["targa", "marca_modello", "colore", "km", "numero_chiave", "zona_attuale", "Data Inserimento", "note"]
                df_out = df[cols].copy()
                st.dataframe(df_out, use_container_width=True)
                out = BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as w: df_out.to_excel(w, index=False)
                st.download_button("📥 Scarica Excel", out.getvalue(), f"Piazzale_{z_exp}.xlsx")
        except Exception as e: st.error(f"❌ Errore: {e}")

    elif scelta == "📋 Verifica Zone":
        st.subheader("📋 Analisi Piazzale")
        z_id_v = st.selectbox("Zona da analizzare", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("parco_usato").select("*").eq("zona_id", z_id_v).eq("stato", "PRESENTE").execute()
        st.metric("Posti Occupati", len(res.data) if res.data else 0)
        if res.data: st.dataframe(pd.DataFrame(res.data)[["targa", "marca_modello", "colore"]], use_container_width=True)

    elif scelta == "📊 Dashboard Zone":
        st.subheader("📍 Storico Movimenti Zona")
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[z_sel]}%").order("created_at", desc=True).limit(50).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df["Data/Ora"] = (
                pd.to_datetime(df["created_at"], errors="coerce")
                .dt.strftime("%d/%m/%Y %H:%M:%S")
            )
            st.dataframe(
                df[["Data/Ora", "targa", "azione", "utente"]],
                use_container_width=True
            )

    elif scelta == "📜 Log":
        st_autorefresh(interval=10000, key="log_ref")
        
        # 1️⃣ FILTRO LOG PER OPERATORE
        operatori = ["TUTTI"] + sorted(set(CREDENZIALI.keys()))
        operatore_sel = st.selectbox("👤 Filtra per operatore", operatori)

        # 📆 2️⃣ FILTRO DATA (oggi / ieri / settimana)
        periodo = st.radio(
            "📆 Periodo",
            ["Oggi", "Ieri", "Ultimi 7 giorni", "Tutto"],
            horizontal=True
        )

        query = supabase.table("log_movimenti").select("*")

        if operatore_sel != "TUTTI":
            query = query.eq("utente", operatore_sel)

        oggi_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        if periodo == "Oggi":
            query = query.gte("created_at", oggi_dt.isoformat())
        elif periodo == "Ieri":
            ieri_dt = oggi_dt - timedelta(days=1)
            query = query.gte("created_at", ieri_dt.isoformat()).lt("created_at", oggi_dt.isoformat())
        elif periodo == "Ultimi 7 giorni":
            settimana_dt = oggi_dt - timedelta(days=7)
            query = query.gte("created_at", settimana_dt.isoformat())

        logs = query.order("created_at", desc=True).limit(200).execute()

        if logs.data:
            df = pd.DataFrame(logs.data)

            # 🔧 FORMAT DATA SENZA MILLESIMI E FUSO ORARIO
            df["Data/Ora"] = (
                pd.to_datetime(df["created_at"], errors="coerce")
                .dt.strftime("%d/%m/%Y %H:%M:%S")
            )

            st.dataframe(
                df[["Data/Ora", "targa", "azione", "utente"]],
                use_container_width=True
            )

            # 📤 3️⃣ EXPORT LOG EXCEL (1 click)
            df_export = df.copy()
            df_export["Data/Ora"] = (
                pd.to_datetime(df_export["created_at"], errors="coerce")
                .dt.strftime("%d/%m/%Y %H:%M:%S")
            )
            cols_export = ["Data/Ora", "targa", "azione", "utente", "dettaglio"]
            df_export = df_export[cols_export]

            out_log = BytesIO()
            with pd.ExcelWriter(out_log, engine="xlsxwriter") as w:
                df_export.to_excel(w, index=False)

            st.download_button(
                "📤 Scarica log Excel",
                out_log.getvalue(),
                f"log_movimenti_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    elif scelta == "🖨️ Stampa QR":
        z_pr = st.selectbox("Zona QR", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        qr_img = qrcode.make(f"ZONA|{z_pr}"); buf = BytesIO(); qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), width=300); st.download_button("Scarica QR", buf.getvalue(), f"QR_{z_pr}.png")

    elif scelta == "♻️ Ripristina":
        t_back = st.text_input("Targa da ripristinare").upper().strip()
        if t_back:
            res = supabase.table("parco_usato").select("*").eq("targa", t_back).eq("stato", "CONSEGNATO").execute()
            if res.data:
                if st.button(f"RIPRISTINA {t_back}"):
                    supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", t_back).execute()
                    registra_log(t_back, "Ripristino", "Riportata in PRESENTE", utente_attivo)
                    st.success("✅ Ripristinata!"); time.sleep(1); st.rerun()
            else: st.error("❌ Targa non trovata tra le consegnate.")
