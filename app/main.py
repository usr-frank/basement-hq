import streamlit as st
import psutil
import time

def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

def main():
    st.set_page_config(page_title="Basement HQ", layout="wide")

    # Load custom CSS
    try:
        load_css("app/style.css")
    except FileNotFoundError:
        # Fallback if running from a different directory context or file missing
        try:
            load_css("style.css")
        except:
            st.warning("CSS file not found.")

    st.title("BASEMENT HQ")

    st.markdown("---")

    st.header("System Health")

    # Create placeholders for metrics
    col1, col2 = st.columns(2)

    # Simple auto-refresh loop (optional, but good for dashboards)
    # For now, we just render it once per run/rerun.
    # To make it dynamic, user can click 'Rerun' or we can use st.empty() loop.
    # Given the requirements "Display a clean header... Show a placeholder section",
    # I will display the current snapshot.

    cpu_usage = psutil.cpu_percent(interval=1)
    ram_usage = psutil.virtual_memory().percent

    col1.metric("CPU Usage", f"{cpu_usage}%")
    col2.metric("RAM Usage", f"{ram_usage}%")

if __name__ == "__main__":
    main()
