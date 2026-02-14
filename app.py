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
    os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"] 
)

# --- 2. CONFIGURAZIONE ZONE ---
ZONE_INFO = {
    "Z01": "Deposito N.9", "Z02": "Deposito N.7", "Z03": "Deposito N.6 (Lavaggisti)", 
    "Z04": "Deposito unificato 1 e 2", "Z05": "Showroom", "Z06": "Vetture vendute", 
    "Z07": "Piazzale Lavaggio", "Z08": "Commercianti senza telo", 
    "Z09": "Commercianti con telo", "Z10": "Lavorazioni esterni", 
    "Z11": "Verso altre sedi", "Z12": "Deposito N.10", "Z13": "Deposito N.8",
    "Z14": "Esterno (Con o Senza telo Motorsclub)" 
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
if 'camera_attiva' not in st.session_state:
    st.session_state['camera_attiva'] = False 
if "ingresso_salvato" not in st.session_state:
    st.session_state["ingresso_salvato"] = False 

if "ricerca_attiva" not in st.session_state:
    st.session_state["ricerca_attiva"] = False 
if "ricerca_risultati" not in st.session_state:
    st.session_state["ricerca_risultati"] = [] 
if "vettura_selezionata" not in st.session_state:
    st.session_state["vettura_selezionata"] = None 
if "form_ingresso_ver" not in st.session_state:
    st.session_state["form_ingresso_ver"] = 0 
if "azione_attiva" not in st.session_state:
    st.session_state["azione_attiva"] = None 
if "post_azione_msg" not in st.session_state:
    st.session_state["post_azione_msg"] = None 

# Supporto per la chiave proposta
if "valore_chiave_proposta" not in st.session_state:
    st.session_state["valore_chiave_proposta"] = 0

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
def trova_prima_chiave_libera():
    try:
        res = supabase.table("parco_usato").select("numero_chiave").eq("stato", "PRESENTE").execute()
        occupate = set()
        if res.data:
            for r in res.data:
                num = r.get("numero_chiave")
                if num and 1 <= int(num) <= 520:
                    occupate.add(int(num))
        for i in range(1, 521):
            if i not in occupate:
                return i
        return 0
    except:
        return 0

def descrivi_modifiche(old, new):
    campi = {
        "marca_modello": "Marca/Modello",
        "colore": "Colore",
        "km": "KM",
        "numero_chiave": "Chiave"
    }
    modifiche = []
    for k, label in campi.items():
        if str(old.get(k, "")).strip() != str(new.get(k, "")).strip():
            modifiche.append(f"{label} ({old.get(k)} → {new.get(k)})")
    return ", ".join(modifiche)

def feedback_ricerca(tipo, valore, risultati):
    if valore is None or valore == "": 
        st.info("⌨️ Inserisci un valore per iniziare la ricerca") 
        return False 
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

def reset_ricerca():
    st.session_state["ricerca_attiva"] = False 
    st.session_state["ricerca_risultati"] = [] 
    st.session_state["vettura_selezionata"] = None 
    st.session_state["azione_attiva"] = None 
    for k in ["chk_spost", "chk_mod", "chk_cons"]: 
        st.session_state.pop(k, None) 

def reset_azione():
    st.session_state["azione_attiva"] = None 
    for k in ["chk_spost", "chk_mod", "chk_cons"]: 
        st.session_state.pop(k, None) 

# --- CALLBACK PER MUTUA ESCLUSIONE FLAG ---
def cb_spost():
    if st.session_state.chk_spost: 
        st.session_state["azione_attiva"] = "spost" 
        st.session_state["chk_mod"] = False 
        st.session_state["chk_cons"] = False 
    else: st.session_state["azione_attiva"] = None 

def cb_mod():
    if st.session_state.chk_mod: 
        st.session_state["azione_attiva"] = "mod" 
        st.session_state["chk_spost"] = False 
        st.session_state["chk_cons"] = False 
    else: st.session_state["azione_attiva"] = None 

def cb_cons():
    if st.session_state.chk_cons: 
        st.session_state["azione_attiva"] = "cons" 
        st.session_state["chk_spost"] = False 
        st.session_state["chk_mod"] = False 
    else: st.session_state["azione_attiva"] = None 

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
            st.session_state['can_consegna'] = user.get("can_consegna", False) 
            aggiorna_attivita() 
            st.rerun() 
        else: st.error("Accesso negato: PIN errato o utente non attivo") 

else:
    utente_attivo = st.session_state['user_autenticato'] 
    menu = ["➕ Ingresso", "🔍 Ricerca", "📋 Verifica Zone", "📊 Dashboard Zone", "📊 Dashboard Generale", "📊 Export", "📜 Log", "🖨️ Stampa QR", "♻️ Ripristina"] 
    if st.session_state["ruolo"] == "admin": menu.append("👥 Gestione Utenti") 
    scelta = st.radio("Seleziona Funzione", menu, horizontal=True) 
    st.session_state["pagina_attuale"] = scelta 
    st.markdown("---") 

    # --- 7. SIDEBAR --- 
    with st.sidebar: 
        st.info(f"👤 {utente_attivo} ({st.session_state['ruolo']})") 
        st.session_state['heartbeat'] = st_autorefresh(interval=30000, key="presence_heartbeat") 
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

        if st.button("🔑 CALCOLA PRIMA CHIAVE LIBERA (1-520)", use_container_width=True):
            st.session_state["valore_chiave_proposta"] = trova_prima_chiave_libera()
            st.rerun()

        with st.form(key=f"f_ingresso_{st.session_state['form_ingresso_ver']}"): 
            if not st.session_state['zona_id']: st.error("❌ Scansione QR Obbligatoria per abilitare i campi") 
            else: st.info(f"📍 Zona: **{st.session_state['zona_nome']}**") 
            
            targa = st.text_input("TARGA").upper().strip() 
            marca = st.text_input("Marca").upper().strip() 
            modello = st.text_input("Modello").upper().strip() 
            colore = st.text_input("Colore").capitalize().strip() 
            km = st.number_input("Chilometri", min_value=0, step=100) 
            
            n_chiave = st.number_input(
                "N. Chiave (0 = Commerciante)", 
                min_value=0, 
                max_value=520, 
                value=st.session_state["valore_chiave_proposta"],
                step=1
            ) 
            
            if n_chiave > 0:
                check_preview = supabase.table("parco_usato") \
                    .select("targa") \
                    .eq("numero_chiave", int(n_chiave)) \
                    .eq("stato", "PRESENTE") \
                    .limit(1) \
                    .execute()
                if check_preview.data:
                    st.warning(f"⚠️ Attenzione: chiave già usata da {check_preview.data[0]['targa']}")
            
            note = st.text_area("Note") 
            submit = st.form_submit_button("REGISTRA LA VETTURA", disabled=not st.session_state['zona_id']) 
            
            if submit: 
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa): st.error("Targa non valida"); st.stop() 
                
                check_t = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").limit(1).execute() 
                if check_t.data: st.error("Targa già presente nel piazzale!"); st.stop() 
                
                if n_chiave > 0:
                    check_k = supabase.table("parco_usato").select("targa").eq("numero_chiave", int(n_chiave)).eq("stato", "PRESENTE").limit(1).execute()
                    if check_k.data: 
                        st.error(f"La chiave {n_chiave} è già occupata dalla vettura {check_k.data[0]['targa']}"); st.stop()

                payload = { 
                    "targa": targa, "marca_modello": f"{marca} {modello}", "colore": colore, 
                    "km": int(km), "numero_chiave": int(n_chiave), "zona_id": st.session_state["zona_id"], 
                    "zona_attuale": st.session_state["zona_nome"], "data_ingresso": datetime.now(timezone.utc).isoformat(), 
                    "note": note, "stato": "PRESENTE", "utente_ultimo_invio": utente_attivo 
                } 
                supabase.table("parco_usato").insert(payload).execute() 
                
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']} | Nota: {note}" if note else f"In {st.session_state['zona_nome']}", utente_attivo) 
                
                st.session_state["ingresso_salvato"] = { "targa": targa, "modello": f"{marca} {modello}", "colore": colore, "km": int(km), "chiave": int(n_chiave), "zona": st.session_state["zona_nome"] } 
                st.session_state["valore_chiave_proposta"] = 0
                st.rerun() 
                
        if st.session_state.get("ingresso_salvato"): 
            info = st.session_state["ingresso_salvato"] 
            st.markdown(f""" <div style="background-color:#d4edda; border:1px solid #28a745; padding:16px; border-radius:10px; color:#155724;"> <h4>✅ Vettura registrata correttamente</h4> <b>🚗 Targa:</b> {info['targa']}<br> <b>📦 Modello:</b> {info['modello']}<br> <b>🎨 Colore:</b> {info['colore']}<br> <b>📏 Chilometri:</b> {info['km']}<br> <b>🔑 Numero chiave:</b> {info['chiave']}<br> <b>📍 Zona:</b> {info['zona']} </div> """, unsafe_allow_html=True) 
            if st.button("🆕 NUOVA REGISTRAZIONE", use_container_width=True): 
                st.session_state["ingresso_salvato"] = False 
                st.session_state["zona_id"] = "" 
                st.session_state["zona_nome"] = "" 
                st.session_state["form_ingresso_ver"] += 1 
                st.rerun() 

    # --- 9. SEZIONE RICERCA (UNIFICATA E PERSISTENTE) --- 
    elif scelta == "🔍 Ricerca": 
        aggiorna_attivita() 
        st.subheader("🔍 Ricerca Vettura") 
        if st.session_state.get("post_azione_msg"): 
            st.success(st.session_state["post_azione_msg"]) 
            st.markdown("### ✅ Operazione completata") 
            if st.button("🔍 Torna alla ricerca", use_container_width=True): 
                st.session_state["post_azione_msg"] = None 
                reset_ricerca() 
                st.rerun() 
            st.stop() 
        with st.form("f_ricerca_unica"): 
            tipo = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True) 
            q = st.text_input("Valore da cercare").strip().upper() 
            cerca = st.form_submit_button("🔍 CERCA") 
        if cerca and q: 
            col = "targa" if tipo == "Targa" else "numero_chiave" 
            val = q if tipo == "Targa" else int(q) if q.isdigit() else None 
            if val is None: st.error("Valore non valido") 
            else: 
                res = supabase.table("parco_usato").select("*").eq(col, val).eq("stato", "PRESENTE").execute() 
                if feedback_ricerca(tipo, q, res.data): 
                    st.session_state["ricerca_attiva"] = True 
                    st.session_state["ricerca_risultati"] = res.data 
                    st.session_state["vettura_selezionata"] = None 
                    st.session_state["azione_attiva"] = None 
        if st.session_state["ricerca_attiva"]: 
            risultati = st.session_state["ricerca_risultati"] 
            if len(risultati) > 1: 
                st.session_state["vettura_selezionata"] = st.selectbox( "Seleziona vettura", risultati, key="sel_vettura_select", format_func=lambda x: f"{x['targa']} | {x['marca_modello']} | Chiave {x['numero_chiave']}" ) 
            else: st.session_state["vettura_selezionata"] = risultati[0] 
            v = st.session_state["vettura_selezionata"] 
            if v: 
                st.markdown(f"## 🚗 Vettura: {v['targa']}") 
                c1, c2 = st.columns(2) 
                with c1: 
                    st.write(f"**Marca / Modello:** {v['marca_modello']}") 
                    st.write(f"**Colore:** {v['colore']}") 
                    st.write(f"**KM:** {v['km']}") 
                with c2: 
                    st.write(f"**Numero Chiave:** {v['numero_chiave']}") 
                    st.info(f"📍 **Zona Attuale:** {v['zona_attuale']}") 
                
                with st.expander("📜 Visualizza Storico Movimenti"): 
                    log = supabase.table("log_movimenti").select("*").eq("targa", v["targa"]).order("created_at", desc=True).execute() 
                    if log.data: 
                        df_log = pd.DataFrame(log.data) 
                        df_log["Ora"] = pd.to_datetime(df_log["created_at"]).dt.tz_convert("Europe/Rome").dt.strftime("%d/%m/%Y %H:%M") 
                        
                        def estrai_nota(d):
                            if d and "Nota:" in d:
                                return d.split("Nota:", 1)[1].strip()
                            return ""
                        
                        df_log["Nota"] = df_log["dettaglio"].apply(estrai_nota)
                        st.dataframe(df_log[["Ora", "azione", "utente", "dettaglio", "Nota"]], use_container_width=True) 
                    else: st.info("Nessuno storico disponibile") 
                st.markdown("---") 
                col_a, col_b, col_c = st.columns(3) 
                abilita_spost = col_a.checkbox("🔄 Spostamento", key="chk_spost", on_change=cb_spost) 
                abilita_mod = col_b.checkbox("✏️ Modifica", key="chk_mod", on_change=cb_mod) 
                abilita_consegna = col_c.checkbox("🔴 Consegna", key="chk_cons", on_change=cb_cons) 
                if st.session_state["azione_attiva"] == "spost": 
                    if not st.session_state.camera_attiva: st.warning("📷 Per spostare la vettura devi **attivare lo Scanner QR** dalla sidebar") 
                    else: 
                        st.markdown("**📝 Note attuali:**") 
                        st.info(v["note"] if v["note"] else "Nessuna nota presente") 
                        nota_spost = st.text_area("Nota per lo spostamento (opzionale)", key=f"nota_sp_{v['targa']}") 
                        foto = st.camera_input("📷 Scanner QR Zona Destinazione", key=f"cam_sp_{v['targa']}") 
                        if foto: 
                            z_id = leggi_qr_zona(foto) 
                            if z_id: 
                                st.success(f"🎯 Zona rilevata: **{ZONE_INFO[z_id]}**") 
                                if st.button(f"➡️ SPOSTA IN {ZONE_INFO[z_id]}", use_container_width=True): 
                                    nuova_nota = v["note"] or "" 
                                    if nota_spost: nuova_nota = f"{nuova_nota}\n[{datetime.now().strftime('%d/%m %H:%M')}] {nota_spost}" 
                                    supabase.table("parco_usato").update({"zona_id": z_id, "zona_attuale": ZONE_INFO[z_id], "note": nuova_nota}).eq("targa", v['targa']).execute() 
                                    
                                    registra_log(v["targa"], "Spostamento", f"In {ZONE_INFO[z_id]} | Nota: {nota_spost.strip()}" if nota_spost.strip() else f"In {ZONE_INFO[z_id]}", utente_attivo) 
                                    
                                    st.session_state["post_azione_msg"] = f"✅ Vettura spostata correttamente in **{ZONE_INFO[z_id]}**" 
                                    reset_azione() 
                                    st.rerun() 
                            else: st.error("❌ QR non valido") 
                elif st.session_state["azione_attiva"] == "mod": 
                    with st.form("f_mod_v"): 
                        nota_mod = st.text_area("Note", v["note"])
                        upd = { 
                            "marca_modello": st.text_input("Marca / Modello", v["marca_modello"]).upper(), 
                            "colore": st.text_input("Colore", v["colore"]).capitalize(), 
                            "km": st.number_input("KM", value=int(v['km'])), 
                            "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])), 
                            "note": nota_mod 
                        } 
                        if st.form_submit_button("💾 SALVA MODIFICHE"): 
                            if int(upd["numero_chiave"]) > 0 and int(upd["numero_chiave"]) != v["numero_chiave"]:
                                check_k = supabase.table("parco_usato").select("targa").eq("numero_chiave", int(upd["numero_chiave"])).eq("stato", "PRESENTE").limit(1).execute()
                                if check_k.data: st.error(f"La chiave {upd['numero_chiave']} è già occupata"); st.stop()

                            supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute() 
                            
                            diff = descrivi_modifiche(v, upd)
                            if diff and nota_mod.strip():
                                dettaglio = f"Modificati: {diff} | Nota: {nota_mod.strip()}"
                            elif diff:
                                dettaglio = f"Modificati: {diff}"
                            elif nota_mod.strip():
                                dettaglio = f"Correzione dati | Nota: {nota_mod.strip()}"
                            else:
                                dettaglio = "Correzione dati"

                            registra_log(v["targa"], "Modifica", dettaglio, utente_attivo) 
                            st.session_state["post_azione_msg"] = f"✅ Dati della vettura {v['targa']} aggiornati correttamente" 
                            reset_azione() 
                            st.rerun() 
                elif st.session_state["azione_attiva"] == "cons": 
                    if not st.session_state.can_consegna: st.error("🔒 Non sei autorizzato alla CONSEGNA") 
                    else: 
                        st.warning("⚠️ ATTENZIONE: la consegna è DEFINITIVA") 
                        conferma = st.checkbox(f"Confermo la CONSEGNA DEFINITIVA della vettura {v['targa']}", key=f"conf_f_{v['targa']}") 
                        if st.button("🔴 ESEGUI CONSEGNA", disabled=not conferma, use_container_width=True): 
                            supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", v['targa']).execute() 
                            registra_log(v["targa"], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo) 
                            st.session_state["post_azione_msg"] = f"✅ Vettura {v['targa']} CONSEGNATA correttamente" 
                            reset_azione() 
                            st.rerun() 

    # --- 11. DASHBOARD GENERALE --- 
    elif scelta == "📊 Dashboard Generale": 
        st.subheader("📊 Dashboard Generale") 
        c1, c2 = st.columns(2) 
        with c1: periodo_dash = st.selectbox("📅 Periodo", ["Oggi", "Ieri", "Ultimi 7 giorni", "Ultimi 30 giorni"], key="dash_period") 
        res_ut = supabase.table("utenti").select("nome").eq("attivo", True).order("nome").execute() 
        lista_operatori = ["Tutti"] + [u["nome"] for u in res_ut.data] if res_ut.data else ["Tutti"] 
        with c2: operatore_sel = st.selectbox("👤 Operatore", lista_operatori, key="dash_op") 
        now = datetime.now(timezone.utc) 
        if periodo_dash == "Oggi": data_inizio = now.replace(hour=0, minute=0, second=0, microsecond=0); data_fine = None 
        elif periodo_dash == "Ieri": data_fine = now.replace(hour=0, minute=0, second=0, microsecond=0); data_inizio = data_fine - timedelta(days=1) 
        elif periodo_dash == "Ultimi 7 giorni": data_inizio = now - timedelta(days=7); data_fine = None 
        else: data_inizio = now - timedelta(days=30); data_fine = None 
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
            st.dataframe(df[["targa", "marca_modello", "colore", "zona_attuale", "numero_chiave", "note"]], use_container_width=True) 
            out = BytesIO() 
            with pd.ExcelWriter(out, engine="xlsxwriter") as writer: df.to_excel(writer, index=False, sheet_name="Piazzale") 
            st.download_button("📥 SCARICA EXCEL", out.getvalue(), "Piazzale.xlsx", use_container_width=True) 

    # --- 13. VERIFICA ZONE --- 
    elif scelta == "📋 Verifica Zone": 
        st.subheader("📋 Analisi per Zona") 
        z_v = st.selectbox("Scegli Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}") 
        res = supabase.table("parco_usato").select("targa, marca_modello, colore").eq("zona_id", z_v).eq("stato", "PRESENTE").execute() 
        totale_zona = len(res.data) if res.data else 0 
        st.metric(label=f"🚗 Totale vetture in {ZONE_INFO[z_v]}", value=totale_zona) 
        if res.data: st.dataframe(pd.DataFrame(res.data), use_container_width=True) 
        else: st.warning("Zona vuota") 

    # --- 14. SEZIONE LOG (GENERALE) --- 
    elif scelta == "📜 Log": 
        st.subheader("📜 Registro Movimenti") 
        res = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(500).execute() 
        if res.data: 
            df = pd.DataFrame(res.data) 
            df["Ora"] = pd.to_datetime(df["created_at"]).dt.tz_convert("Europe/Rome").dt.strftime("%d/%m/%Y %H:%M:%S") 
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
        if st.session_state["ruolo"] != "admin": st.error("Accesso non autorizzato"); st.stop() 
        res_all = supabase.table("utenti").select("*").order("nome").execute() 
        if res_all.data: 
            df_ut = pd.DataFrame(res_all.data) 
            st.dataframe(df_ut[["nome", "ruolo", "attivo", "can_consegna"]], use_container_width=True) 
        col_ut1, col_ut2 = st.columns(2) 
        with col_ut1: 
            with st.form("add_user"): 
                st.markdown("### ➕ Aggiungi Nuovo") 
                n = st.text_input("Nome e Cognome") 
                p = st.text_input("PIN", type="password") 
                r = st.selectbox("Ruolo", ["operatore", "admin"]) 
                c_cons = st.checkbox("Autorizzato alla CONSEGNA") 
                if st.form_submit_button("CREA UTENTE"): 
                    if n and p: 
                        supabase.table("utenti").insert({"nome": n, "pin": p, "ruolo": r, "attivo": True, "can_consegna": c_cons}).execute() 
                        st.success(f"✅ Creato"); time.sleep(1); st.rerun() 
        with col_ut2: 
            if res_all.data: 
                st.markdown("### ✏️ Modifica / Disattiva") 
                u_sel_nome = st.selectbox("Seleziona utente", [u["nome"] for u in res_all.data]) 
                ut_data = next(u for u in res_all.data if u["nome"] == u_sel_nome) 
                with st.form("edit_user"): 
                    new_pin = st.text_input("Nuovo PIN (vuoto per non cambiare)", type="password") 
                    new_ruolo = st.selectbox("Ruolo", ["operatore", "admin"], index=0 if ut_data["ruolo"] == "operatore" else 1) 
                    new_can_cons = st.checkbox("Autorizzato alla CONSEGNA", value=ut_data.get("can_consegna", False)) 
                    new_attivo = st.checkbox("Utente Attivo", value=ut_data["attivo"]) 
                    if st.form_submit_button("SALVA MODIFICHE"): 
                        upd = {"ruolo": new_ruolo, "can_consegna": new_can_cons, "attivo": new_attivo} 
                        if new_pin: upd["pin"] = new_pin 
                        supabase.table("utenti").update(upd).eq("nome", u_sel_nome).execute() 
                        if u_sel_nome == st.session_state['user_autenticato']: st.session_state['can_consegna'] = new_can_cons 
                        st.success("✅ Aggiornato"); time.sleep(1); st.rerun()
