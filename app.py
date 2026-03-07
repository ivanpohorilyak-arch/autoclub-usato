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
from streamlit_autorefresh import st_autorefresh

# =========================================================
# CONFIG SESSIONE
# =========================================================
SESSION_DEFAULTS = {
    "user_autenticato": None,
    "ruolo": None,
    "can_consegna": False,
    "last_action": None,
    "zona_id": "",
    "zona_nome": "",
    "camera_attiva": False,
    "ingresso_salvato": False,
    "form_ingresso_ver": 0,
    "valore_chiave_proposta": 0,
    "ricerca_attiva": False,
    "ricerca_risultati": [],
    "vettura_selezionata": None,
    "azione_attiva": None,
    "post_azione_msg": None,
    "chk_spost": False,
    "chk_mod": False,
    "chk_cons": False,
    "qr_scansionato_ingresso": False,
    "ultima_zona_scansionata": "",
    "menu_mobile": "➕ Ingresso",
}

for key, default_value in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

if st.session_state["last_action"] is None:
    st.session_state["last_action"] = datetime.now(timezone.utc)

# Pulizia cache all'avvio
st.cache_data.clear()
st.cache_resource.clear()

# =========================================================
# CONFIG BASE
# =========================================================
ZONE_INFO = {
    "Z01": "Deposito N.9",
    "Z02": "Deposito N.7",
    "Z03": "Deposito N.6 (Lavaggisti)",
    "Z04": "Deposito unificato 1 e 2",
    "Z05": "Showroom",
    "Z06": "Vetture vendute",
    "Z07": "Piazzale Lavaggio",
    "Z08": "Commercianti senza telo",
    "Z09": "Commercianti con telo",
    "Z10": "Lavorazioni esterni",
    "Z11": "Verso altre sedi",
    "Z12": "Deposito N.10",
    "Z13": "Deposito N.8",
    "Z14": "Esterno (Con o Senza telo Motorsclub)"
}

TIMEOUT_MINUTI = 20

st.set_page_config(
    page_title="Autoclub Usato 1.1",
    page_icon="🚗",
    layout="wide"
)

# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
.stApp {
    background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
}

.block-container {
    max-width: 1450px;
    padding-top: 0.9rem;
    padding-bottom: 1.5rem;
}

h1, h2, h3 {
    color: #0f172a !important;
    letter-spacing: -0.2px;
}
h1 { font-weight: 800 !important; }
h2, h3 { font-weight: 700 !important; }

.card-ui {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 16px 18px;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
    margin-bottom: 14px;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
    border-right: 1px solid rgba(255,255,255,0.06);
}
section[data-testid="stSidebar"] * {
    color: #ffffff !important;
}
section[data-testid="stSidebar"] hr {
    background: rgba(255,255,255,0.18) !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: linear-gradient(135deg, #f97316 0%, #ea580c 100%) !important;
    color: white !important;
    border: none !important;
    box-shadow: 0 6px 14px rgba(249, 115, 22, 0.28) !important;
}

.stButton > button,
.stDownloadButton > button,
div[data-testid="stFormSubmitButton"] > button {
    border-radius: 14px !important;
    border: 0 !important;
    min-height: 44px !important;
    font-weight: 700 !important;
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
    color: #ffffff !important;
    box-shadow: 0 6px 14px rgba(37, 99, 235, 0.24);
    transition: all 0.18s ease-in-out;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
div[data-testid="stFormSubmitButton"] > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 18px rgba(37, 99, 235, 0.28);
}

.stTextInput > div > div,
.stNumberInput > div > div,
.stTextArea textarea,
div[data-baseweb="select"] > div,
.stDateInput > div > div {
    border-radius: 12px !important;
    border: 1px solid #cbd5e1 !important;
    background: #ffffff !important;
}

.stTextInput > div > div:focus-within,
.stNumberInput > div > div:focus-within,
.stTextArea textarea:focus,
div[data-baseweb="select"] > div:focus-within,
.stDateInput > div > div:focus-within {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.12) !important;
}

form {
    background: rgba(255,255,255,0.96);
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 18px;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04);
}

button[data-baseweb="tab"] {
    border-radius: 12px 12px 0 0 !important;
    font-weight: 700 !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    background: #eff6ff !important;
    color: #1d4ed8 !important;
}

