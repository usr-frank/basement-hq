import streamlit as st
import psutil
import time
import requests
import pandas as pd
import socket
import os
from dotenv import load_dotenv

# --- 1. CONFIGURATION & STATE ---
# Load secrets from .env file
load_dotenv()

st.set_page_config(page_title="Basement HQ", layout="wide")

if 'red_alert' not in st.session_state:
    st.session_state.red_alert = False

# For Network Speed Calculation
if 'net_last_time' not in st.session_state:
    st.session_state.net_last_time = time.time()
    st.session_state.net_last_io = psutil.net_io_counters()

# --- 2. HELPER FUNCTIONS ---

def save_secrets(key, value):
    """Simple helper to write a secret to .env file"""
    # Read existing lines
    lines = []
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            lines = f.readlines()
    
    # Check if key exists and update it
    key_found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            key_found = True
        else:
            new_lines.append(line)
    
    # If not found, append it
    if not key_found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}={value}\n")
    
    # Write back
    with open(".env", "w") as f:
        f.writelines(new_lines)
    
    # Reload environment immediately for this session
    os.environ[key] = value

def inject_custom_css():
    # Load the CSS file content
    css_file = "app/style.css"
    if not os.path.exists(css_file):
        css_file = "style.css" # Fallback
    
    with open(css_file) as f:
        style_content = f.read()

    # If Red Alert is Active, inject red variables
    if st.session_state.red_alert:
        theme_override = """
        :root {
            --primary-color: #ef4444 !important;
            --bg-color: #2b0a0a !important;
            --card-bg: #450a0a !important;
        }
        """
        st.markdown(f'<style>{style_content}\n{theme_override}</style>', unsafe_allow_html=True)
    else:
        st.markdown(f'<style>{style_content}</style>', unsafe_allow_html=True)

def get_weather():
    # Try to get coordinates from Secrets, default to Laval
    lat = os.getenv("OPEN_METEO_LAT", "45.57")
    lon = os.getenv("OPEN_METEO_LONG", "-73.75")
    
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    
    try:
        response = requests.get(url, timeout=2)
        data = response.json()
        temp = data['current_weather']['temperature']
        code = data['current_weather']['weathercode']
        # Simple code map
        condition = "Clear"
        if code > 3: condition = "Cloudy"
        if code > 50: condition = "Rainy"
        if code > 70: condition = "Snow"
        
        return temp, condition
    except:
        return "N/A", "Offline"

def check_ping(host):
    # Pure Python Ping (Socket Connect)
    try:
        sock = socket.create_connection((host, 80), timeout=1)
        sock.close()
        return True
    except:
        return False

def get_top_hogs():
    # Get top 5 processes by Memory
    processes = []
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    df = pd.DataFrame(processes)
    if not df.empty:
        df = df.sort_values(by='memory_percent', ascending=False).head(5)
        df['memory_percent'] = df['memory_percent'].apply(lambda x: f"{x:.1f}%")
        return df[['name', 'pid', 'memory_percent']]
    return pd.DataFrame()

# --- 3. MAIN DASHBOARD ---

# Auto-refresh every 2 seconds
@st.fragment(run_every=2)
def render_dashboard():
    
    # -- ROW 1: HEADER & ALERTS --
    c1, c2 = st.columns([3, 1])
    with c1:
        st.title("BASEMENT HQ // COMMAND")
    with c2:
        # Red Alert Toggle
        mode = st.toggle("🚨 RED ALERT", value=st.session_state.red_alert)
        if mode != st.session_state.red_alert:
            st.session_state.red_alert = mode
            st.rerun()

    st.markdown("---")

    # -- ROW 2: ENVIRONMENT & HEALTH --
    col_weather, col_cpu, col_ram, col_disk = st.columns(4)

    # Weather
    temp, cond = get_weather()
    with col_weather:
        with st.container(border=True):
            st.metric("Weather", f"{temp}°C", cond)

    # System Stats
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

    with col_cpu:
        with st.container(border=True):
            st.metric("CPU Load", f"{cpu}%")
            st.progress(cpu / 100)
    
    with col_ram:
        with st.container(border=True):
            st.metric("RAM Usage", f"{ram}%")
            st.progress(ram / 100)

    with col_disk:
        with st.container(border=True):
            st.metric("Disk Space", f"{disk}%")
            st.progress(disk / 100)

    # -- ROW 3: NETWORK & COMMS --
    st.subheader("Uplink Status")
    net_col, ping_col = st.columns([2, 1])

    # Network Speed Logic
    now = time.time()
    current_io = psutil.net_io_counters()
    
    dt = now - st.session_state.net_last_time
    if dt < 0.1: dt = 0.1 # Prevent divide by zero

    # Bytes per second
    rx_speed = (current_io.bytes_recv - st.session_state.net_last_io.bytes_recv) / dt
    tx_speed = (current_io.bytes_sent - st.session_state.net_last_io.bytes_sent) / dt

    # Update State
    st.session_state.net_last_time = now
    st.session_state.net_last_io = current_io

    with net_col:
        with st.container(border=True):
            nc1, nc2 = st.columns(2)
            nc1.metric("Download", f"{rx_speed/1024/1024:.2f} MB/s")
            nc2.metric("Upload", f"{tx_speed/1024/1024:.2f} MB/s")

    # Ping Radar
    google_up = check_ping("google.com")
    github_up = check_ping("github.com")
    
    with ping_col:
        with st.container(border=True):
            st.write("Connectivity Radar")
            st.markdown(f"**Google:** {'🟢 Online' if google_up else '🔴 Offline'}")
            st.markdown(f"**GitHub:** {'🟢 Online' if github_up else '🔴 Offline'}")

    # -- ROW 4: TOP HOGS --
    st.subheader("Process Monitor (Top Hogs)")
    df_hogs = get_top_hogs()
    st.dataframe(df_hogs, hide_index=True, use_container_width=True)

# --- 4. ADMIN PANEL (Secrets) ---
def render_admin_panel():
    with st.expander("⚙️ System Configuration (Secure Vault)"):
        st.write("Update API Keys and Settings. Changes are saved to `.env`.")
        
        # Load current values
        current_lat = os.getenv("OPEN_METEO_LAT", "45.57")
        current_lon = os.getenv("OPEN_METEO_LONG", "-73.75")
        current_jf_key = os.getenv("JELLYFIN_API_KEY", "")
        current_ad_user = os.getenv("ADGUARD_USERNAME", "")
        
        # Input Form
        with st.form("secrets_form"):
            c1, c2 = st.columns(2)
            new_lat = c1.text_input("Latitude", value=current_lat)
            new_lon = c2.text_input("Longitude", value=current_lon)
            
            new_jf = st.text_input("Jellyfin API Key", value=current_jf_key, type="password")
            new_ad = st.text_input("AdGuard Username", value=current_ad_user)
            
            submitted = st.form_submit_button("💾 Save Configuration")
            
            if submitted:
                save_secrets("OPEN_METEO_LAT", new_lat)
                save_secrets("OPEN_METEO_LONG", new_lon)
                save_secrets("JELLYFIN_API_KEY", new_jf)
                save_secrets("ADGUARD_USERNAME", new_ad)
                st.success("Configuration Saved! Reloading...")
                time.sleep(1)
                st.rerun()

# --- 5. APP ENTRY POINT ---
if __name__ == "__main__":
    inject_custom_css()
    render_dashboard()
    render_admin_panel()