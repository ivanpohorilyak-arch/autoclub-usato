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
TIMEOUT_MINUTI = 10

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
        if not marca: return []
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

        with st.form("f_ingresso"):
            if not st.session_state['zona_id']: st.error("❌ Scansione QR Obbligatoria per abilitare la registrazione")
            else: st.info(f"📍 Zona selezionata: **{st.session_state['zona_nome']}**")
           
            targa = st.text_input("TARGA", key="ing_targa").upper().strip()

            # ---------- MARCA ----------
            marche = get_marche()
            marca = st.text_input("Marca", key="marca_input").upper().strip()
            sug_marche = [m for m in marche if m.startswith(marca)] if marca else marche[:5]
            if sug_marche:
                sel_marca = st.selectbox("Suggerimenti Marca", [""] + sug_marche, key="marca_sug")
                if sel_marca:
                    marca = sel_marca
                    st.session_state["marca_input"] = sel_marca

            # ---------- MODELLO ----------
            modelli = get_modelli(marca) if marca else []
            modello = st.text_input("Modello", key="modello_input").upper().strip()
            sug_mod = [m for m in modelli if m.startswith(modello)] if modello else modelli[:5]
            if sug_mod:
                sel_mod = st.selectbox("Suggerimenti Modello", [""] + sug_mod, key="modello_sug")
                if sel_mod:
                    modello = sel_mod
                    st.session_state["modello_input"] = sel_mod
           
            c_sug = suggerisci_colore(targa) if targa else None
            if c_sug: st.info(f"🎨 Suggerito: **{c_sug}**")

            # ---------- COLORE ----------
            colori = get_colori()
            colore = st.text_input("Colore", key="colore_input").capitalize().strip()
            sug_col = [c for c in colori if c.lower().startswith(colore.lower())] if colore else colori
            if sug_col:
                sel_col = st.selectbox("Suggerimenti Colore", [""] + sug_col, key="colore_sug")
                if sel_col:
                    colore = sel_col
                    st.session_state["colore_input"] = sel_col

            km = st.number_input("Chilometri", min_value=0, step=100, key="ing_km")
            n_chiave = st.number_input("N. Chiave", min_value=0, step=1, key="ing_chiave")
            st.caption("ℹ️ **Chiave = 0** → vettura **destinata ai commercianti** (nessuna chiave fisica)")
            note = st.text_area("Note", key="ing_note")

            if st.form_submit_button("REGISTRA LA VETTURA", disabled=not st.session_state['zona_id']):
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.warning("❌ Targa non valida"); st.stop()
                if not marca or not modello or not colore:
                    st.error("❌ Marca, Modello e Colore sono obbligatori"); st.stop()
                
                check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                if check.data: st.error("❌ Vettura già presente!"); st.stop()
                
                data_pulita = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                data = {
                    "targa": targa, "marca_modello": f"{marca} {modello}",
                    "colore": colore, "km": int(km), "numero_chiave": int(n_chiave),
                    "zona_id": st.session_state["zona_id"], "zona_attuale": st.session_state["zona_nome"],
                    "data_ingresso": data_pulita, "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo
                }
                supabase.table("parco_usato").insert(data).execute()
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)
                st.session_state["ingresso_salvato"] = True
                
                st.success("✅ Vettura registrata correttamente")
                st.markdown(f"""<div style="background-color:#0f172a; border-left:6px solid #22c55e; padding:16px; border-radius:8px; color:#e5e7eb; font-size:16px; margin-top:10px;">🚗 <b>{targa}</b><br>🏷️ <b>{marca} {modello}</b><br>🎨 Colore: <b>{colore}</b><br>🔑 Chiave: <b>{n_chiave}</b><br>📍 Zona: <b>{st.session_state["zona_nome"]}</b><br>👤 Operatore: <b>{utente_attivo}</b></div>""", unsafe_allow_html=True)
                st.components.v1.html("<script>if (navigator.vibrate) { navigator.vibrate([120, 60, 120]); }</script>", height=0)

        if st.session_state.get("ingresso_salvato"):
            st.markdown("---")
            if st.button("➕ NUOVO INGRESSO", use_container_width=True):
                for k in ["ing_targa", "ing_km", "ing_chiave", "ing_note", "marca_input", "marca_sug", "modello_input", "modello_sug", "colore_input", "colore_sug"]:
                    if k in st.session_state: del st.session_state[k]
                st.session_state["zona_id"] = ""; st.session_state["zona_nome"] = ""
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
                
                if not feedback_ricerca(tipo, q, res.data): 
                    st.stop()
                
                for v in res.data:
                    with st.expander(f"🚗 {v['targa']} - {v['marca_modello']}", expanded=True):
                        st.write(f"📍 Posizione attuale: **{v['zona_attuale']}**")
                        st.markdown("---")
                        st.markdown("#### 🔄 Azione Spostamento")
                        
                        if st.session_state.camera_attiva:
                            foto_sp = st.camera_input(f"Scansiona QR Destinazione per {v['targa']}", key=f"cam_{v['targa']}")
                            if foto_sp:
                                z_id_sp = leggi_qr_zona(foto_sp)
                                if z_id_sp:
                                    st.session_state["zona_id_sposta"] = z_id_sp
                                    st.session_state["zona_nome_sposta"] = ZONE_INFO[z_id_sp]
                                    st.success(f"📍 Destinazione rilevata: **{st.session_state['zona_nome_sposta']}**")
                                else:
                                    st.error("❌ QR Zona non valido")
                        else:
                            st.warning("📷 Attiva lo scanner nella Sidebar per abilitare lo spostamento")

                        if not st.session_state['zona_id_sposta']:
                            st.caption("ℹ️ Per spostare questa vettura, scansiona il **QR della zona di arrivo**.")
                        
                        c1, c2 = st.columns(2)
                        
                        if c1.button("SPOSTA QUI", key=f"b_{v['targa']}", disabled=not st.session_state['zona_id_sposta'], use_container_width=True):
                            supabase.table("parco_usato").update({
                                "zona_id": st.session_state["zona_id_sposta"], 
                                "zona_attuale": st.session_state["zona_nome_sposta"]
                            }).eq("targa", v['targa']).execute()
                            
                            registra_log(v['targa'], "Spostamento", f"In {st.session_state['zona_nome_sposta']}", utente_attivo)
                            st.session_state["zona_id_sposta"] = ""
                            st.session_state["zona_nome_sposta"] = ""
                            st.success("✅ Vettura Spostata!")
                            time.sleep(1); st.rerun()
                        
                        with c2:
                            conf_key = f"conf_{v['targa']}"
                            if conf_key not in st.session_state: st.session_state[conf_key] = False
                            st.checkbox("⚠️ Confermo CONSEGNA DEFINITIVA", key=conf_key)
                            if st.button("🔴 CONSEGNA", key=f"btn_{v['targa']}", disabled=not st.session_state[conf_key], use_container_width=True):
                                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute()
                                registra_log(v['targa'], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                                st.success("✅ CONSEGNA REGISTRATA")
                                time.sleep(1); st.rerun()

    # --- SEZIONI RESTANTI INVARIATE ---
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
                if not feedback_ricerca(tipo_m, q_mod, res.data): st.stop()
                v = res.data[0]
                st.info(f"📝 Modificando: **{v['targa']}** | Chiave: **{v['numero_chiave']}**")
                with st.form("f_mod"):
                    upd = {"marca_modello": st.text_input("Modello", value=v['marca_modello']).upper(), "colore": st.text_input("Colore", value=v['colore']).strip().capitalize(), "km": st.number_input("KM", value=int(v['km'])), "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])), "note": st.text_area("Note", value=v['note'])}
                    if st.form_submit_button("SALVA"):
                        supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()
                        registra_log(v['targa'], "Modifica", "Correzione", utente_attivo)
                        st.success("✅ Salvato!"); time.sleep(1); st.rerun()

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
        c1.metric("🚗 Presenti", len(presenti)); c2.metric("📦 Consegnate", len(consegnati)); c3.metric("📍 Zone attive", len({v["zona_id"] for v in presenti if v.get("zona_id")})); c4.metric("⏱️ Giorni medi", media); c5.metric("⚠️ +30 giorni", critiche)
        st.markdown("---")
        st.subheader("📜 Attività di Oggi")
        oggi = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        log_res = supabase.table("log_movimenti").select("*").gte("created_at", oggi.isoformat()).order("created_at", desc=True).execute()
        logs = log_res.data or []
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("🔄 Movimenti", len(logs)); k2.metric("👤 Operatori", len({l["utente"] for l in logs if l.get("utente")})); k3.metric("➕ Ingressi", sum(1 for l in logs if l.get("azione") == "Ingresso")); k4.metric("📦 Consegne", sum(1 for l in logs if l.get("azione") == "Consegna"))
        if logs:
            df_log = pd.DataFrame(logs); df_log["Ora"] = pd.to_datetime(df_log["created_at"]).dt.strftime("%H:%M")
            st.dataframe(df_log[["Ora", "targa", "azione", "utente"]], use_container_width=True)

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
                df_out = df[cols].copy(); st.dataframe(df_out, use_container_width=True)
                out = BytesIO()
                with pd.ExcelWriter(out, engine="xlsxwriter") as w: df_out.to_excel(w, index=False)
                st.download_button("📥 Scarica Excel", out.getvalue(), f"Piazzale_{z_exp}.xlsx")
        except Exception as e: st.error(f"❌ Errore: {e}")

    elif scelta == "📋 Verifica Zone":
        st.subheader("📋 Analisi Piazzale")
        z_id_v = st.selectbox("Zona da analizzare", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("parco_usato").select("*").eq("zona_id", z_id_v).eq("stato", "PRESENTE").execute()
        posti = len(res.data) if res.data else 0
        st.metric("Posti Occupati", posti)
        if posti == 0: st.warning("⚠️ Nessuna vettura presente in questa zona")
        if res.data:
            df_zona = pd.DataFrame(res.data)
            st.dataframe(df_zona[["targa", "marca_modello", "colore", "numero_chiave"]], use_container_width=True)

    elif scelta == "📊 Dashboard Zone":
        st.subheader("📍 Storico Movimenti Zona")
        z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[z_sel]}%").order("created_at", desc=True).limit(50).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            if "numero_chiave" not in df.columns: df["numero_chiave"] = None
            df["Data/Ora"] = pd.to_datetime(df["created_at"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M:%S")
            st.dataframe(df[["Data/Ora", "targa", "azione", "utente", "numero_chiave"]], use_container_width=True)

    elif scelta == "📜 Log":
        st_autorefresh(interval=10000, key="log_ref")
        operatori = ["TUTTI"] + sorted(list(CREDENZIALI.keys()))
        operatore_sel = st.selectbox("👤 Filtra per operatore", operatori)
        periodo = st.radio("📆 Periodo", ["Oggi", "Ieri", "Ultimi 7 giorni", "Tutto"], horizontal=True)
        targa_search = st.text_input("🔎 Cerca targa (parziale o completa)").upper().strip()
        query = supabase.table("log_movimenti").select("*")
        if operatore_sel != "TUTTI": query = query.eq("utente", operatore_sel)
        if targa_search: query = query.ilike("targa", f"%{targa_search}%")
        oggi_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        if periodo == "Oggi": query = query.gte("created_at", oggi_dt.isoformat())
        elif periodo == "Ieri":
            ieri_dt = oggi_dt - timedelta(days=1)
            query = query.gte("created_at", ieri_dt.isoformat()).lt("created_at", oggi_dt.isoformat())
        elif periodo == "Ultimi 7 giorni":
            settimana_dt = oggi_dt - timedelta(days=7)
            query = query.gte("created_at", settimana_dt.isoformat())
        logs = query.order("created_at", desc=True).limit(200).execute()
        if logs.data:
            df = pd.DataFrame(logs.data)
            if "numero_chiave" not in df.columns: df["numero_chiave"] = None
            df["Data/Ora"] = pd.to_datetime(df["created_at"], errors="coerce").dt.strftime("%d/%m/%Y %H:%M:%S")
            st.markdown("### 📊 KPI Operatori")
            if not df.empty:
                kpi_ops = df.groupby("utente").size().reset_index(name="Movimenti").sort_values("Movimenti", ascending=False)
                c1, c2, c3 = st.columns(3)
                top = kpi_ops.iloc[0]; c1.metric("🥇 Operatore più attivo", top["utente"]); c2.metric("🔄 Movimenti", int(top["Movimenti"])); c3.metric("👥 Operatori coinvolti", kpi_ops["utente"].nunique())
                with st.expander("📋 Dettaglio movimenti per operatore"): st.dataframe(kpi_ops, use_container_width=True)
            st.markdown("### 📍 KPI Zone")
            if "dettaglio" in df.columns:
                df_zone_kpi = df.copy()
                df_zone_kpi["zona"] = df_zone_kpi["dettaglio"].str.replace("In ", "", regex=False)
                kpi_zone = df_zone_kpi.groupby("zona").agg(Movimenti=("targa", "count"), Chiavi_coinvolte=("numero_chiave", lambda x: ", ".join(sorted({str(int(i)) for i in x.dropna() if str(i).isdigit()})))).reset_index().sort_values("Movimenti", ascending=False)
                if not kpi_zone.empty:
                    z1, z2, z3 = st.columns(3); top_z = kpi_zone.iloc[0]
                    z1.metric("🏆 Zona più movimentata", top_z["zona"]); z2.metric("🔄 Movimenti", int(top_z["Movimenti"])); z3.metric("🔑 Chiavi coinvolte", len(top_z["Chiavi_coinvolte"].split(",")) if top_z["Chiavi_coinvolte"] else 0)
                    with st.expander("📋 Dettaglio movimenti per zona (con chiavi)"): st.dataframe(kpi_zone, use_container_width=True)
            st.dataframe(df[["Data/Ora", "targa", "azione", "utente", "numero_chiave"]], use_container_width=True)
            df_export = df.copy(); cols_export = ["Data/Ora", "targa", "azione", "utente", "numero_chiave", "dettaglio"]
            out_log = BytesIO()
            with pd.ExcelWriter(out_log, engine="xlsxwriter") as w: df_export[cols_export].to_excel(w, index=False)
            st.download_button("📤 Scarica log Excel", out_log.getvalue(), f"log_movimenti_{datetime.now().strftime('%d_%m_%Y')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    elif scelta == "🖨️ Stampa QR":
        z_pr = st.selectbox("Zona QR", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        qr_img = qrcode.make(f"ZONA|{z_pr}"); buf = BytesIO(); qr_img.save(buf, format="PNG")
        st.image(buf.getvalue(), width=300); st.download_button("Scarica QR", buf.getvalue(), f"QR_{z_pr}.png")

    elif scelta == "♻️ Ripristina":
        t_back = st.text_input("Targa da ripristinare").upper().strip()
        if t_back:
            res = supabase.table("parco_usato").select("*").eq("targa", t_back).eq("stato", "CONSEGNATO").execute()
            if not feedback_ricerca("Targa consegnata", t_back, res.data): st.stop()
            if st.button(f"RIPRISTINA {t_back}"):
                supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", t_back).execute()
                registra_log(t_back, "Ripristino", "Riportata in PRESENTE", utente_attivo)
                st.success("✅ Ripristinata!"); time.sleep(1); st.rerun()
