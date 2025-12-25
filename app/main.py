import streamlit as st
import psutil
import time
import requests
import socket
import pandas as pd

# --- Logic Functions ---

def load_css(theme_mode):
    """
    Reads style.css and replaces placeholders based on the selected theme.
    """
    if theme_mode == 'red':
        accent = "#ef4444"  # Red
        bg_color = "#1a0505" # Dark Reddish Tint
        card_bg = "#2a1010"
    else:
        accent = "#10b981"  # Green
        bg_color = "#1e1e1e" # Dark Grey
        card_bg = "#1a1a1a"

    try:
        with open("app/style.css") as f:
            css_template = f.read()
    except FileNotFoundError:
        try:
            with open("style.css") as f:
                css_template = f.read()
        except:
            return

    css = css_template.replace("{{ACCENT_COLOR}}", accent)\
                      .replace("{{BG_COLOR}}", bg_color)\
                      .replace("{{CARD_BG}}", card_bg)

    st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)

def get_weather():
    """Fetches current weather for Laval, Quebec."""
    try:
        # Laval coordinates: 45.57, -73.75
        url = "https://api.open-meteo.com/v1/forecast?latitude=45.57&longitude=-73.75&current_weather=true"
        response = requests.get(url, timeout=2)
        if response.status_code == 200:
            data = response.json().get("current_weather", {})
            temp = data.get("temperature")
            # Simple WMO code mapping
            code = data.get("weathercode")
            condition = "Unknown"
            if code == 0: condition = "Clear"
            elif 1 <= code <= 3: condition = "Partly Cloudy"
            elif code in [45, 48]: condition = "Fog"
            elif 51 <= code <= 67: condition = "Rain"
            elif 71 <= code <= 77: condition = "Snow"
            elif code >= 95: condition = "Thunderstorm"

            return temp, condition
    except:
        pass
    return None, "N/A"

def get_network_speed():
    """Calculates upload/download speed based on delta since last call."""
    counters = psutil.net_io_counters()
    now = time.time()

    if 'net_last_counters' not in st.session_state:
        st.session_state['net_last_counters'] = counters
        st.session_state['net_last_time'] = now
        return 0.0, 0.0 # First run, no delta

    last_counters = st.session_state['net_last_counters']
    last_time = st.session_state['net_last_time']

    delta_time = now - last_time
    if delta_time <= 0: return 0.0, 0.0 # Avoid div by zero

    bytes_recv = counters.bytes_recv - last_counters.bytes_recv
    bytes_sent = counters.bytes_sent - last_counters.bytes_sent

    # Update state
    st.session_state['net_last_counters'] = counters
    st.session_state['net_last_time'] = now

    # Convert to KB/s
    down_speed = (bytes_recv / 1024) / delta_time
    up_speed = (bytes_sent / 1024) / delta_time

    return round(down_speed, 1), round(up_speed, 1)

def check_connectivity(host, port):
    """Checks TCP connectivity to a host:port."""
    try:
        # Use a short timeout for responsiveness
        sock = socket.create_connection((host, port), timeout=1)
        sock.close()
        return True
    except:
        return False

def get_top_hogs():
    """Returns a DataFrame of top 5 memory hogs."""
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
        try:
            pinfo = proc.info
            processes.append(pinfo)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    df = pd.DataFrame(processes)
    if not df.empty:
        df = df.sort_values(by='memory_percent', ascending=False).head(5)
        df['memory_percent'] = df['memory_percent'].apply(lambda x: f"{x:.1f}%")
        # Clean columns
        df = df[['name', 'pid', 'memory_percent']]
        df.columns = ["Process", "PID", "Memory %"]
        return df
    return pd.DataFrame()

# --- UI Layout ---

@st.fragment(run_every=2)
def display_dashboard():
    # --- Row 1: System Health (Existing) ---
    st.header("System Health")
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.metric("CPU", f"{cpu}%")
            st.progress(cpu / 100)
    with c2:
        with st.container(border=True):
            st.metric("RAM", f"{ram}%")
            st.progress(ram / 100)
    with c3:
        with st.container(border=True):
            st.metric("Disk", f"{disk}%")
            st.progress(disk / 100)

    st.markdown("---")

    # --- Row 2: Uplink & Ping ---
    col_uplink, col_ping = st.columns(2)

    # Uplink Monitor
    down, up = get_network_speed()
    with col_uplink:
        st.subheader("Uplink Monitor")
        with st.container(border=True):
            uc1, uc2 = st.columns(2)
            uc1.metric("Download", f"{down} KB/s")
            uc2.metric("Upload", f"{up} KB/s")

    # Ping Radar
    google_ok = check_connectivity("8.8.8.8", 53)
    # Using github.com:443 for second check
    github_ok = check_connectivity("github.com", 443)

    with col_ping:
        st.subheader("Ping Radar")
        with st.container(border=True):
            pc1, pc2 = st.columns(2)
            pc1.metric("Google DNS", "ONLINE" if google_ok else "OFFLINE")
            pc2.metric("GitHub", "ONLINE" if github_ok else "OFFLINE")

    st.markdown("---")

    # --- Row 3: Top Hogs ---
    st.subheader("Top Hogs")
    df_hogs = get_top_hogs()
    st.dataframe(df_hogs, use_container_width=True, hide_index=True)


def main():
    st.set_page_config(page_title="Basement HQ", layout="wide")

    # Initialize session state for theme
    if "theme" not in st.session_state:
        st.session_state.theme = "green"

    # --- Top Bar: Weather & Toggle ---
    top_col1, top_col2 = st.columns([3, 1])

    with top_col1:
        temp, condition = get_weather()
        if temp is None:
            st.metric("Laval, QC", "N/A")
        else:
            st.metric(f"Laval, QC: {condition}", f"{temp}°C")

    with top_col2:
        # Theme Switcher
        # We use a unique key to update session state automatically or handle it manually.
        # Here we manually check value to set state.
        current_val = (st.session_state.theme == "red")
        red_alert = st.toggle("Red Alert Mode", value=current_val)

        if red_alert:
            st.session_state.theme = "red"
        else:
            st.session_state.theme = "green"

    # Load CSS dynamically based on state
    load_css(st.session_state.theme)

    st.title("BASEMENT HQ")
    st.markdown("---")

    # Main Dashboard Logic (Auto-Refreshes)
    display_dashboard()

if __name__ == "__main__":
    main()
