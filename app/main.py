import streamlit as st
import psutil
import time
import requests
import pandas as pd
import socket
import os
from dotenv import load_dotenv

# --- 1. CONFIGURATION & STATE ---
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
    lines = []
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            lines = f.readlines()
    
    key_found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            key_found = True
        else:
            new_lines.append(line)
    
    if not key_found:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}={value}\n")
    
    with open(".env", "w") as f:
        f.writelines(new_lines)
    os.environ[key] = value

def inject_custom_css():
    css_file = "app/style.css"
    if not os.path.exists(css_file):
        css_file = "style.css"
    
    with open(css_file) as f:
        style_content = f.read()

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
    lat = os.getenv("OPEN_METEO_LAT", "45.57")
    lon = os.getenv("OPEN_METEO_LONG", "-73.75")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        response = requests.get(url, timeout=2)
        data = response.json()
        temp = data['current_weather']['temperature']
        code = data['current_weather']['weathercode']
        condition = "Clear"
        if code > 3: condition = "Cloudy"
        if code > 50: condition = "Rainy"
        if code > 70: condition = "Snow"
        return temp, condition
    except:
        return "N/A", "Offline"

def get_jellyfin_stats():
    base_url = os.getenv("JELLYFIN_URL", "http://192.168.0.200:8096")
    api_key = os.getenv("JELLYFIN_API_KEY", "")
    
    if not api_key:
        return 0, "No Key"
    
    headers = {"X-Emby-Token": api_key}
    try:
        # Get Sessions to see who is active
        url = f"{base_url}/Sessions"
        r = requests.get(url, headers=headers, timeout=2)
        if r.status_code == 200:
            sessions = r.json()
            return len(sessions), "Online"
        else:
            return 0, "Error"
    except:
        return 0, "Offline"

def check_ping(host):
    try:
        sock = socket.create_connection((host, 80), timeout=1)
        sock.close()
        return True
    except:
        return False

def get_top_hogs():
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
@st.fragment(run_every=2)
def render_dashboard():
    
    # ROW 1: HEADER
    c1, c2 = st.columns([3, 1])
    with c1: st.title("BASEMENT HQ // COMMAND")
    with c2:
        if st.toggle("🚨 RED ALERT", value=st.session_state.red_alert):
            if not st.session_state.red_alert:
                st.session_state.red_alert = True
                st.rerun()
        else:
            if st.session_state.red_alert:
                st.session_state.red_alert = False
                st.rerun()

    st.markdown("---")

    # ROW 2: ENVIRONMENT
    col_w, col_c, col_r, col_d = st.columns(4)
    temp, cond = get_weather()
    with col_w:
        with st.container(border=True): st.metric("Weather", f"{temp}°C", cond)
    
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent
    
    with col_c:
        with st.container(border=True):
            st.metric("CPU", f"{cpu}%")
            st.progress(cpu/100)
    with col_r:
        with st.container(border=True):
            st.metric("RAM", f"{ram}%")
            st.progress(ram/100)
    with col_d:
        with st.container(border=True):
            st.metric("Disk", f"{disk}%")
            st.progress(disk/100)

    # ROW 3: NETWORK & MEDIA
    st.subheader("Network & Media")
    net_col, ping_col, media_col = st.columns([2, 1, 1])

    # Network
    now = time.time()
    current_io = psutil.net_io_counters()
    dt = now - st.session_state.net_last_time
    if dt < 0.1: dt = 0.1
    rx = (current_io.bytes_recv - st.session_state.net_last_io.bytes_recv) / dt
    tx = (current_io.bytes_sent - st.session_state.net_last_io.bytes_sent) / dt
    st.session_state.net_last_time = now
    st.session_state.net_last_io = current_io
    
    with net_col:
        with st.container(border=True):
            nc1, nc2 = st.columns(2)
            nc1.metric("Download", f"{rx/1024/1024:.2f} MB/s")
            nc2.metric("Upload", f"{tx/1024/1024:.2f} MB/s")

    # Ping
    g_up = check_ping("google.com")
    gh_up = check_ping("github.com")
    with ping_col:
        with st.container(border=True):
            st.markdown(f"**Google:** {'🟢' if g_up else '🔴'}")
            st.markdown(f"**GitHub:** {'🟢' if gh_up else '🔴'}")

    # Jellyfin Widget
    jf_active, jf_status = get_jellyfin_stats()
    with media_col:
        with st.container(border=True):
            st.metric("Jellyfin", jf_status)
            if jf_status == "Online":
                st.caption(f"{jf_active} Active Streams")

    # ROW 4: HOGS
    st.subheader("System Processes")
    df_hogs = get_top_hogs()
    st.dataframe(df_hogs, hide_index=True, use_container_width=True)

# --- 4. ADMIN PANEL ---
def render_admin_panel():
    with st.expander("⚙️ System Configuration (Secure Vault)"):
        st.write("Update Secrets. Saves to `.env`.")
        
        # Load Defaults
        c_lat = os.getenv("OPEN_METEO_LAT", "45.57")
        c_lon = os.getenv("OPEN_METEO_LONG", "-73.75")
        c_jf_url = os.getenv("JELLYFIN_URL", "http://192.168.0.200:8096")
        c_jf_key = os.getenv("JELLYFIN_API_KEY", "")
        c_ad_user = os.getenv("ADGUARD_USERNAME", "")
        
        with st.form("secrets"):
            c1, c2 = st.columns(2)
            n_lat = c1.text_input("Lat", c_lat)
            n_lon = c2.text_input("Lon", c_lon)
            
            n_url = st.text_input("Jellyfin URL", c_jf_url)
            n_key = st.text_input("Jellyfin API Key", c_jf_key, type="password")
            n_ad = st.text_input("AdGuard User", c_ad_user)
            
            if st.form_submit_button("💾 Save"):
                save_secrets("OPEN_METEO_LAT", n_lat)
                save_secrets("OPEN_METEO_LONG", n_lon)
                save_secrets("JELLYFIN_URL", n_url)
                save_secrets("JELLYFIN_API_KEY", n_key)
                save_secrets("ADGUARD_USERNAME", n_ad)
                st.success("Saved! Reloading...")
                time.sleep(1)
                st.rerun()

if __name__ == "__main__":
    inject_custom_css()
    render_dashboard()
    render_admin_panel()