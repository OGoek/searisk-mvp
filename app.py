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
    # Basis-Risiko
    risk_score = 0

    # Saisonrisiko
    winter_months = ["November", "Dezember", "Januar", "Februar"]
    if month in winter_months:
        risk_score += 30
    elif month in ["März", "April", "Oktober"]:
        risk_score += 15
    else:
        risk_score += 5

    # Route/Region (nur grob geschätzt anhand von Hafen-Namen)
    route = (origin + destination).lower()
    if any(sea in route for sea in ["atlant", "north", "kanada", "new york", "rotterdam"]):
        risk_score += 30
    elif any(sea in route for sea in ["mittelmeer", "mediterr", "istanbul", "genua"]):
        risk_score += 10
    else:
        risk_score += 15

    # Schiffstyp-Risiko
    if "Feeder" in ship_type:
        risk_score += 20
    elif "Panamax" in ship_type:
        risk_score += 10
    elif "Ultra" in ship_type:
        risk_score += 5

    # Streckenlänge (grob geschätzt)
    if len(origin) + len(destination) > 20:
        risk_score += 10  # lange Route

    # Cap bei 100
    risk_score = min(risk_sco
