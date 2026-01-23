import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO
import re

# --- CONFIGURAZIONE DATABASE (Inserisci i tuoi dati) ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- CONFIGURAZIONE ZONE E CAPACITÀ ---
ZONE_INFO = {
    "Deposito N.9": 100, "Deposito N.7": 100, "Deposito N.6 (Lavaggisti)": 100, 
    "Deposito unificato 1 e 2": 100, "Showroom": 100, "A Vetture vendute": 100, 
    "B Lavaggio Esterno": 100, "C Commercianti senza telo": 100, 
    "D Commercianti con telo": 100, "E lavorazioni esterni": 100, "F verso altri sedi": 100
}
UTENTI = ["Luca", "Ivan"]

st.set_page_config(page_title="AUTOCLUB CENTER DATA", layout="centered")

# --- FUNZIONI DI SUPPORTO ---
def valida_targa(targa):
    pattern = re.compile(r"^[A-Z]{2}\d{3}[A-Z]{2}$|^[A-Z]{2}\d{4}$") # Standard IT o Prova
    return pattern.match(targa)

def registra_log(targa, azione, dettaglio, utente):
    supabase.table("log_movimenti").insert({
        "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente
    }).execute()

def get_colori():
    res = supabase.table("parco_usato").select("colore").execute()
    colori = list(set([str(r['colore']).capitalize() for r in res.data if r['colore']]))
    return colori if colori else ["Bianco", "Nero", "Grigio"]

# --- INTERFACCIA ---
st.title("🚗 AUTOCLUB CENTER DATA USATO 1.1")
utente_attivo = st.sidebar.selectbox("Operatore:", UTENTI)
menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export & Log"]
scelta = st.sidebar.radio("Menu", menu)

# --- 1. INGRESSO CON AUTO-APPRENDIMENTO COLORI ---
if scelta == "➕ Ingresso":
    st.subheader("Nuovo Arrivo")
    with st.form("form_ingresso", clear_on_submit=True):
        targa = st.text_input("TARGA (Standard IT)").upper().strip()
        modello = st.text_input("Marca e Modello")
        
        colore_sugg = get_colori()
        colore = st.selectbox("Colore (Auto-apprendimento)", ["Altro..."] + colore_sugg)
        if colore == "Altro...":
            colore = st.text_input("Specifica nuovo colore")
            
        km = st.number_input("Chilometri", min_value=0)
        n_chiave = st.number_input("N° Chiave (0=Commerciante)", min_value=0)
        zona = st.selectbox("Zona iniziale", list(ZONE_INFO.keys()))
        note = st.text_area("Note")

        if st.form_submit_button("REGISTRA"):
            if not valida_targa(targa):
                st.error("Formato targa non valido!")
            else:
                # Blocco duplicati
                check = supabase.table("parco_usato").select("targa").eq("targa", targa).eq("stato", "PRESENTE").execute()
                if check.data:
                    st.error(f"Errore: La targa {targa} è già presente nel piazzale!")
                else:
                    data = {
                        "targa": targa, "marca_modello": modello, "colore": colore,
                        "km": km, "numero_chiave": n_chiave, "zona_attuale": zona, 
                        "note": note, "utente_ultimo_invio": utente_attivo, "stato": "PRESENTE"
                    }
                    supabase.table("parco_usato").insert(data).execute()
                    registra_log(targa, "Ingresso", f"Inserita in {zona} con chiave {n_chiave}", utente_attivo)
                    st.success(f"Vettura {targa} registrata!")

# --- 2. RICERCA SMART (TARGA O CHIAVE) ---
elif scelta == "🔍 Ricerca/Sposta":
    st.subheader("Ricerca Vettura")
    criterio = st.radio("Cerca per:", ["Targa", "Numero Chiave"], horizontal=True)
    query = st.text_input(f"Inserisci {criterio}")

    if query:
        col_cerca = "targa" if criterio == "Targa" else "numero_chiave"
        res = supabase.table("parco_usato").select("*").eq(col_cerca, query.upper()).eq("stato", "PRESENTE").execute()
        
        if res.data:
            for v in res.data:
                st.info(f"📍 **{v['marca_modello']}** | Chiave: {v['numero_chiave']} | Zona: {v['zona_attuale']}")
                nuova_zona = st.selectbox(f"Sposta {v['targa']} in:", list(ZONE_INFO.keys()), key=v['targa'])
                if st.button(f"Aggiorna Posizione {v['targa']}"):
                    supabase.table("parco_usato").update({"zona_attuale": nuova_zona}).eq("targa", v['targa']).execute()
                    registra_log(v['targa'], "Spostamento", f"Spostata in {nuova_zona}", utente_attivo)
                    st.success("Posizione aggiornata!")
        else:
            st.error("Nessuna vettura trovata.")

# --- 3. VERIFICA ZONE E CAPACITÀ ---
elif scelta == "📋 Verifica Zone":
    z_sel = st.selectbox("Seleziona Zona", list(ZONE_INFO.keys()))
    res = supabase.table("parco_usato").select("*").eq("zona_attuale", z_sel).eq("stato", "PRESENTE").execute()
    
    occupati = len(res.data)
    totali = ZONE_INFO[z_sel]
    liberi = totali - occupati
    
    st.metric(label=f"Stato {z_sel}", value=f"{occupati} / {totali}", delta=f"{liberi} posti liberi")
    
    if res.data:
        df = pd.DataFrame(res.data)[["targa", "marca_modello", "numero_chiave", "data_ingresso"]]
        df['data_ingresso'] = pd.to_datetime(df['data_ingresso']).dt.strftime('%d/%m/%Y %H:%M')
        st.dataframe(df, use_container_width=True)

# --- 4. EXPORT EXCEL CON AUTO-ADATTAMENTO ---
elif scelta == "📊 Export & Log":
    st.subheader("Esportazione Dati")
    res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
    
    if res.data:
        df_ex = pd.DataFrame(res.data).drop(columns=['stato'], errors='ignore')
        df_ex['data_ingresso'] = pd.to_datetime(df_ex['data_ingresso']).dt.strftime('%d/%m/%Y %H:%M')
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_ex.to_excel(writer, index=False, sheet_name='Piazzale')
            worksheet = writer.sheets['Piazzale']
            for i, col in enumerate(df_ex.columns):
                column_len = max(df_ex[col].astype(str).str.len().max(), len(col)) + 2
                worksheet.set_column(i, i, column_len)
        
        st.download_button("📥 Scarica Excel Parco Usato AC", output.getvalue(), "Parco_Usato_AC.xlsx")
