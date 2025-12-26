import streamlit as st
import psutil
import time
import requests
import pandas as pd
import socket
import os
import docker
from dotenv import load_dotenv

# --- 1. CONFIGURATION & STATE ---
load_dotenv()

st.set_page_config(page_title="Basement HQ", layout="wide")

# Theme & Personalization State Defaults
if 'dashboard_theme' not in st.session_state:
    st.session_state.dashboard_theme = os.getenv("DASHBOARD_THEME", "Default")

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

    theme = st.session_state.dashboard_theme
    theme_css = ""

    if theme == "Red Alert":
        theme_css = """
        :root {
            --primary-color: #ef4444 !important;
            --bg-color: #2b0a0a !important;
            --card-bg: #450a0a !important;
        }
        """
    elif theme == "Retro (Amber)":
        theme_css = """
        :root {
            --primary-color: #ffb000 !important;
            --bg-color: #000000 !important;
            --card-bg: #1a1a1a !important;
            --font-family: 'Courier New', monospace !important;
        }
        """
    elif theme == "Cyberpunk (Neon)":
        theme_css = """
        :root {
            --primary-color: #00ff41 !important;
            --bg-color: #0b0014 !important;
            --card-bg: #1a0b2e !important;
        }
        """

    st.markdown(f'<style>{style_content}\n{theme_css}</style>', unsafe_allow_html=True)

def get_weather():
    lat = os.getenv("OPEN_METEO_LAT", "45.57")
    lon = os.getenv("OPEN_METEO_LONG", "-73.75")
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        data = response.json()
        temp = data['current_weather']['temperature']
        code = data['current_weather']['weathercode']
        condition = "Clear"
        if code > 3: condition = "Cloudy"
        if code > 50: condition = "Rainy"
        if code > 70: condition = "Snow"
        return temp, condition
    except requests.exceptions.Timeout:
        return "N/A", "Timeout"
    except requests.exceptions.RequestException:
        return "N/A", "Offline"
    except Exception:
         return "N/A", "Error"


def get_jellyfin_stats():
    # Load and Sanitize URL
    base_url = os.getenv("JELLYFIN_URL", "http://192.168.0.200:8096").rstrip('/')
    api_key = os.getenv("JELLYFIN_API_KEY", "")
    
    if not api_key:
        return 0, "⚠️ No API Key"
    
    headers = {"X-Emby-Token": api_key}
    
    try:
        url = f"{base_url}/Sessions"
        # INCREASED TIMEOUT to 5 seconds
        r = requests.get(url, headers=headers, timeout=5)
        
        if r.status_code == 200:
            sessions = r.json()
            # Success!
            return len(sessions), "Online"
        elif r.status_code == 401:
            return 0, "⛔ Unauthorized"
        elif r.status_code == 403:
            return 0, "⛔ Forbidden"
        else:
            return 0, f"Error {r.status_code}"
            
    except requests.exceptions.Timeout:
        return 0, "⏱️ Timeout"
    except requests.exceptions.ConnectionError:
        return 0, "🔌 Connection Refused"
    except Exception as e:
        # Show specific error name for debugging
        return 0, f"⚠️ {type(e).__name__}"

def check_ping(host):
    try:
        sock = socket.create_connection((host, 80), timeout=1)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False
    except Exception:
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
        df = df.sort_values(by='memory_percent', ascending=False).head(10)
        df['memory_percent'] = df['memory_percent'].apply(lambda x: f"{x:.1f}%")
        return df[['name', 'pid', 'memory_percent']]
    return pd.DataFrame()

def get_docker_containers():
    try:
        client = docker.from_env()
        containers = client.containers.list()
        data = []
        for c in containers:
            data.append({
                "Name": c.name,
                "Status": c.status,
                "Image": c.image.tags[0] if c.image.tags else c.image.id[:12]
            })
        return pd.DataFrame(data)
    except Exception as e:
        return pd.DataFrame()

# --- 3. TABS & FRAGMENTS ---

@st.fragment(run_every=2)
def render_command():
    # ROW 2: ENVIRONMENT
    col_w, col_n, col_p, col_m = st.columns(4)

    # Weather
    temp, cond = get_weather()
    with col_w:
        with st.container(border=True): st.metric("Weather", f"{temp}°C", cond)

    # Network
    now = time.time()
    current_io = psutil.net_io_counters()
    dt = now - st.session_state.net_last_time
    if dt < 0.1: dt = 0.1
    rx = (current_io.bytes_recv - st.session_state.net_last_io.bytes_recv) / dt
    tx = (current_io.bytes_sent - st.session_state.net_last_io.bytes_sent) / dt
    st.session_state.net_last_time = now
    st.session_state.net_last_io = current_io
    
    with col_n:
        with st.container(border=True):
            st.metric("DL", f"{rx/1024/1024:.2f} MB/s")
            st.metric("UL", f"{tx/1024/1024:.2f} MB/s")

    # Ping
    g_up = check_ping("google.com")
    gh_up = check_ping("github.com")
    with col_p:
        with st.container(border=True):
            st.markdown(f"**Google:** {'🟢' if g_up else '🔴'}")
            st.markdown(f"**GitHub:** {'🟢' if gh_up else '🔴'}")

    # Jellyfin
    jf_active, jf_status = get_jellyfin_stats()
    with col_m:
        with st.container(border=True):
            st.metric("Jellyfin", jf_status)
            if jf_status == "Online":
                st.caption(f"{jf_active} Streams")

