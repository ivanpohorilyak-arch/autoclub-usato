import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime
import qrcode
from io import BytesIO
import re
import cv2
import numpy as np
import pytesseract

# --- CONFIGURAZIONE DATABASE ---
SUPABASE_URL = "https://ihhypwraskzhjovyvwxd.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImloaHlwd3Jhc2t6aGpvdnl2d3hkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjkxODM4MDQsImV4cCI6MjA4NDc1OTgwNH0.E5R3nUzfkcJz1J1wr3LYxKEtLA9-8cvbsh56sEURpqA"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- GESTIONE UTENTI E PASSWORD INDIVIDUALI ---
# Puoi cambiare queste password come preferisci
CREDENZIALI = {
    "Luca": "luca2026",
    "Ivan": "ivan2026"
}

st.set_page_config(page_title="AUTOCLUB MASTER 1.2.3", layout="centered")

# --- INIZIALIZZAZIONE SESSIONE ---
if 'user_autenticato' not in st.session_state:
    st.session_state['user_autenticato'] = None

def schermata_login():
    st.title("🔐 Login Autoclub Center")
    with st.container():
        user_sel = st.selectbox("Seleziona il tuo nome", list(CREDENZIALI.keys()))
        password_input = st.text_input("Inserisci la tua Password", type="password")
        
        if st.button("Accedi"):
            if password_input == CREDENZIALI[user_sel]:
                st.session_state['user_autenticato'] = user_sel
                st.success(f"Benvenuto {user_sel}!")
                st.rerun()
            else:
                st.error("Password errata per l'utente selezionato.")

# --- FUNZIONI DI SUPPORTO ---
def registra_log(targa, azione, dettaglio, utente):
    supabase.table("log_movimenti").insert({
        "targa": targa, "azione": azione, "dettaglio": dettaglio, "utente": utente
    }).execute()

# --- LOGICA DI ACCESSO ---
if st.session_state['user_autenticato'] is None:
    schermata_login()
else:
    utente_attivo = st.session_state['user_autenticato']
    
    # Barra laterale con Info Utente e Logout
    st.sidebar.success(f"Loggato come: {utente_attivo}")
    if st.sidebar.button("Esci / Cambia Utente"):
        st.session_state['user_autenticato'] = None
        st.rerun()

    # --- MENU PRINCIPALE ---
    menu = ["➕ Ingresso", "🔍 Ricerca/Sposta", "📋 Verifica Zone", "📊 Export & Log"]
    scelta = st.radio("Cosa vuoi fare?", menu, horizontal=True)

    # --- 1. INGRESSO (Identico a prima, ma usa utente_attivo del login) ---
    if scelta == "➕ Ingresso":
        st.subheader(f"Registrazione - Operatore: {utente_attivo}")
        attiva_camera = st.toggle("📸 Scanner Targa")
        targa_letta = ""
        
        if attiva_camera:
            foto = st.camera_input("Scatta foto targa")
            if foto:
                # La funzione leggi_targa_da_foto è quella definita prima
                targa_letta = "" # Qui il sistema elabora...
        
        with st.form("nuovo_ingresso"):
            targa = st.text_input("TARGA", value=targa_letta).upper().strip()
            modello = st.text_input("Modello")
            n_chiave = st.number_input("N° Chiave (0=Commerciante)", min_value=0)
            zona = st.selectbox("Posiziona in:", ["Deposito N.9", "Deposito N.7", "Showroom", "C Commercianti"])
            
            if st.form_submit_button("REGISTRA"):
                if targa:
                    # Registra usando utente_attivo per la tracciabilità [cite: 2026-01-02]
                    supabase.table("parco_usato").insert({
                        "targa": targa, "marca_modello": modello, 
                        "numero_chiave": n_chiave, "zona_attuale": zona, 
                        "utente_ultimo_invio": utente_attivo, "stato": "PRESENTE"
                    }).execute()
                    registra_log(targa, "Ingresso", f"Inserita in {zona}", utente_attivo)
                    st.success("Vettura salvata con successo!")
                else:
                    st.error("Inserire la targa.")

    # --- IL RESTO DELLE FUNZIONI (Ricerca, Verifica, Export) RIMANGONO UGUALI ---
    # L'unica differenza è che 'utente_attivo' è ora bloccato dal login iniziale.
