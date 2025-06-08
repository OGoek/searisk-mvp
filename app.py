import streamlit as st
import pandas as pd
import pydeck as pdk

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
        risk_score += 25
    elif "Panamax" in ship_type:
        risk_score += 15
    elif "Post" in ship_type:
        risk_score += 10
    elif "Ultra" in ship_type:
        risk_score += 5

    # Streckenlänge grob schätzen (nur als Platzhalter)
    if len(origin) + len(destination) > 20:
        risk_score += 10

    # Risiko auf Skala von 0–100 beschränken
    risk_score = min(risk_score, 100)

    st.subheader(f"📊 Risikowert: {risk_score} von 100")

    if risk_score >= 70:
        st.error("⚠️ Sehr hohes Risiko: Containerverlust sehr wahrscheinlich.")
    elif risk_score >= 40:
        st.warning("🟠 Mittleres Risiko: Vorsichtsmaßnahmen empfohlen.")
    else:
        st.success("✅ Geringes Risiko. Route gilt als stabil.")

    st.caption("Hinweis: Risikomodell basiert auf vereinfachten Annahmen zu Saison, Region und Schiffstyp.")

    # Dummy-Koordinaten für ausgewählte Häfen
    ports = {
        "Rotterdam": [4.47917, 51.9225],
        "New York": [-74.006, 40.7128],
        "Genua": [8.9463, 44.4056],
        "Alexandria": [29.9187, 31.2001],
        "Shanghai": [121.4737, 31.2304],
        "Singapur": [103.8198, 1.3521]
    }

    origin_coords = ports.get(origin, [0, 0])
    dest_coords = ports.get(destination, [0, 0])

    st.subheader("🗺️ Routenkarte")

    route_data = pd.DataFrame({
        'from_lon': [origin_coords[0]],
        'from_lat': [origin_coords[1]],
        'to_lon': [dest_coords[0]],
        'to_lat': [dest_coords[1]]
    })

    layer = pdk.Layer(
        "LineLayer",
        route_data,
        get_source_position='[from_lon, from_lat]',
        get_target_position='[to_lon, to_lat]',
        get_width=4,
        get_color=[255, 100, 100],
        pickable=True
    )

    view_state = pdk.ViewState(
        longitude=(origin_coords[0] + dest_coords[0]) / 2,
        latitude=(origin_coords[1] + dest_coords[1]) / 2,
        zoom=2,
        pitch=0
    )

    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": f"{origin} → {destination}"}
    ))
