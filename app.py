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

# --- 2. CREDENZIALI & TIMEOUT (AGGIORNATO A 10 MIN) ---
CREDENZIALI = {"Luca Simonini": "2026", "Ivan Pohorilyak": "1234", "Abdul": "0000", "Tommaso Zani": "1111", "Andrea Sachetti": "2345", "Roberto Gozzi": "3412" }
TIMEOUT_MINUTI = 10  # <--- Ritocco effettuato qui

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
    st.session_state['last_action'] = datetime.now()
if 'zona_id' not in st.session_state: st.session_state['zona_id'] = ""
if 'zona_nome' not in st.session_state: st.session_state['zona_nome'] = ""
if 'zona_id_sposta' not in st.session_state: st.session_state['zona_id_sposta'] = ""
if 'zona_nome_sposta' not in st.session_state: st.session_state['zona_nome_sposta'] = ""
if 'camera_attiva' not in st.session_state:
    st.session_state['camera_attiva'] = False
if "ingresso_salvato" not in st.session_state:
    st.session_state["ingresso_salvato"] = False

def aggiorna_attivita():
    st.session_state['last_action'] = datetime.now()

def controllo_timeout():
    if st.session_state['user_autenticato']:
        trascorso = datetime.now() - st.session_state['last_action']
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
        st.components.v1.html("<script>if (navigator.vibrate) navigator.vibrate([80,40,80]);</script>", height=0)
        return False
    st.success(f"✅ {len(risultati)} risultato/i trovato/i per {tipo}: {valore}")
    return True

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
        n_chiave = 0
        v_info = supabase.table("parco_usato").select("numero_chiave").eq("targa", targa).limit(1).execute()
        if v_info.data: n_chiave = v_info.data[0]["numero_chiave"]
        supabase.table("log_movimenti").insert({
            "targa": targa, "azione": azione, "dettaglio": d, "utente": u, "numero_chiave": n_chiave
        }).execute()
    except Exception as e: st.error(f"Errore Log: {e}")

def get_marche():
    try:
        res = supabase.table("parco_usato").select("marca_modello").execute()
        marche = {r["marca_modello"].split()[0].upper() for r in res.data if r.get("marca_modello")}
        return sorted(list(marche))
    except: return []

