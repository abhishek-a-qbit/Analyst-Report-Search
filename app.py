import streamlit as st
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Analyst Report Search",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Analyst Report Search")
st.markdown("""
Find analyst reports from top firms like Gartner, Forrester, IDC, Everest Group, and Quadrant Knowledge Solutions.
""")

# Session state for conversation history
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

# Sidebar - API Status and Info
st.sidebar.header("� API Status")
api_status = st.empty()

def check_api_status():
    try:
        response = requests.get(f"{API_URL}/", timeout=5)
        if response.status_code == 200:
            return "✅ Connected", "success"
        else:
            return f"⚠️ Error: {response.status_code}", "warning"
    except:
        return "❌ Disconnected", "error"

status, status_type = check_api_status()
api_status.markdown(f"**Status:** {status}")

st.sidebar.header("ℹ️ Info")
st.sidebar.markdown(f"**API URL:** {API_URL}")
st.sidebar.markdown(f"**Searches:** {len(st.session_state.conversation_history)}")

# User input
user_query = st.text_input(
    "Enter your query:",
    placeholder="e.g., What are the typical names of analyst reports for ABM category from Gartner?",
    key="query_input"
)

col1, col2 = st.columns([1, 5])
with col1:
    search_button = st.button("🔍 Search", type="primary")
with col2:
    clear_button = st.button("🗑️ Clear History")

if clear_button:
    st.session_state.conversation_history = []
    st.rerun()

if search_button and user_query:
    with st.spinner("Searching for analyst reports..."):
        try:
            response = requests.post(
                f"{API_URL}/search",
                json={"query": user_query},
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            
            # Add to conversation history
            st.session_state.conversation_history.append({
                "query": user_query,
                "search_query": result["search_query"],
                "official_site_query": result.get("official_site_query", ""),
                "real_report_names": result.get("real_report_names", []),
                "results": result["search_results"]
            })
            
            # Display current search
            st.subheader("Step 1: Official Site Search")
            if result.get("official_site_query"):
                st.code(result["official_site_query"], language="text")
            else:
                st.info("No official site query generated (firm not identified)")
            
            st.subheader("Step 2: Real Report Names Found")
            if result.get("real_report_names") and result["real_report_names"]:
                for i, report in enumerate(result["real_report_names"], 1):
                    if isinstance(report, dict):
                        st.markdown(f"{i}. **{report['name']}**")
                        st.markdown(f"   - Source: [{report['link']}]({report['link']})")
                    else:
                        st.markdown(f"{i}. **{report}**")
            else:
                st.info("No specific report names found. Using general search terms.")
            
            st.subheader("Step 3: Search Queries for Free Versions")
            if result.get("search_queries") and result["search_queries"]:
                st.markdown(f"**Using {len(result['search_queries'])} search queries based on report names:**")
                for i, query in enumerate(result["search_queries"], 1):
                    st.code(query, language="text")
            else:
                st.code(result["search_query"], language="text")
            
            st.subheader("Step 4: Final Search Results")
            
            if not result["search_results"]:
                st.warning("No results found. Try rephrasing your query.")
            elif "error" in result["search_results"][0]:
                st.error(result["search_results"][0]["error"])
            else:
                for i, res in enumerate(result["search_results"], 1):
                    with st.expander(f"{i}. {res['title']}", expanded=i == 1):
                        st.markdown(f"**Link:** [{res['link']}]({res['link']})")
                        st.markdown(f"**Snippet:** {res['snippet']}")
                        st.markdown(f"[Open Link]({res['link']})")
            
        except requests.exceptions.RequestException as e:
            st.error(f"Failed to connect to API: {str(e)}")
            st.error("Make sure the FastAPI server is running on http://localhost:8000")
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
