import streamlit as st
import psutil
import time
import requests
from requests.auth import HTTPBasicAuth
import pandas as pd
import socket
import os
import docker
import docker.errors
from dotenv import load_dotenv

# --- 1. CONFIGURATION & STATE ---
load_dotenv()

st.set_page_config(page_title="Basement HQ", layout="wide")

# Ensure assets directory exists
if not os.path.exists("app/assets"):
    os.makedirs("app/assets")

# Initialize Session State
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
    
    if os.path.exists(css_file):
        with open(css_file) as f:
            style_content = f.read()
    else:
        style_content = ""

    theme = st.session_state.dashboard_theme

    # Custom Font Logic
    font_face_css = ""
    global_font_family = "sans-serif" # Fallback

    # Check for custom font files
    font_path_ttf = "app/assets/custom_font.ttf"
    font_path_otf = "app/assets/custom_font.otf"

    found_font = None
    fmt = None

    if os.path.exists(font_path_ttf):
        found_font = font_path_ttf
        fmt = "truetype"
    elif os.path.exists(font_path_otf):
        found_font = font_path_otf
        fmt = "opentype"

    if found_font:
        import base64
        with open(found_font, "rb") as f:
            b64_font = base64.b64encode(f.read()).decode()

        font_face_css = f"""
        @font-face {{
            font-family: 'CustomFont';
            src: url('data:font/{fmt};base64,{b64_font}') format('{fmt}');
            font-weight: normal;
            font-style: normal;
        }}
        """
        global_font_family = "'CustomFont', sans-serif"

    # Theme Colors
    theme_css = ""
    if theme == "Red Alert":
        theme_css = """
        :root { --primary-color: #ef4444 !important; --bg-color: #2b0a0a !important; --card-bg: #450a0a !important; }
        """
    elif theme == "Retro (Amber)":
        theme_css = """
        :root { --primary-color: #ffb000 !important; --bg-color: #000000 !important; --card-bg: #1a1a1a !important; }
        """
    elif theme == "Cyberpunk (Neon)":
        theme_css = """
        :root { --primary-color: #00ff41 !important; --bg-color: #0b0014 !important; --card-bg: #1a0b2e !important; }
        """

    # Background Image Logic
    bg_css = ""
    bg_path = "app/assets/background.png"
    if os.path.exists(bg_path):
        import base64
        with open(bg_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode()
        bg_css = f"""
        .stApp {{
            background-image: url("data:image/png;base64,{encoded_string}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        """

    # Global Font Injection
    global_font_css = f"""
    html, body, [class*="css"] {{
        font-family: {global_font_family} !important;
    }}
    """

    st.markdown(f'<style>{font_face_css}\n{theme_css}\n{style_content}\n{global_font_css}\n{bg_css}</style>', unsafe_allow_html=True)

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
    except (requests.exceptions.RequestException, KeyError):
        return "N/A", "Offline"

def get_jellyfin_stats():
    base_url = os.getenv("JELLYFIN_URL", "http://192.168.0.200:8096").rstrip('/')
    api_key = os.getenv("JELLYFIN_API_KEY", "")
    
    if not api_key: return "⚠️ No Key", "Check Config"
    
    try:
        url = f"{base_url}/Sessions"
        r = requests.get(url, headers={"X-Emby-Token": api_key}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            active_streams = []
            for s in data:
                if "NowPlayingItem" in s:
                    title = s["NowPlayingItem"].get("Name", "Unknown")
                    user = s.get("UserName", "Someone")
                    active_streams.append(f"{user} watching {title}")

            count = len(active_streams)
            if count == 0:
                return "Online", "System Idle"

            status_label = "1 Stream" if count == 1 else f"{count} Streams"

            if count > 1:
                details_text = f"{active_streams[0]} (+{count - 1} others)"
            else:
                details_text = active_streams[0]

            return status_label, details_text

        elif r.status_code == 401 or r.status_code == 403:
            return "Auth Error", "Check API Key"
        else:
            return f"Error {r.status_code}", "Check Logs"
    except requests.exceptions.RequestException:
        return "Offline", "Connection Lost"

def get_adguard_stats():
    base_url = os.getenv("ADGUARD_URL", "http://192.168.0.200:80").rstrip("/")
    if base_url.endswith("/control/stats"):
        url = base_url
    else:
        url = f"{base_url}/control/stats"

    username = os.getenv("ADGUARD_USERNAME", "")
    password = os.getenv("ADGUARD_PASSWORD", "")

    try:
        response = requests.get(url, auth=HTTPBasicAuth(username, password), timeout=3)
        response.raise_for_status()
        data = response.json()

        total = data.get("num_dns_queries", 0)
        blocked = data.get("num_blocked_filtering", 0)

        if total > 0:
            percentage = (blocked / total) * 100
        else:
            percentage = 0.0

        return str(total), str(blocked), f"{percentage:.1f}%"

    except requests.exceptions.HTTPError as e:
        return "⚠️ Error", f"{e.response.status_code} {e.response.reason}", "Offline"
    except requests.exceptions.ConnectionError:
        return "⚠️ Error", "Connection Refused", "Offline"
    except requests.exceptions.Timeout:
        return "⚠️ Error", "Timeout", "Offline"
    except (requests.exceptions.RequestException, ValueError) as e:
        # Catch other request exceptions or JSON decoding errors
        return "⚠️ Error", str(e)[:25], "Offline"

def check_ping(host):
    try:
        sock = socket.create_connection((host, 80), timeout=1)
        sock.close()
        return True
    except (socket.timeout, socket.error, OSError):
        return False

def get_top_hogs():
    # Returns real processes from Host because we use pid: host
    processes = []
    # Handle specific psutil exceptions safely
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
        try:
            processes.append(proc.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    df = pd.DataFrame(processes)
    if not df.empty:
        df = df.sort_values(by='memory_percent', ascending=False).head(10)
        df['memory_percent'] = df['memory_percent'].apply(lambda x: f"{x:.1f}%")
        return df[['name', 'pid', 'memory_percent']]
    return pd.DataFrame()

@st.cache_resource
def get_docker_client():
    try:
        return docker.from_env()
    except Exception:
        return None

def get_docker_containers():
    client = get_docker_client()
    if not client:
        return pd.DataFrame()

    try:
        # Use all=True to get exited containers as well, so we can show red status
        containers = client.containers.list(all=True)
        data = []
        for c in containers:
            status_val = c.status
            # Add emojis for badge-like appearance
            if status_val == 'running':
                display_status = "🟢 Running"
            elif status_val == 'exited':
                display_status = "🔴 Exited"
            else:
                display_status = f"⚪ {status_val.capitalize()}"

            data.append({
                "Name": c.name,
                "Status": display_status,
                "Image": c.image.tags[0] if c.image.tags else c.image.id[:12]
            })
        return pd.DataFrame(data)
    except (docker.errors.DockerException, docker.errors.APIError):
        return pd.DataFrame()

# --- 3. TABS & FRAGMENTS ---

@st.fragment(run_every=2)
def render_command():
    # ROW 1: Weather & Network & Ping & Jellyfin
    col_w, col_n, col_p, col_m = st.columns(4)

    # Weather
    temp, cond = get_weather()
    with col_w:
        with st.container(border=True): st.metric("Weather", f"{temp}°C", cond)

    # Network IO
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
            sub_c1, sub_c2 = st.columns(2)
            sub_c1.metric("DL", f"{rx/1024/1024:.2f} MB/s")
            sub_c2.metric("UL", f"{tx/1024/1024:.2f} MB/s")

    # Custom Pings
    p1_host = os.getenv("PING_HOST_1", "google.com")
    p1_label = os.getenv("PING_LABEL_1", "Google")
    p2_host = os.getenv("PING_HOST_2", "github.com")
    p2_label = os.getenv("PING_LABEL_2", "GitHub")

    g_up = check_ping(p1_host)
    gh_up = check_ping(p2_host)
    with col_p:
        with st.container(border=True):
            sub_p1, sub_p2 = st.columns(2)
            sub_p1.markdown(f"**{p1_label}:** {'🟢' if g_up else '🔴'}")
            sub_p2.markdown(f"**{p2_label}:** {'🟢' if gh_up else '🔴'}")

    # Jellyfin
    jf_label, jf_details = get_jellyfin_stats()
    with col_m:
        with st.container(border=True):
            st.metric("Jellyfin", jf_label)
            st.caption(jf_details)

    # ROW 2: Network Defense (AdGuard)
    st.subheader("🛡️ Network Defense")
    ad_label1, ad_label2, ad_label3 = get_adguard_stats()
    col_ad1, col_ad2, col_ad3 = st.columns(3)

    with col_ad1:
        with st.container(border=True):
            st.metric("Total Queries", ad_label1)

    with col_ad2:
        with st.container(border=True):
            st.metric("Ads Blocked", ad_label2)

    with col_ad3:
        with st.container(border=True):
            st.metric("Efficiency", ad_label3)

    # Footer
    st.caption(f"System Heartbeat: {time.strftime('%H:%M:%S')}")

@st.fragment(run_every=5)
def render_docker_fleet():
    st.subheader("🐳 Docker Fleet")
    df = get_docker_containers()
    
    hidden_str = os.getenv("HIDDEN_CONTAINERS", "")
    hidden_list = [x.strip() for x in hidden_str.split(",") if x.strip()]

    if not df.empty:
        # Filter hidden
        df = df[~df['Name'].isin(hidden_list)]

        # Display with specific column configuration for Status "pill" look
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn(
                    "Status",
                    help="Container health status",
                    width="medium"
                ),
                "Name": st.column_config.TextColumn("Container Name"),
                "Image": st.column_config.TextColumn("Image")
            }
        )
    else:
        st.warning("No containers found or Docker socket not connected.")

@st.fragment(run_every=2)
def render_system():
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
    
    c_lat = os.getenv("OPEN_METEO_LAT", "45.57")
    c_lon = os.getenv("OPEN_METEO_LONG", "-73.75")
    c_jf_url = os.getenv("JELLYFIN_URL", "http://192.168.0.200:8096")
    c_jf_key = os.getenv("JELLYFIN_API_KEY", "")
    c_ad_url = os.getenv("ADGUARD_URL", "http://192.168.0.200:80")
    c_ad_user = os.getenv("ADGUARD_USERNAME", "")
    c_ad_pass = os.getenv("ADGUARD_PASSWORD", "")
    c_app_title = os.getenv("APP_TITLE", "BASEMENT HQ // COMMAND")
    # c_app_logo is managed by file upload mostly now, but keeping env read for safety
    c_app_logo = os.getenv("APP_LOGO", "")
    
    # Ping defaults
    c_p1_host = os.getenv("PING_HOST_1", "google.com")
    c_p1_label = os.getenv("PING_LABEL_1", "Google")
    c_p2_host = os.getenv("PING_HOST_2", "github.com")
    c_p2_label = os.getenv("PING_LABEL_2", "GitHub")

    c_hidden = os.getenv("HIDDEN_CONTAINERS", "")
    current_hidden = [x.strip() for x in c_hidden.split(",") if x.strip()]
    
    # Get container options
    df_containers = get_docker_containers()
    all_names = df_containers['Name'].tolist() if not df_containers.empty else []
    for h in current_hidden:
        if h not in all_names: all_names.append(h)

    with st.form("secrets"):
        st.subheader("Personalization")

        # Theme
        col_t = st.columns(1)[0]
        c_theme = col_t.selectbox("Dashboard Theme",
            ["Default (Green)", "Red Alert", "Retro (Amber)", "Cyberpunk (Neon)"],
            index=["Default (Green)", "Red Alert", "Retro (Amber)", "Cyberpunk (Neon)"].index(st.session_state.dashboard_theme) if st.session_state.dashboard_theme in ["Default (Green)", "Red Alert", "Retro (Amber)", "Cyberpunk (Neon)"] else 0)
        
        p1, p2 = st.columns(2)
        n_title = p1.text_input("App Title", c_app_title)

        # File Uploaders
        st.subheader("Asset Management")
        u_logo = st.file_uploader("Upload Logo (PNG)", type=["png"])
        u_bg = st.file_uploader("Upload Wallpaper (PNG)", type=["png"])
        u_font = st.file_uploader("Upload Custom Font (TTF/OTF)", type=["ttf", "otf"])

        st.subheader("Docker Config")
        n_hidden = st.multiselect("Hide Containers", options=all_names, default=current_hidden)

        st.subheader("Network Configuration")
        net1, net2 = st.columns(2)
        n_p1_host = net1.text_input("Ping Target 1 (Host)", c_p1_host)
        n_p1_label = net2.text_input("Ping Target 1 (Label)", c_p1_label)

        net3, net4 = st.columns(2)
        n_p2_host = net3.text_input("Ping Target 2 (Host)", c_p2_host)
        n_p2_label = net4.text_input("Ping Target 2 (Label)", c_p2_label)

        st.subheader("System Secrets")
        c1, c2 = st.columns(2)
        n_lat = c1.text_input("Lat", c_lat)
        n_lon = c2.text_input("Lon", c_lon)
        n_url = st.text_input("Jellyfin URL", c_jf_url)
        n_key = st.text_input("Jellyfin Key", c_jf_key, type="password")
        n_ad_url = st.text_input("AdGuard URL", c_ad_url)
        n_ad = st.text_input("AdGuard User", c_ad_user)
        n_ad_pass = st.text_input("AdGuard Password", c_ad_pass, type="password")

        if st.form_submit_button("💾 Save"):
            # Process File Uploads
            if u_logo:
                with open("app/assets/logo.png", "wb") as f:
                    f.write(u_logo.getbuffer())
                save_secrets("APP_LOGO", "app/assets/logo.png")

            if u_bg:
                with open("app/assets/background.png", "wb") as f:
                    f.write(u_bg.getbuffer())

            if u_font:
                # Determine extension
                ext = u_font.name.split(".")[-1].lower()
                if ext in ["ttf", "otf"]:
                    # Remove old files to avoid confusion
                    if os.path.exists("app/assets/custom_font.ttf"): os.remove("app/assets/custom_font.ttf")
                    if os.path.exists("app/assets/custom_font.otf"): os.remove("app/assets/custom_font.otf")

                    target_path = f"app/assets/custom_font.{ext}"
                    with open(target_path, "wb") as f:
                        f.write(u_font.getbuffer())

            save_secrets("OPEN_METEO_LAT", n_lat)
            save_secrets("OPEN_METEO_LONG", n_lon)
            save_secrets("JELLYFIN_URL", n_url)
            save_secrets("JELLYFIN_API_KEY", n_key)
            save_secrets("ADGUARD_URL", n_ad_url)
            save_secrets("ADGUARD_USERNAME", n_ad)
            save_secrets("ADGUARD_PASSWORD", n_ad_pass)
            save_secrets("APP_TITLE", n_title)

            # Save Ping Config
            save_secrets("PING_HOST_1", n_p1_host)
            save_secrets("PING_LABEL_1", n_p1_label)
            save_secrets("PING_HOST_2", n_p2_host)
            save_secrets("PING_LABEL_2", n_p2_label)

            save_secrets("DASHBOARD_THEME", c_theme)
            save_secrets("HIDDEN_CONTAINERS", ",".join(n_hidden))
            
            st.session_state.dashboard_theme = c_theme
            st.success("Saved! Reloading...")
            time.sleep(1)
            st.rerun()

# --- MAIN ENTRY ---
if __name__ == "__main__":
    inject_custom_css()
    
    # Custom Header (Logo + Title)
    # Replaces the standard st.header/st.title usage and sidebar usage for title
    app_title = os.getenv("APP_TITLE", "BASEMENT HQ // COMMAND")
    app_logo = os.getenv("APP_LOGO", "")

    # Layout: Logo (0.5) | Title (4)
    # We put this at the top of the main area
    h_col1, h_col2 = st.columns([0.5, 4], vertical_alignment="center")

    with h_col1:
        if app_logo and os.path.exists(app_logo):
            st.image(app_logo, width=80)
        elif app_logo: # Fallback if it's a URL or path that os.path.exists failed on (e.g. http)
             st.image(app_logo, width=80)

    with h_col2:
        st.markdown(f"<h1 style='margin-top: 0; padding-top: 0; display: inline-block;'>{app_title}</h1>", unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.header("Control")
        if st.button("🔄 Refresh Data", type="primary"):
            st.rerun()

    tab1, tab2, tab3, tab4 = st.tabs(["🏠 Command", "🐳 Docker Fleet", "🧠 System Intelligence", "⚙️ Admin"])
    
    with tab1: render_command()
    with tab2: render_docker_fleet()
    with tab3: render_system()
    with tab4: render_admin()
