import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
from datetime import datetime, timedelta

# === SETTINGS ===
st.set_page_config(page_title="SeaRisk AI", page_icon="🚢")

# === HEADLINE ===
st.title("🌊 SeaRisk AI – Maritime Risikobewertung mit Echtzeit-Wetterdaten")

# === INPUT FORM ===
with st.form("input_form"):
    col1, col2 = st.columns(2)
    with col1:
        origin = st.text_input("Start-Hafen", "Rotterdam")
    with col2:
        destination = st.text_input("Ziel-Hafen", "New York")
    
    col3, col4 = st.columns(2)
    with col3:
        vessel_type = st.selectbox("Schiffstyp", ["Containerschiff", "Tanker", "Fähre", "Fischkutter"])
    with col4:
        start_date = st.date_input("Startdatum", datetime.today())
    
    submitted = st.form_submit_button("Risiko berechnen")

# === DUMMY-COORDINATES FÜR HÄFEN ===
port_coords = {
    "Rotterdam": [51.9225, 4.47917],
    "New York": [40.7128, -74.0060]
}

# === API-KEYS ===
stormglass_api_key = "52eefa2a-4468-11f0-b16b-0242ac130006-52eefa98-4468-11f0-b16b-0242ac130006"
noaa_token = "QWTcLJKbRevQchwfIcdKlAdpSJAbxTgg"
metno_headers = {"User-Agent": "SeaRiskAI/you@example.com"}
# === HELPER FUNCTIONS ===
def get_stormglass_forecast(lat, lon):
    end = datetime.utcnow() + timedelta(days=7)
    start = datetime.utcnow()
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
    forecast = []
    for hour in data.get("hours", [])[:7*24:24]:  # alle 24h
        try:
            forecast.append({
                "time": hour["time"],
                "wave": hour["waveHeight"]["noaa"],
                "wind": hour["windSpeed"]["noaa"]
            })
        except:
            continue
    return forecast

def get_metno_forecast(lat, lon):
    url = f"https://api.met.no/weatherapi/oceanforecast/2.0/complete?lat={lat}&lon={lon}"
    response = requests.get(url, headers=metno_headers)
    forecast = []
    try:
        timeseries = response.json()["properties"]["timeseries"]
        for t in timeseries[:7*24:24]:
            details = t["data"]["instant"]["details"]
            forecast.append({
                "time": t["time"],
                "wave": details.get("significantWaveHeight", 0),
                "wind": details.get("windSpeed", 0)
            })
    except:
        pass
    return forecast

def get_noaa_station(lat, lon):
    url = f"https://www.ncei.noaa.gov/cdo-web/api/v2/stations?extent={lat-0.1},{lon-0.1},{lat+0.1},{lon+0.1}"
    headers = {"token": noaa_token}
    try:
        response = requests.get(url, headers=headers)
        stations = response.json().get("results", [])
        return stations[0]["name"] if stations else "Keine Station gefunden"
    except:
        return "Fehler bei NOAA"

def compute_risk(wave, wind, vessel_type):
    risk = 0
    if wave > 4:
        risk += 40
    elif wave > 2:
        risk += 20
    else:
        risk += 5

    if wind > 15:
        risk += 40
    elif wind > 8:
        risk += 20
    else:
        risk += 5

    if vessel_type in ["Fischkutter", "Fähre"]:
        risk += 10  # kleinere Schiffe = höheres Risiko

    return min(risk, 100)
# === MAIN LOGIC ===
if submitted:
    if origin not in port_coords or destination not in port_coords:
        st.error("Bitte gültige Häfen eingeben.")
    else:
        st.subheader("📍 Hafenpositionen")
        origin_lat, origin_lon = port_coords[origin]
        dest_lat, dest_lon = port_coords[destination]
        st.write(f"**{origin}** → ({origin_lat}, {origin_lon})")
        st.write(f"**{destination}** → ({dest_lat}, {dest_lon})")

        # NOAA-Station anzeigen
        noaa_station = get_noaa_station(origin_lat, origin_lon)
        st.info(f"📡 Nächste NOAA-Station: {noaa_station}")

        # Wetterdaten abrufen
        sg_data = get_stormglass_forecast(origin_lat, origin_lon)
        met_data = get_metno_forecast(origin_lat, origin_lon)

        # Kombinieren + Risikobewertung
        combined = []
        for i in range(min(len(sg_data), len(met_data))):
            avg_wave = (sg_data[i]["wave"] + met_data[i]["wave"]) / 2
            avg_wind = (sg_data[i]["wind"] + met_data[i]["wind"]) / 2
            risk = compute_risk(avg_wave, avg_wind, vessel_type)
            combined.append({
                "Datum": sg_data[i]["time"][:10],
                "Wellenhöhe (m)": round(avg_wave, 2),
                "Windgeschw. (m/s)": round(avg_wind, 2),
                "Risikowert": risk
            })

        df = pd.DataFrame(combined)
        st.subheader("📊 7-Tage Risikoanalyse")
        st.dataframe(df)

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
            get_color=[200, 30, 0]
        )

        view_state = pdk.ViewState(
            longitude=(origin_lon + dest_lon)/2,
            latitude=(origin_lat + dest_lat)/2,
            zoom=2
        )

        st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
