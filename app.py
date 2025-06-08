# Kompletter Streamlit-Code mit Integration von Stormglass.io, NOAA und Met.no
# Nutzt Dummy-Koordinaten (Rotterdam → New York) und holt Meereswetterdaten von 3 APIs
# Du musst ggf. dein requirements.txt um folgende Einträge ergänzen: streamlit, requests, pandas, pydeck

import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timedelta

st.set_page_config(page_title="SeaRisk AI – mit Echtdaten", page_icon="🌊")

st.title("🌊 SeaRisk AI – Risikobewertung mit Echtzeit-Wetterdaten")

# Eingabe
with st.form("form"):
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("Start-Hafen", "Rotterdam")
    with col2:
        destination = st.text_input("Ziel-Hafen", "New York")
    submitted = st.form_submit_button("Risiko berechnen")

# Dummy-Koordinaten für Start/Ziel
port_coords = {
    "Rotterdam": [51.9225, 4.47917],
    "New York": [40.7128, -74.0060]
}

# API KEYS
stormglass_api_key = "52eefa2a-4468-11f0-b16b-0242ac130006-52eefa98-4468-11f0-b16b-0242ac130006"
noaa_token = "QWTcLJKbRevQchwfIcdKlAdpSJAbxTgg"
metno_headers = {"User-Agent": "SeaRiskAI/you@example.com"}

def get_stormglass_data(lat, lon):
    end = datetime.utcnow()
    start = end - timedelta(hours=6)
    url = f"https://api.stormglass.io/v2/weather/point"
    params = {
        'lat': lat,
        'lng': lon,
        'params': ','.join(['waveHeight', 'windSpeed']),
        'start': int(start.timestamp()),
        'end': int(end.timestamp())
    }
    headers = {'Authorization': stormglass_api_key}
    response = requests.get(url, params=params, headers=headers)
    data = response.json()
    try:
        waves = data['hours'][0]['waveHeight']['noaa']
        wind = data['hours'][0]['windSpeed']['noaa']
        return {"wave_height": waves, "wind_speed": wind}
    except:
        return None

def get_metno_data(lat, lon):
    url = f"https://api.met.no/weatherapi/oceanforecast/2.0/complete?lat={lat}&lon={lon}"
    response = requests.get(url, headers=metno_headers)
    try:
        json_data = response.json()
        latest = json_data["properties"]["timeseries"][0]["data"]["instant"]["details"]
        return {
            "wave_height": latest.get("significantWaveHeight", 0),
            "wind_speed": latest.get("windSpeed", 0)
        }
    except:
        return None

def get_noaa_data(lat, lon):
    url = f"https://www.ncei.noaa.gov/cdo-web/api/v2/stations?extent={lat-0.1},{lon-0.1},{lat+0.1},{lon+0.1}"
    headers = {"token": noaa_token}
    try:
        response = requests.get(url, headers=headers)
        stations = response.json().get("results", [])
        if stations:
            return {"station_found": True, "station_name": stations[0]["name"]}
        else:
            return {"station_found": False}
    except:
        return {"station_found": False}

if submitted:
    if origin not in port_coords or destination not in port_coords:
        st.error("Bitte gültige Häfen eingeben (z. B. Rotterdam, New York).")
    else:
        st.subheader("📡 Echtdaten-Abfrage")

        origin_lat, origin_lon = port_coords[origin]
        dest_lat, dest_lon = port_coords[destination]

        st.write(f"📍 {origin}: {origin_lat}, {origin_lon}")
        st.write(f"📍 {destination}: {dest_lat}, {dest_lon}")

        # Stormglass Daten
        sg_origin = get_stormglass_data(origin_lat, origin_lon)
        sg_dest = get_stormglass_data(dest_lat, dest_lon)

        # Met.no Daten
        met_origin = get_metno_data(origin_lat, origin_lon)
        met_dest = get_metno_data(dest_lat, dest_lon)

        # NOAA Info
        noaa_check = get_noaa_data(origin_lat, origin_lon)

        # Anzeigen
        st.markdown("### 🌊 Wellen- und Wetterdaten")
        st.write("#### Stormglass (Start)")
        st.json(sg_origin)
        st.write("#### Met.no (Ziel)")
        st.json(met_dest)
        st.write("#### NOAA Station in der Nähe:")
        st.write(noaa_check.get("station_name", "Keine gefunden"))

        # Risiko berechnen (sehr grob)
        avg_wave = (sg_origin["wave_height"] + met_dest["wave_height"]) / 2 if sg_origin and met_dest else 0
        avg_wind = (sg_origin["wind_speed"] + met_dest["wind_speed"]) / 2 if sg_origin and met_dest else 0

        risk = 0
        if avg_wave > 4:
            risk += 40
        elif avg_wave > 2:
            risk += 20
        else:
            risk += 5

        if avg_wind > 15:
            risk += 40
        elif avg_wind > 8:
            risk += 20
        else:
            risk += 5

        risk = min(risk, 100)

        st.subheader(f"📊 Risikowert: {risk} von 100")
        if risk >= 70:
            st.error("⚠️ Sehr hohes Risiko")
        elif risk >= 40:
            st.warning("🟠 Mittleres Risiko")
        else:
            st.success("✅ Geringes Risiko")

        # Karte
        st.subheader("🗺️ Routenkarte")
        route_df = pd.DataFrame({
            'from_lon': [origin_lon],
            'from_lat': [origin_lat],
            'to_lon': [dest_lon],
            'to_lat': [dest_lat]
        })

        layer = pdk.Layer(
            "LineLayer",
            route_df,
            get_source_position='[from_lon, from_lat]',
            get_target_position='[to_lon, to_lat]',
            get_width=4,
            get_color=[0, 128, 200]
        )

        view_state = pdk.ViewState(
            longitude=(origin_lon + dest_lon)/2,
            latitude=(origin_lat + dest_lat)/2,
            zoom=2
        )

        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))

