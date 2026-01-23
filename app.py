import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO

# --- CONFIGURAZIONE DATABASE (Inserisci i tuoi dati presi da Supabase) ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- LISTE DEFINITE ---
ZONE = [
    "Deposito N.9", "Deposito N.7", "Deposito N.6 (Lavaggisti)", 
    "Deposito unificato 1 e 2", "Showroom", "A Vetture vendute", 
    "B Lavaggio Esterno", "C Commercianti senza telo", 
    "D Commercianti con telo", "E lavorazioni esterni", "F verso altri sedi"
]
UTENTI = ["Luca", "Ivan", "Marco", "Matteo", "Admin"]

st.set_page_config(page_title="AUTOCLUB CENTER DATA", layout="centered")

st.title("🚗 AUTOCLUB CENTER - MOBILE")
utente_attivo = st.sidebar.selectbox("Operatore:", UTENTI)

menu = ["➕ Nuova Entrata", "🔄 Sposta/Modifica", "📋 Verifica Zona", "🖨️ Stampa QR", "📊 Esporta Excel"]
scelta = st.sidebar.radio("Menu", menu)

# --- FUNZIONE LOG ---
def registra_log(targa, azione, dettaglio):
    supabase.table("log_movimenti").insert({
        "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente_attivo
    }).execute()

# --- 1. NUOVA ENTRATA ---
if scelta == "➕ Nuova Entrata":
    with st.form("form_ingresso"):
        targa = st.text_input("TARGA").upper().strip()
        modello = st.text_input("Marca e Modello")
        colore = st.text_input("Colore")
        km = st.number_input("Chilometri", min_value=0)
        n_chiave = st.number_input("N° Chiave (0 = Commerciante)", min_value=0)
        zona = st.selectbox("Zona iniziale", ZONE)
        note = st.text_area("Note Urgenti")
        
        if n_chiave == 0: st.warning("⚠️ CHIAVE 0: Destinata a COMMERCIANTI")

        if st.form_submit_button("REGISTRA"):
            if targa and modello:
                data = {
                    "targa": targa, "marca_modello": modello, "colore": colore,
                    "km": km, "numero_chiave": n_chiave, "zona_attuale": zona, "note": note,
                    "utente_ultimo_invio": utente_attivo, "stato": "PRESENTE"
                }
                supabase.table("parco_usato").upsert(data).execute()
                registra_log(targa, "Inserimento", f"Ingresso in {zona}")
                st.success("Vettura Registrata!")
            else: st.error("Inserisci Targa e Modello")

# --- 2. SPOSTA/MODIFICA ---
elif scelta == "🔄 Sposta/Modifica":
    cerca = st.text_input("Cerca Targa").upper()
    if cerca:
        res = supabase.table("parco_usato").select("*").eq("targa", cerca).execute()
        if res.data:
            v = res.data[0]
            st.write(f"**{v['marca_modello']}** | Zona: **{v['zona_attuale']}**")
            nuova_zona = st.selectbox("Nuova Posizione (o scansiona QR)", ZONE)
            if st.button("CONFERMA SPOSTAMENTO"):
                supabase.table("parco_usato").update({"zona_attuale": nuova_zona}).eq("targa", cerca).execute()
                registra_log(cerca, "Spostamento", f"Spostata in {nuova_zona}")
                st.success("Posizione Aggiornata!")
            
            if st.button("🔴 CONSEGNA AL CLIENTE"):
                supabase.table("parco_usato").update({"stato": "CONSEGNATO"}).eq("targa", cerca).execute()
                registra_log(cerca, "Consegna", "Uscita definitiva")
                st.success("Consegnata!")

# --- 3. VERIFICA ZONA ---
elif scelta == "📋 Verifica Zona":
    z = st.selectbox("Seleziona Zona", ZONE)
    res = supabase.table("parco_usato").select("*").eq("zona_attuale", z).eq("stato", "PRESENTE").execute()
    if res.data:
        df = pd.DataFrame(res.data)
        st.write(f"Auto in questa zona: {len(df)}")
        st.dataframe(df[["targa", "marca_modello", "numero_chiave", "note"]])
    else: st.write("Zona vuota")

# --- 4. STAMPA QR ---
elif scelta == "🖨️ Stampa QR":
    z_qr = st.selectbox("Scegli zona", ZONE)
    qr_img = qrcode.make(z_qr)
    buf = BytesIO()
    qr_img.save(buf, format="PNG")
    st.image(buf.getvalue(), caption=f"QR {z_qr}")
    st.download_button("Scarica per Plastificazione", buf.getvalue(), f"QR_{z_qr}.png")

# --- 5. ESPORTA EXCEL ---
elif scelta == "📊 Esporta Excel":
    res = supabase.table("parco_usato").select("*").eq("stato", "PRESENTE").execute()
    if res.data:
        df_excel = pd.DataFrame(res.data)
        # Rimuoviamo colonne tecniche per l'export
        df_excel = df_excel.drop(columns=['stato'], errors='ignore')
        
        # Generazione file Excel in memoria
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_excel.to_excel(writer, index=False, sheet_name='Parco Usato AC')
        
        st.download_button(
            label="📥 SCARICA EXCEL AGGIORNATO (Parco Usato AC)",
            data=output.getvalue(),
            file_name=f"Parco_Usato_AC_{datetime.now().strftime('%d_%m_%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
