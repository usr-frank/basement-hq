import streamlit as st
import psutil
import time
import os

def load_css(file_name):
    # Try loading from app/ folder first, then current folder
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        try:
            # Fallback for local testing
            with open(os.path.basename(file_name)) as f:
                st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
        except FileNotFoundError:
            st.warning(f"CSS file not found: {file_name}")

@st.fragment(run_every=2)
def display_system_stats():
    st.header("System Health")

    # Fetch Metrics
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

    # Create 3 Columns for the Console Look
    col1, col2, col3 = st.columns(3)

    with col1:
        with st.container(border=True):
            st.metric("CPU", f"{cpu}%")
            st.progress(cpu / 100)

    with col2:
        with st.container(border=True):
            st.metric("RAM", f"{ram}%")
            st.progress(ram / 100)

    with col3:
        with st.container(border=True):
            st.metric("Disk", f"{disk}%")
            st.progress(disk / 100)

def main():
    st.set_page_config(page_title="Basement HQ", layout="wide")

    # Load custom CSS
    load_css("app/style.css")

    st.title("BASEMENT HQ")
    st.markdown("---")

    # Display the Auto-Refreshing Stats
    display_system_stats()

if __name__ == "__main__":
    main()