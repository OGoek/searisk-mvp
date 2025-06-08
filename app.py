import streamlit as st

st.set_page_config(page_title="SeaRisk AI MVP", page_icon="🌊")

st.title("🌊 SeaRisk AI – Containerverlust Risiko-Score")

st.markdown("""
Dieses MVP schätzt das Risiko eines Containerverlusts auf Basis von:
- Start-/Zielhafen
- Monat der Überfahrt
- Schiffstyp
""")

# Eingabeformular
with st.form("risk_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("Start-Hafen", value="Rotterdam")
    with col2:
        destination = st.text_input("Ziel-Hafen", value="New York")

    month = st.selectbox("Monat der Fahrt", [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ])

    ship_type = st.selectbox("Schiffstyp", [
        "Feeder (<3.000 TEU)", "Panamax (4.000–5.000 TEU)",
        "Post-Panamax (6.000–10.000 TEU)", "Ultra Large (>14.000 TEU)"
    ])

    submit = st.form_submit_button("Risiko berechnen")

# Risikologik (Dummy-Modell)
if submit:
    risk_score = 10  # Grundwert

    if "atlant" in (origin + destination).lower():
        risk_score += 20

    if month in ["November", "Dezember", "Januar", "Februar"]:
        risk_score += 30

    if "Feeder" in ship_type:
        risk_score += 15
    elif "Ultra" in ship_type:
        risk_score += 10

    st.subheader(f"📊 Risikowert: {risk_score} von 100")

    if risk_score >= 60:
        st.error("⚠️ Hohes Risiko: Containerverlust möglich. Verstärkte Sicherung empfohlen.")
    elif risk_score >= 30:
        st.warning("🟠 Moderates Risiko. Routenbedingungen prüfen.")
    else:
        st.success("✅ Geringes Risiko. Bedingungen stabil.")

    st.caption("Hinweis: Dies ist eine vereinfachte MVP-Schätzung.")
