import streamlit as st
import pandas as pd
from supabase import create_client


# ==========================================
# CONFIGURATIE
# ==========================================

st.set_page_config(
    page_title="Financial Cockpit",
    page_icon="💰",
    layout="wide"
)


# ==========================================
# SUPABASE
# ==========================================

try:

    supabase = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
    )

    supabase_available = True

except Exception:

    supabase_available = False


# ==========================================
# LOGIN FUNCTIES
# ==========================================

def login():

    st.title("💰 Financial Cockpit")

    st.subheader("Inloggen")

    email = st.text_input(
        "E-mailadres"
    )

    password = st.text_input(
        "Wachtwoord",
        type="password"
    )

    if st.button(
        "Inloggen",
        use_container_width=True
    ):

        try:

            response = supabase.auth.sign_in_with_password(
                {
                    "email": email,
                    "password": password
                }
            )

            if response.user:

                st.session_state["user"] = response.user

                st.success(
                    "✅ Succesvol ingelogd"
                )

                st.rerun()

        except Exception as e:

            st.error(
                f"❌ Inloggen mislukt: {e}"
            )


def register():

    st.title("💰 Financial Cockpit")

    st.subheader("Account aanmaken")

    email = st.text_input(
        "E-mailadres",
        key="register_email"
    )

    password = st.text_input(
        "Wachtwoord",
        type="password",
        key="register_password"
    )

    password_repeat = st.text_input(
        "Wachtwoord herhalen",
        type="password",
        key="register_password_repeat"
    )

    if st.button(
        "Account aanmaken",
        use_container_width=True
    ):

        if password != password_repeat:

            st.error(
                "❌ De wachtwoorden komen niet overeen."
            )

            return

        if len(password) < 8:

            st.error(
                "❌ Het wachtwoord moet minimaal 8 tekens bevatten."
            )

            return

        try:

            response = supabase.auth.sign_up(
                {
                    "email": email,
                    "password": password
                }
            )

            if response.user:

                st.success(
                    "✅ Account aangemaakt."
                )

                st.info(
                    "Controleer je e-mail om je account te bevestigen."
                )

        except Exception as e:

            st.error(
                f"❌ Account aanmaken mislukt: {e}"
            )


# ==========================================
# LOGIN / REGISTRATIE SCHERM
# ==========================================

if "user" not in st.session_state:

    tab_login, tab_register = st.tabs(
        [
            "Inloggen",
            "Account aanmaken"
        ]
    )

    with tab_login:

        login()

    with tab_register:

        register()

    st.stop()


# ==========================================
# INGelogd
# ==========================================

user = st.session_state["user"]


# ==========================================
# HEADER
# ==========================================

col1, col2 = st.columns(
    [4, 1]
)

with col1:

    st.title("💰 Financial Cockpit")

with col2:

    if st.button(
        "Uitloggen",
        use_container_width=True
    ):

        supabase.auth.sign_out()

        st.session_state.pop(
            "user",
            None
        )

        st.rerun()


st.caption(
    f"Ingelogd als {user.email}"
)


# ==========================================
# DASHBOARD PLACEHOLDER
# ==========================================

st.success(
    "🎉 Je bent succesvol ingelogd!"
)

st.markdown(
    """
    ### Volgende stap

    Hier komt je persoonlijke financiële dashboard.

    We gaan vervolgens:

    - 🏦 bankrekeningen toevoegen
    - 💳 transacties opslaan
    - 🏷️ categorieën koppelen
    - 📊 inkomsten en uitgaven analyseren
    - 🎯 budgetten toevoegen
    """
)