div[data-testid="metric-container"] {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 16px;
    box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
}
div[data-testid="metric-container"] label {
    font-weight: 700 !important;
    color: #334155 !important;
}
div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
    color: #0f172a !important;
    font-weight: 800 !important;
}

div[data-testid="stAlert"] {
    border-radius: 14px !important;
    border: 1px solid rgba(0,0,0,0.06) !important;
}

details {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 8px 12px;
}

div[data-testid="stDataFrame"] {
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    overflow: hidden;
    background: white;
}

hr {
    border: none;
    height: 1px;
    background: linear-gradient(90deg, transparent, #cbd5e1, transparent);
    margin: 1rem 0 1.2rem 0;
}

.stCheckbox {
    padding-top: 4px;
    padding-bottom: 4px;
}

@media (max-width: 768px) {
    .block-container {
        padding-top: 0.7rem !important;
        padding-left: 0.7rem !important;
        padding-right: 0.7rem !important;
    }

    .card-ui {
        border-radius: 16px !important;
        padding: 14px !important;
        margin-bottom: 12px !important;
    }

    h1, h2, h3 {
        line-height: 1.15 !important;
    }

    div[data-testid="metric-container"] {
        padding: 12px !important;
        border-radius: 14px !important;
    }

    form {
        padding: 14px !important;
        border-radius: 16px !important;
    }

    .stButton > button,
    .stDownloadButton > button,
    div[data-testid="stFormSubmitButton"] > button {
        min-height: 46px !important;
        font-size: 15px !important;
    }
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<link rel="apple-touch-icon" href="https://cdn.jsdelivr.net/gh/ivanpohorilyak-arch/autoclub-usato@main/assets/icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
""", unsafe_allow_html=True)

# =========================================================
# DB
# =========================================================
supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_ANON_KEY"]
)

# =========================================================
# HELPER UI
# =========================================================
def section_title(emoji, titolo, sottotitolo=""):
    st.markdown(f"""
    <div class="card-ui">
        <div style="font-size:26px; font-weight:800; color:#0f172a;">{emoji} {titolo}</div>
        {f'<div style="color:#64748b; margin-top:4px; font-size:14px;">{sottotitolo}</div>' if sottotitolo else ''}
    </div>
    """, unsafe_allow_html=True)

def app_header(utente=None, ruolo=None):
    if utente and ruolo:
        badge_html = f"""
        <div style="
            background:#eff6ff;
            color:#1d4ed8;
            padding:8px 14px;
            border-radius:999px;
            font-weight:700;
            font-size:14px;
            white-space:nowrap;
        ">
            👤 {utente} · {ruolo}
        </div>
        """
    else:
        badge_html = ""

    st.markdown(f"""
    <div class="card-ui" style="padding:16px 20px;">
        <div style="
            display:flex;
            justify-content:space-between;
            align-items:center;
            flex-wrap:wrap;
            gap:12px;
        ">
            <div>
                <div style="font-size:30px; font-weight:800; color:#0f172a;">
                    🚗 Autoclub Usato 1.1
                </div>
                <div style="color:#475569; font-size:14px; margin-top:4px;">
                    Gestione piazzale, movimenti, chiavi e zone
                </div>
            </div>
            {badge_html}
        </div>
    </div>
    """, unsafe_allow_html=True)

def scheda_vettura_header(v):
    st.markdown(f"""
    <div class="card-ui">
        <div style="font-size:28px; font-weight:800; color:#0f172a;">🚗 {v['targa']}</div>
        <div style="color:#64748b; margin-top:4px;">Scheda vettura selezionata</div>
    </div>
    """, unsafe_allow_html=True)

def success_card_ingresso(info):
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
        border: 1px solid #86efac;
        padding: 18px;
        border-radius: 18px;
        color: #14532d;
        box-shadow: 0 6px 18px rgba(20, 83, 45, 0.08);
        margin-bottom: 14px;
    ">
        <div style="font-size:22px; font-weight:800; margin-bottom:10px;">✅ Vettura registrata correttamente</div>
        <div><b>🚗 Targa:</b> {info['targa']}</div>
        <div><b>📦 Modello:</b> {info['modello']}</div>
        <div><b>🎨 Colore:</b> {info['colore']}</div>
        <div><b>📏 Chilometri:</b> {info['km']}</div>
        <div><b>🔑 Numero chiave:</b> {info['chiave']}</div>
        <div><b>📍 Zona:</b> {info['zona']}</div>
    </div>
    """, unsafe_allow_html=True)

# =========================================================
# FUNZIONI CORE
# =========================================================
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

def login_db(nome, pin):
    try:
        res = supabase.rpc(
            "login_operatore",
            {"nome_input": nome, "pin_input": pin}
        ).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Errore login: {e}")
        return None

def get_lista_utenti_login():
    try:
        res = supabase.rpc("lista_utenti_attivi").execute()
        return [u["nome"] for u in res.data] if res.data else []
    except Exception as e:
        st.error(f"Errore recupero utenti: {e}")
        return []

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
    except:
        pass

def registra_log(targa, azione, d, u):
    try:
        n_chiave = 0
        v_info = supabase.table("parco_usato").select("numero_chiave").eq("targa", targa).limit(1).execute()
        if v_info.data:
            n_chiave = v_info.data[0]["numero_chiave"]
        supabase.table("log_movimenti").insert({
            "targa": targa,
            "azione": azione,
            "dettaglio": d,
            "utente": u,
            "numero_chiave": n_chiave,
            "created_at": datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        st.error(f"Errore Log: {e}")

def leggi_qr_zona(image_file):
    try:
        image_file.seek(0)
        file_bytes = np.asarray(bytearray(image_file.read()), dtype=np.uint8)
        img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        detector = cv2.QRCodeDetector()
        data, _, _ = detector.detectAndDecode(img)
        if not data or not data.startswith("ZONA|"):
            return None
        z_id = data.replace("ZONA|", "").strip()
        return z_id if z_id in ZONE_INFO else None
    except:
        return None

def processa_scansione_zona_auto(image_file, contesto="ingresso"):
    if not image_file:
        return None

    z_id = leggi_qr_zona(image_file)
    if not z_id:
        st.error("❌ QR non valido")
        return None

    st.session_state["zona_id"] = z_id
    st.session_state["zona_nome"] = ZONE_INFO[z_id]
    st.session_state["ultima_zona_scansionata"] = z_id

    if contesto == "ingresso":
        st.session_state["qr_scansionato_ingresso"] = True

    st.success(f"✅ Zona rilevata automaticamente: {ZONE_INFO[z_id]}")
    return z_id

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

def cb_spost():
    if st.session_state.chk_spost:
        st.session_state["azione_attiva"] = "spost"
        st.session_state["chk_mod"] = False
        st.session_state["chk_cons"] = False
    else:
        st.session_state["azione_attiva"] = None

def cb_mod():
    if st.session_state.chk_mod:
        st.session_state["azione_attiva"] = "mod"
        st.session_state["chk_spost"] = False
        st.session_state["chk_cons"] = False
    else:
        st.session_state["azione_attiva"] = None

def cb_cons():
    if st.session_state.chk_cons:
        st.session_state["azione_attiva"] = "cons"
        st.session_state["chk_spost"] = False
        st.session_state["chk_mod"] = False
    else:
        st.session_state["azione_attiva"] = None

controllo_timeout()

# =========================================================
# LOGIN
# =========================================================
if st.session_state['user_autenticato'] is None:
    app_header()

    st.markdown("""
    <div class="card-ui" style="max-width:720px; margin: 18px auto;">
        <div style="font-size:30px; font-weight:800; color:#0f172a;">🔐 Accesso</div>
        <div style="color:#64748b; margin-top:4px;">Accedi con operatore e PIN</div>
    </div>
    """, unsafe_allow_html=True)

    lista_u = get_lista_utenti_login()
    col_l, col_c, col_r = st.columns([1, 1.2, 1])

    with col_c:
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
            else:
                st.error("Accesso negato: PIN errato o utente non attivo")

# =========================================================
# APP
# =========================================================
else:
    utente_attivo = st.session_state['user_autenticato']
    app_header(utente_attivo, st.session_state['ruolo'])

    menu = [
        "➕ Ingresso",
        "🔍 Ricerca",
        "📋 Verifica Zone",
        "📊 Dashboard Zone",
        "📊 Dashboard Generale",
        "📊 Export",
        "📜 Log",
        "🖨️ Stampa QR",
        "♻️ Ripristina"
    ]
    if st.session_state["ruolo"] == "admin":
        menu.append("👥 Gestione Utenti")

    st.markdown('<div class="card-ui">', unsafe_allow_html=True)
    scelta = st.selectbox("Seleziona Funzione", menu, key="menu_mobile")
    st.markdown('</div>', unsafe_allow_html=True)

    st.session_state["pagina_attuale"] = scelta
    st.markdown("---")

    with st.sidebar:
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.10); border-radius:16px; padding:14px; margin-bottom:12px;">
            <div style="font-size:18px; font-weight:800;">👤 {utente_attivo}</div>
            <div style="font-size:13px; opacity:0.9;">Ruolo: {st.session_state['ruolo']}</div>
        </div>
        """, unsafe_allow_html=True)

        st.session_state['heartbeat'] = st_autorefresh(interval=30000, key="presence_heartbeat")
        aggiorna_presenza(utente_attivo, st.session_state["pagina_attuale"])

        st.markdown("---")
        st.markdown("### 📷 Scanner QR")
        st.checkbox("Attiva scanner", key="camera_attiva")
        if st.session_state["camera_attiva"]:
            st.caption("La lettura avviene automaticamente appena la foto viene acquisita.")

        if st.button("Log-out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    # =====================================================
    # INGRESSO
    # =====================================================
    if scelta == "➕ Ingresso":
        aggiorna_attivita()
        section_title("➕", "Registrazione Nuova Vettura", "Inserimento rapido nuova vettura in piazzale")

        if st.session_state.camera_attiva:
            foto_z = st.camera_input("Scansiona QR della Zona", key=f"cam_in_{st.session_state['form_ingresso_ver']}")
            if foto_z and not st.session_state.get("qr_scansionato_ingresso", False):
                processa_scansione_zona_auto(foto_z, "ingresso")

        if st.session_state["zona_id"]:
            st.info(f"📍 Zona attuale selezionata: **{st.session_state['zona_nome']}**")

        if st.button("🔑 TROVA NUMERO CHIAVE LIBERO (1-520)", use_container_width=True):
            st.session_state["valore_chiave_proposta"] = trova_prima_chiave_libera()
            st.rerun()

        with st.form(key=f"f_ingresso_{st.session_state['form_ingresso_ver']}"):
            if not st.session_state['zona_id']:
                st.error("❌ Scansione QR Obbligatoria per abilitare i campi")
            else:
                st.success(f"✅ Zona confermata: {st.session_state['zona_nome']}")

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

            if n_chiave > 0 and targa:
                check_preview = supabase.table("parco_usato") \
                    .select("targa") \
                    .eq("numero_chiave", int(n_chiave)) \
                    .eq("stato", "PRESENTE") \
                    .limit(1) \
                    .execute()

                if check_preview.data:
                    targa_esistente = check_preview.data[0]["targa"]
                    if targa_esistente != targa:
                        st.error(f"🚨 ATTENZIONE: la chiave {n_chiave} è già utilizzata dalla vettura {targa_esistente}")

            note = st.text_area("Note")
            submit = st.form_submit_button("REGISTRA LA VETTURA", disabled=not st.session_state['zona_id'])

            if submit:
                if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', targa):
                    st.error("Targa non valida")
                    st.stop()

                check_t = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").limit(1).execute()
                if check_t.data:
                    st.error("Targa già presente nel piazzale!")
                    st.stop()

                if n_chiave > 0:
                    check_k = supabase.table("parco_usato").select("targa").eq("numero_chiave", int(n_chiave)).eq("stato", "PRESENTE").limit(1).execute()
                    if check_k.data:
                        st.error(f"La chiave {n_chiave} è già occupata dalla vettura {check_k.data[0]['targa']}")
                        st.stop()

                payload = {
                    "targa": targa,
                    "marca_modello": f"{marca} {modello}",
                    "colore": colore,
                    "km": int(km),
                    "numero_chiave": int(n_chiave),
                    "zona_id": st.session_state["zona_id"],
                    "zona_attuale": st.session_state["zona_nome"],
                    "data_ingresso": datetime.now(timezone.utc).isoformat(),
                    "note": note,
                    "stato": "PRESENTE",
                    "utente_ultimo_invio": utente_attivo
                }

                supabase.table("parco_usato").insert(payload).execute()
                registra_log(targa, "Ingresso", f"In {st.session_state['zona_nome']}", utente_attivo)

                st.session_state["ingresso_salvato"] = {
                    "targa": targa,
                    "modello": f"{marca} {modello}",
                    "colore": colore,
                    "km": int(km),
                    "chiave": int(n_chiave),
                    "zona": st.session_state["zona_nome"]
                }
                st.session_state["valore_chiave_proposta"] = 0
                st.rerun()

        if st.session_state.get("ingresso_salvato"):
            info = st.session_state["ingresso_salvato"]
            success_card_ingresso(info)

            if st.button("🆕 NUOVA REGISTRAZIONE", use_container_width=True):
                st.session_state["ingresso_salvato"] = False
                st.session_state["zona_id"] = ""
                st.session_state["zona_nome"] = ""
                st.session_state["qr_scansionato_ingresso"] = False
                st.session_state["ultima_zona_scansionata"] = ""
                st.session_state["form_ingresso_ver"] += 1
                st.rerun()

    # =====================================================
    # RICERCA
    # =====================================================
    elif scelta == "🔍 Ricerca":
        aggiorna_attivita()
        section_title("🔍", "Ricerca Vettura", "Ricerca per targa o numero chiave")

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
            if val is None:
                st.error("Valore non valido")
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
                st.session_state["vettura_selezionata"] = st.selectbox(
                    "Seleziona vettura",
                    risultati,
                    key="sel_vettura_select",
                    format_func=lambda x: f"{x['targa']} | {x['marca_modello']} | Chiave {x['numero_chiave']}"
                )
            else:
                st.session_state["vettura_selezionata"] = risultati[0]

            v = st.session_state["vettura_selezionata"]
            if v:
                scheda_vettura_header(v)

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
                    else:
                        st.info("Nessuno storico disponibile")

                st.markdown("---")
                col_a, col_b, col_c = st.columns(3)
                col_a.checkbox("🔄 Spostamento", key="chk_spost", on_change=cb_spost)
                col_b.checkbox("✏️ Modifica", key="chk_mod", on_change=cb_mod)
                col_c.checkbox("🔴 Consegna", key="chk_cons", on_change=cb_cons)

                if st.session_state["azione_attiva"] == "spost":
                    if not st.session_state.camera_attiva:
                        st.warning("📷 Per spostare la vettura devi attivare lo scanner QR dalla sidebar")
                    else:
                        st.markdown("**📝 Note attuali:**")
                        st.info(v["note"] if v["note"] else "Nessuna nota presente")
                        nota_spost = st.text_area("Nota per lo spostamento (opzionale)", key=f"nota_sp_{v['targa']}")
                        foto = st.camera_input("📷 Scanner QR Zona Destinazione", key=f"cam_sp_{v['targa']}")
                        if foto:
                            z_id = leggi_qr_zona(foto)
                            if z_id:
                                st.success(f"🎯 Zona rilevata automaticamente: **{ZONE_INFO[z_id]}**")
                                if st.button(f"➡️ SPOSTA IN {ZONE_INFO[z_id]}", use_container_width=True):
                                    nuova_nota = v["note"] or ""
                                    if nota_spost:
                                        nuova_nota = f"{nuova_nota}\n[{datetime.now().strftime('%d/%m %H:%M')}] {nota_spost}"

                                    supabase.table("parco_usato").update({
                                        "zona_id": z_id,
                                        "zona_attuale": ZONE_INFO[z_id],
                                        "note": nuova_nota
                                    }).eq("targa", v['targa']).execute()

                                    registra_log(v["targa"], "Spostamento", f"In {ZONE_INFO[z_id]}", utente_attivo)

                                    st.session_state["post_azione_msg"] = f"✅ Vettura spostata correttamente in **{ZONE_INFO[z_id]}**"
                                    reset_azione()
                                    st.rerun()
                            else:
                                st.error("❌ QR non valido")

                elif st.session_state["azione_attiva"] == "mod":
                    with st.form("f_mod_v"):
                        nuova_targa = st.text_input("Targa", v["targa"]).upper().strip()
                        nota_mod = st.text_area("Note", v["note"])

                        upd = {
                            "targa": nuova_targa,
                            "marca_modello": st.text_input("Marca / Modello", v["marca_modello"]).upper(),
                            "colore": st.text_input("Colore", v["colore"]).capitalize(),
                            "km": st.number_input("KM", value=int(v['km'])),
                            "numero_chiave": st.number_input("Chiave", value=int(v['numero_chiave'])),
                            "note": nota_mod
                        }

                        if st.form_submit_button("💾 SALVA MODIFICHE"):
                            if not re.match(r'^[A-Z]{2}[0-9]{3}[A-Z]{2}$', nuova_targa):
                                st.error("❌ Formato targa non valido (es. AA123BB)")
                                st.stop()

                            if nuova_targa != v["targa"]:
                                check_t = supabase.table("parco_usato").select("targa").eq("targa", nuova_targa).eq("stato", "PRESENTE").limit(1).execute()
                                if check_t.data:
                                    st.error(f"❌ Errore: la targa {nuova_targa} è già presente in piazzale!")
                                    st.stop()

                            if int(upd["numero_chiave"]) > 0 and int(upd["numero_chiave"]) != v["numero_chiave"]:
                                check_k = supabase.table("parco_usato").select("targa").eq("numero_chiave", int(upd["numero_chiave"])).eq("stato", "PRESENTE").limit(1).execute()
                                if check_k.data:
                                    st.error(f"❌ Errore: la chiave {upd['numero_chiave']} è già occupata")
                                    st.stop()

                            supabase.table("parco_usato").update(upd).eq("targa", v['targa']).execute()

                            diff = descrivi_modifiche(v, upd)
                            if nuova_targa != v["targa"]:
                                diff = f"Targa ({v['targa']} → {nuova_targa}), " + diff

                            if diff and nota_mod.strip():
                                dettaglio = f"Modificati: {diff} | Nota: {nota_mod.strip()}"
                            elif diff:
                                dettaglio = f"Modificati: {diff}"
                            elif nota_mod.strip():
                                dettaglio = f"Correzione dati | Nota: {nota_mod.strip()}"
                            else:
                                dettaglio = "Correzione dati"

                            registra_log(nuova_targa, "Modifica", dettaglio, utente_attivo)

                            st.session_state["post_azione_msg"] = f"✅ Dati della vettura {nuova_targa} aggiornati correttamente"
                            reset_azione()
                            st.rerun()

                elif st.session_state["azione_attiva"] == "cons":
                    if not st.session_state.can_consegna:
                        st.error("🔒 Non sei autorizzato alla CONSEGNA")
                    else:
                        st.warning("⚠️ ATTENZIONE: la consegna è DEFINITIVA")
                        conferma = st.checkbox(f"Confermo la CONSEGNA DEFINITIVA della vettura {v['targa']}", key=f"conf_f_{v['targa']}")
                        if st.button("🔴 ESEGUI CONSEGNA", disabled=not conferma, use_container_width=True):
                            supabase.table("parco_usato").update({
                                "stato": "CONSEGNATO",
                                "numero_chiave": 0
                            }).eq("targa", v['targa']).execute()
                            registra_log(v["targa"], "Consegna", f"Uscita da {v['zona_attuale']}", utente_attivo)
                            st.session_state["post_azione_msg"] = f"✅ Vettura {v['targa']} CONSEGNATA correttamente"
                            reset_azione()
                            st.rerun()

    # =====================================================
    # DASHBOARD GENERALE
    # =====================================================
    elif scelta == "📊 Dashboard Generale":
        section_title("📊", "Dashboard Generale", "KPI, occupazione chiavi e controllo duplicati")

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
        else:
            data_inizio = now - timedelta(days=30)
            data_fine = None

        query = supabase.table("log_movimenti").select("*").gte("created_at", data_inizio.isoformat())
        if data_fine:
            query = query.lt("created_at", data_fine.isoformat())
        if operatore_sel != "Tutti":
            query = query.eq("utente", operatore_sel)

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
                    if r["azione"] == "Ingresso":
                        z_in += 1
                    elif r["azione"] == "Spostamento":
                        z_sp += 1
                    elif r["azione"] == "Consegna":
                        z_out += 1
            kpi_zona.append({
                "Zona": f"{z_id} - {z_nome}",
                "➕ Ingressi": z_in,
                "🔄 Spostamenti": z_sp,
                "🔴 Consegne": z_out
            })

        st.dataframe(pd.DataFrame(kpi_zona), use_container_width=True)

        st.markdown("---")
        st.markdown("### 🔑 Occupazione Chiavi 1–520")

        res_chiavi = supabase.table("parco_usato").select("numero_chiave").eq("stato", "PRESENTE").execute()
        chiavi_occupate = set()
        if res_chiavi.data:
            for r in res_chiavi.data:
                num = r.get("numero_chiave")
                if num and 1 <= int(num) <= 520:
                    chiavi_occupate.add(int(num))

        totali = 520
        occupate = len(chiavi_occupate)
        libere = totali - occupate
        percentuale = round((occupate / totali) * 100, 1)

        c1, c2, c3 = st.columns(3)
        c1.metric("🔒 Chiavi Occupate", occupate)
        c2.metric("🟢 Chiavi Libere", libere)
        c3.metric("📊 Percentuale Occupazione", f"{percentuale}%")

        st.progress(percentuale / 100)

        st.markdown("---")
        st.markdown("### ⚠️ Controllo Chiavi Duplicate")

        res_dup = supabase.table("parco_usato").select("numero_chiave, targa").eq("stato", "PRESENTE").execute()
        chiavi = {}
        duplicati = []

        if res_dup.data:
            for r in res_dup.data:
                num = r.get("numero_chiave")
                if num and int(num) > 0:
                    num = int(num)
                    if num not in chiavi:
                        chiavi[num] = [r["targa"]]
                    else:
                        chiavi[num].append(r["targa"])

        for k, v_list in chiavi.items():
            if len(v_list) > 1:
                duplicati.append((k, v_list))

        if duplicati:
            st.error("❌ ATTENZIONE: Sono presenti chiavi duplicate nel sistema!")
            df_dup = [{"Numero Chiave": d[0], "Targhe Coinvolte": ", ".join(d[1])} for d in duplicati]
            st.dataframe(pd.DataFrame(df_dup), use_container_width=True)
        else:
            st.success("✅ Nessuna chiave duplicata rilevata")

    # =====================================================
    # EXPORT
    # =====================================================
    elif scelta == "📊 Export":
        section_title("📊", "Export Piazzale", "Esportazione elenco vetture presenti")

        zone_export = ["Tutte le zone"] + list(ZONE_INFO.keys())
        zona_sel = st.selectbox("📍 Zona", zone_export, format_func=lambda x: x if x == "Tutte le zone" else f"{x} - {ZONE_INFO[x]}")
        query = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE")
        if zona_sel != "Tutte le zone":
            query = query.eq("zona_id", zona_sel)

        res = query.execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.dataframe(df[["targa", "marca_modello", "colore", "zona_attuale", "numero_chiave", "note"]], use_container_width=True)

            out = BytesIO()
            with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Piazzale")

            st.download_button("📥 SCARICA EXCEL", out.getvalue(), "Piazzale.xlsx", use_container_width=True)

    # =====================================================
    # VERIFICA ZONE
    # =====================================================
    elif scelta == "📋 Verifica Zone":
        section_title("📋", "Analisi per Zona", "Verifica vetture presenti nella zona selezionata")

        z_v = st.selectbox("Scegli Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("parco_usato").select("targa, marca_modello, colore").eq("zona_id", z_v).eq("stato", "PRESENTE").execute()
        totale_zona = len(res.data) if res.data else 0
        st.metric(label=f"🚗 Totale vetture in {ZONE_INFO[z_v]}", value=totale_zona)

        if res.data:
            st.dataframe(pd.DataFrame(res.data), use_container_width=True)
        else:
            st.warning("Zona vuota")

    # =====================================================
    # LOG
    # =====================================================
    elif scelta == "📜 Log":
        section_title("📜", "Registro Movimenti", "Ultimi 500 movimenti registrati")

        res = supabase.table("log_movimenti").select("*").order("created_at", desc=True).limit(500).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            df["Ora"] = pd.to_datetime(df["created_at"]).dt.tz_convert("Europe/Rome").dt.strftime("%d/%m/%Y %H:%M:%S")
            st.dataframe(df[["Ora", "targa", "azione", "utente", "dettaglio"]], use_container_width=True)

    # =====================================================
    # STAMPA QR
    # =====================================================
    elif scelta == "🖨️ Stampa QR":
        section_title("🖨️", "Generatore QR Zone", "Creazione QR per identificazione rapida delle zone")

        z_qr = st.selectbox("Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        qr_obj = qrcode.make(f"ZONA|{z_qr}")
        buf = BytesIO()
        qr_obj.save(buf, format="PNG")
        st.image(buf.getvalue(), width=250)
        st.download_button("DOWNLOAD QR", buf.getvalue(), f"QR_{z_qr}.png")

    # =====================================================
    # RIPRISTINA
    # =====================================================
    elif scelta == "♻️ Ripristina":
        section_title("♻️", "Ripristino", "Riporta una vettura consegnata nello stock")

        t_r = st.text_input("Targa Consegnata").upper().strip()
        if t_r and st.button(f"RIPRISTINA {t_r}"):
            supabase.table("parco_usato").update({"stato": "PRESENTE"}).eq("targa", t_r).execute()
            registra_log(t_r, "Ripristino", "Riportata in stock", utente_attivo)
            st.success("✅ Ripristinata")
            time.sleep(1)
            st.rerun()

    # =====================================================
    # DASHBOARD ZONE
    # =====================================================
    elif scelta == "📊 Dashboard Zone":
        section_title("📍", "Storico Zona", "Ultimi movimenti collegati alla zona selezionata")

        z_sel = st.selectbox("Zona", list(ZONE_INFO.keys()), format_func=lambda x: f"{x} - {ZONE_INFO[x]}")
        res = supabase.table("log_movimenti").select("*").ilike("dettaglio", f"%{ZONE_INFO[z_sel]}%").limit(50).execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data)[["targa", "azione", "utente"]], use_container_width=True)

    # =====================================================
    # GESTIONE UTENTI
    # =====================================================
    elif scelta == "👥 Gestione Utenti":
        section_title("👥", "Gestione Utenti", "Creazione, modifica ed eliminazione utenti")
        if st.session_state["ruolo"] != "admin":
            st.error("Accesso negato")
            st.stop()

        utente_loggato = st.session_state["user_autenticato"]
        res_all = supabase.table("utenti").select("*").order("nome").execute()
        utenti = res_all.data if res_all.data else []
        admin_attivi = [u for u in utenti if u["ruolo"] == "admin" and u["attivo"]]

        tab1, tab2 = st.tabs(["➕ Aggiungi Nuovo", "✏️ Modifica / Elimina"])

        with tab1:
            with st.form("add_user"):
                n = st.text_input("Nome e Cognome")
                p = st.text_input("PIN", type="password")
                r = st.selectbox("Ruolo", ["operatore", "admin"])
                c_cons = st.checkbox("Autorizzato alla CONSEGNA")
                if st.form_submit_button("CREA UTENTE"):
                    if n and p:
                        supabase.table("utenti").insert({
                            "nome": n,
                            "pin": p,
                            "ruolo": r,
                            "attivo": True,
                            "can_consegna": c_cons
                        }).execute()
                        st.success("✅ Utente creato")
                        time.sleep(1)
                        st.rerun()

        with tab2:
            if utenti:
                u_sel_nome = st.selectbox("Seleziona utente", [u["nome"] for u in utenti])
                ut_data = next(u for u in utenti if u["nome"] == u_sel_nome)

                with st.form("edit_user"):
                    new_pin = st.text_input("Nuovo PIN (vuoto per non cambiare)", type="password")
                    new_ruolo = st.selectbox("Ruolo", ["operatore", "admin"], index=0 if ut_data["ruolo"] == "operatore" else 1)
                    new_can_cons = st.checkbox("Autorizzato alla CONSEGNA", value=ut_data.get("can_consegna", False))
                    new_attivo = st.checkbox("Utente Attivo", value=ut_data["attivo"])

                    c1, c2 = st.columns(2)
                    salva = c1.form_submit_button("💾 SALVA")
                    elimina = c2.form_submit_button("🗑 ELIMINA")

                    if salva:
                        if u_sel_nome == utente_loggato and not new_attivo:
                            st.error("Non puoi disattivarti")
                            st.stop()

                        if ut_data["ruolo"] == "admin" and (new_ruolo != "admin" or not new_attivo) and len(admin_attivi) <= 1:
                            st.error("Deve esserci almeno un admin attivo")
                            st.stop()

                        upd_u = {
                            "ruolo": new_ruolo,
                            "can_consegna": new_can_cons,
                            "attivo": new_attivo
                        }
                        if new_pin:
                            upd_u["pin"] = new_pin

                        supabase.table("utenti").update(upd_u).eq("nome", u_sel_nome).execute()
                        st.success("Aggiornato")
                        time.sleep(1)
                        st.rerun()

                    if elimina:
                        if u_sel_nome == utente_loggato:
                            st.error("Non puoi eliminarti")
                            st.stop()
                        if ut_data["ruolo"] == "admin" and len(admin_attivi) <= 1:
                            st.error("Impossibile eliminare l'ultimo admin")
                            st.stop()

                        supabase.table("utenti").delete().eq("nome", u_sel_nome).execute()
                        st.success("Eliminato")
                        time.sleep(1)
                        st.rerun()