@st.fragment(run_every=5)
def render_docker_fleet():
    st.subheader("🐳 Docker Fleet")
    df = get_docker_containers()

    hidden_str = os.getenv("HIDDEN_CONTAINERS", "")
    hidden_list = [x.strip() for x in hidden_str.split(",") if x.strip()]

    if not df.empty:
        # Filter hidden
        df = df[~df['Name'].isin(hidden_list)]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.warning("No containers found or Docker socket not connected.")

@st.fragment(run_every=2)
def render_system():
    # Metrics
    c1, c2, c3 = st.columns(3)
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

    with c1:
        with st.container(border=True):
            st.metric("CPU", f"{cpu}%")
            st.progress(cpu/100)
    with c2:
        with st.container(border=True):
            st.metric("RAM", f"{ram}%")
            st.progress(ram/100)
    with c3:
        with st.container(border=True):
            st.metric("Disk", f"{disk}%")
            st.progress(disk/100)

    st.markdown("---")
    st.subheader("Top Processes (Host)")
    df_hogs = get_top_hogs()
    st.dataframe(df_hogs, hide_index=True, use_container_width=True)

def render_admin():
    st.header("⚙️ Admin Panel")
    st.write("System Configuration & Personalization")

    # Load Defaults
    c_lat = os.getenv("OPEN_METEO_LAT", "45.57")
    c_lon = os.getenv("OPEN_METEO_LONG", "-73.75")
    c_jf_url = os.getenv("JELLYFIN_URL", "http://192.168.0.200:8096")
    c_jf_key = os.getenv("JELLYFIN_API_KEY", "")
    c_ad_user = os.getenv("ADGUARD_USERNAME", "")
    c_ad_pass = os.getenv("ADGUARD_PASSWORD", "")
    c_app_title = os.getenv("APP_TITLE", "BASEMENT HQ // COMMAND")
    c_app_logo = os.getenv("APP_LOGO", "")

    c_hidden = os.getenv("HIDDEN_CONTAINERS", "")
    current_hidden = [x.strip() for x in c_hidden.split(",") if x.strip()]

    # Get all containers for multiselect options
    df_containers = get_docker_containers()
    all_container_names = df_containers['Name'].tolist() if not df_containers.empty else []
    # Ensure current hidden ones are in options even if offline
    for h in current_hidden:
        if h not in all_container_names:
            all_container_names.append(h)

    with st.form("secrets"):
        st.subheader("Personalization")
        c_theme = st.selectbox("Dashboard Theme",
                                ["Default (Green)", "Red Alert", "Retro (Amber)", "Cyberpunk (Neon)"],
                                index=["Default (Green)", "Red Alert", "Retro (Amber)", "Cyberpunk (Neon)"].index(st.session_state.dashboard_theme) if st.session_state.dashboard_theme in ["Default (Green)", "Red Alert", "Retro (Amber)", "Cyberpunk (Neon)"] else 0)

        p1, p2 = st.columns(2)
        n_title = p1.text_input("App Title", c_app_title)
        n_logo = p2.text_input("App Logo URL (Optional)", c_app_logo)

        st.subheader("Docker Configuration")
        n_hidden_list = st.multiselect("Hide Containers", options=all_container_names, default=current_hidden)

        st.subheader("System Config")
        c1, c2 = st.columns(2)
        n_lat = c1.text_input("Lat", c_lat)
        n_lon = c2.text_input("Longitude", c_lon)
        
        n_url = st.text_input("Jellyfin URL", c_jf_url)
        n_key = st.text_input("Jellyfin API Key", c_jf_key, type="password")
        n_ad = st.text_input("AdGuard User", c_ad_user)
        n_ad_pass = st.text_input("AdGuard Password", c_ad_pass, type="password")
        
        if st.form_submit_button("💾 Save"):
            save_secrets("OPEN_METEO_LAT", n_lat)
            save_secrets("OPEN_METEO_LONG", n_lon)
            save_secrets("JELLYFIN_URL", n_url)
            save_secrets("JELLYFIN_API_KEY", n_key)
            save_secrets("ADGUARD_USERNAME", n_ad)
            save_secrets("ADGUARD_PASSWORD", n_ad_pass)
            save_secrets("APP_TITLE", n_title)
            save_secrets("APP_LOGO", n_logo)
            save_secrets("DASHBOARD_THEME", c_theme)
            save_secrets("HIDDEN_CONTAINERS", ",".join(n_hidden_list))
            
            st.session_state.dashboard_theme = c_theme
            st.success("Saved! Reloading...")
            time.sleep(1)
            st.rerun()

# --- MAIN ENTRY ---
if __name__ == "__main__":
    inject_custom_css()

    # Header
    app_title = os.getenv("APP_TITLE", "BASEMENT HQ // COMMAND")
    app_logo = os.getenv("APP_LOGO", "")
    c1, c2 = st.columns([3, 1])
    with c1:
        if app_logo:
             st.image(app_logo, width=50)
        st.title(app_title)

    tab1, tab2, tab3, tab4 = st.tabs(["🏠 Command", "🐳 Docker Fleet", "🧠 System Intelligence", "⚙️ Admin"])

    with tab1:
        render_command()
    with tab2:
        render_docker_fleet()
    with tab3:
        render_system()
    with tab4:
        render_admin()
