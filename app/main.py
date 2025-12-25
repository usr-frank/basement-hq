import streamlit as st
import psutil
import time

def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

@st.fragment(run_every=2)
def display_system_stats():
    st.header("System Health")

    # metrics
    cpu = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory().percent
    disk = psutil.disk_usage('/').percent

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
    try:
        load_css("app/style.css")
    except FileNotFoundError:
        try:
            load_css("style.css")
        except:
            st.warning("CSS file not found.")

    st.title("BASEMENT HQ")
    st.markdown("---")

    display_system_stats()

if __name__ == "__main__":
    main()