def get_modelli(marca):
    try:
        if not marca or marca == "- Seleziona -": return []
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
    st.title("🔐 Accesso Autoclub Center Usato 1.1 Master")
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

    # --- 8. SEZIONE INGRESSO (FIX MANUALE) ---
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

        with st.form("f_ingresso", clear_on_submit=False):
            if not st.session_state['zona_id']: 
                st.error("❌ Scansione QR Obbligatoria per abilitare la registrazione")
            else: 
                st.info(f"📍 Zona selezionata: **{st.session_state['zona_nome']}**")
           
            targa = st.text_input("TARGA", key="ing_targa").upper().strip()

            # 🏷️ MARCA
            marche = get_marche()
            marca_sel = st.selectbox("Marca", ["- Seleziona -", "Nuovo..."] + marche, key="marca_sel")
            marca_nuova = st.text_input("✍️ Inserisci nuova Marca (se 'Nuovo...')", key="marca_nuova").upper().strip()

            # 🚗 MODELLO
            modelli = get_modelli(marca_sel) if marca_sel != "Nuovo..." else []
            modello_sel = st.selectbox("Modello", ["- Seleziona -", "Nuovo..."] + modelli, key="modello_sel")
            modello_nuovo = st.text_input("✍️ Inserisci nuovo Modello (se 'Nuovo...')", key="modello_nuovo").upper().strip()

            # 🎨 COLORE
            c_sug = suggerisci_colore(targa) if targa else None
            if c_sug: st.info(f"🎨 Suggerito: **{c_sug}**")
            colori = get_colori()
            colore_sel = st.selectbox("Colore", ["- Seleziona -", "Nuovo..."] + colori, key="colore_sel")
            colore_nuovo = st.text_input("✍️ Inserisci nuovo Colore (se 'Nuovo...')", key="colore_nuovo").strip().capitalize()

            km = st.number_input("Chilometri", min_value=0, step=100, key="ing_km")
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1, key="ing_chiave")
            st.caption("ℹ️ **Chiave = 0** → vettura destinata ai commercianti")
            note = st.text_area("Note", key="ing_note")

            if st.form_submit_button("REGISTRA LA VETTURA", disabled=not st.session_state['zona_id']):
                # Logica finale valori
                m_fin = marca_nuova if marca_sel == "Nuovo..." else marca_sel
                md_fin = modello_nuovo if modello_sel == "Nuovo..." else modello_sel
                c_fin = colore_nuovo if colore_sel == "Nuovo..." else colore_sel

                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("❌ Formato Targa non valido"); st.stop()
                if m_fin in ["", "- Seleziona -"] or md_fin in ["", "- Seleziona -"] or c_fin in ["", "- Seleziona -"]:
                    st.error("❌ Seleziona o inserisci Marca, Modello e Colore"); st.stop()
                
                # Blocco Duplicati
                check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                if check.data: st.error("❌ Vettura già presente in piazzale!"); st.stop()
                
                data_pulita = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                data = {
                    "targa": targa, "marca_modello": f"{m_fin} {md_fin}".upper(),
                    "colore": c_fin, "km": int(km), "numero_chiave": int(n_chiave),
                    "zona_id": st.session_state["zona_id"], "zona_attuale": st.session_state["zona_nome"],
                    "data_ingresso": data_pulita, "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo
                }
                supabase.table("parco_usato").insert(data).execute()
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
                st.session_state["ingresso_salvato"] = True
                
                st.success("✅ Vettura registrata correttamente")
                st.markdown(f"""<div style="background-color:#0f172a; border-left:6px solid #22c55e; padding:16px; border-radius:8px; color:#e5e7eb; font-size:16px;">🚗 <b>{targa}</b><br>🏷️ <b>{m_fin} {md_fin}</b><br>📍 Zona: <b>{st.session_state["zona_nome"]}</b></div>""", unsafe_allow_html=True)

        if st.session_state.get("ingresso_salvato"):
            if st.button("➕ NUOVO INGRESSO", use_container_width=True):
                for k in ["ing_targa", "ing_km", "ing_chiave", "ing_note", "marca_sel", "marca_nuova", "modello_sel", "modello_nuovo", "colore_sel", "colore_nuovo"]:
                    if k in st.session_state: del st.session_state[k]
                st.session_state["zona_id"] = ""; st.session_state["zona_nome"] = ""; st.session_state["ingresso_salvato"] = False
                st.rerun()

    # --- 9. SEZIONE RICERCA / SPOSTA ---
    elif scelta == "🔍 Ricerca/Sposta":
        aggiorna_attivita()
        st.subheader("Ricerca e Spostamento")
        if st.session_state.camera_attiva:
            foto_sp = st.camera_input("Scansiona QR DESTINAZIONE", key="cam_sp")
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
                if not feedback_ricerca(tipo, q, res.data): st.stop()
                for v in res.data:
                    with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                        st.write(f"📍 Attuale: **{v['zona_attuale']}**")
                        c1, c2 = st.columns(2)
                        if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not st.session_state['zona_id_sposta']):
                            supabase.table("parco_usato").update({"zona_id": st.session_state["zona_id_sposta"], "zona_attuale": st.session_state["zona_nome_sposta"]}).eq("targa", v['targa']).execute()
                            registra_log(v['targa'], "Spostamento", f"In {st.session_state['zona_nome_sposta']}", utente_attivo)
                            st.session_state["zona_id_sposta"] = ""; st.session_state["zona_nome_sposta"] = ""
                            st.success("✅ Spostata!"); time.sleep(1); st.rerun()
                        with c2:
                            conf_key = f"conf_{v['targa']}"
                            st.checkbox("⚠️ Confermo CONSEGNA", key=conf_key)
                            if st.button("🔴 CONSEGNA", key=f"btn_{v['targa']}", disabled=not st.session_state.get(conf_key)):
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                st.success("✅ CONSEGNA REGISTRATA"); time.sleep(1); st.rerun()

    # --- SEZIONI RESTANTI ---
    elif scelta == "✏️ Modifica":
        aggiorna_attivita()
        st.subheader("Correzione Dati")
        tipo_m = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True, key="m_search_type")
        q_mod = st.text_input("Valore").strip().upper()
        if q_mod:
            col_m = "targa" if tipo_m == "Targa" else "numero_chiave"
            val_m = q_mod if tipo_m == "Targa" else int(q_mod) if q_mod.isdigit() else None
            if val_m is not None:
                res = supabase.table("parco_usato").select("*").eq(col_m, val_m).eq("stato", "PRESENTE").execute()
                if not feedback_ricerca(tipo_m, q_mod, res.data): st.stop()
                v = res.data[0]
                with st.form("f_mod"):
                    upd = {"marca_modello": st.text_input("Modello", value=v['marca_modello']).upper(), "colore": st.text_input("Colore", value=v['colore']).strip().capitalize(), "km": st.number_input("KM", value=int(v['km'])), "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])), "note": st.text_area("Note", value=v['note'])}
                    if st.form_submit_button("SALVA"):
                        supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                        registra_log(v['targa'], "Modifica", "Correzione", utente_attivo)
                        st.success("✅ Salvato!"); time.sleep(1); st.rerun()

    elif scelta == "📊 Dashboard Generale":
        st.subheader("📊 Dashboard Generale")
        pres_res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        presenti = pres_res.data or []
        st.metric("🚗 Vetture in Piazzale", len(presenti))
        st.markdown("---")
        st.subheader("📜 Movimenti Recenti")
        log_res = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(20).execute()
        if log_res.data:
            df_log = pd.DataFrame(log_res.data)
            df_log["Ora"] = pd.to_datetime(df_log["created_at"]).dt.strftime("%H:%M")
            st.dataframe(df_log[["Ora", "targa", "azione", "utente"]], use_container_width=True)

    elif scelta == "📊 Export":
        st.subheader("📊 Export Dati")
        res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.dataframe(df[["targa", "marca_modello", "zona_attuale", "numero_chiave"]], use_container_width=True)
            out = BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as w: df.to_excel(w, index=False)
            st.download_button("📥 Scarica Excel", out.getvalue(), "piazzale.xlsx")

    elif scelta == "📋 Verifica Zone":
        st.subheader("📋 Analisi Zone")
        z_id_v = st.selectbox("Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("parco_usato").select("*").eq("zona_id", z_id_v).eq("stato", "PRESENTE").execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data)[["targa", "marca_modello", "colore", "numero_chiave"]], use_container_width=True)
        else: st.warning("Zona vuota")

    elif scelta == "📊 Dashboard Zone":
        st.subheader("📍 Storico Zona")
        z_sel = st.selectbox("Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[z_sel]}%").order("created_at", desc=True).limit(50).execute()
        if res.data: st.dataframe(pd.DataFrame(res.data)[["targa", "azione", "utente", "created_at"]], use_container_width=True)

    elif scelta == "📜 Log":
        st_autorefresh(interval=30000, key="log_ref")
        logs = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(100).execute()
        if logs.data: st.dataframe(pd.DataFrame(logs.data), use_container_width=True)

    elif scelta == "🖨️ Stampa QR":
        z_pr = st.selectbox("Zona QR", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        qr_img = qrcode.make(f"ZONA|{z_pr}"); buf = BytesIO(); qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), width=250); st.download_button("Scarica QR", buf.getvalue(), f"QR_{z_pr}.png")

    elif scelta == "♻️ Ripristina":
        t_back = st.text_input("Targa consegnata da ripristinare").upper().strip()
        if t_back:
            if st.button(f"RIPRISTINA {t_back}"):
                supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", t_back).execute()
                registra_log(t_back, "Ripristino", "Riportata in PRESENTE", utente_attivo)
                st.success("✅ Ripristinata!"); time.sleep(1); st.rerun()
