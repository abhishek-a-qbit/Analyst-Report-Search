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

# Initialize session state
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

# Sidebar - Navigation
st.sidebar.header("📌 Navigation")
page = st.sidebar.radio("Go to", ["🔍 Search", "📜 History"])

# Sidebar - API Status and Info
st.sidebar.header("🔌 API Status")
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
st.sidebar.markdown(f"**Total Searches:** {len(st.session_state.conversation_history)}")

# Search Page
if page == "🔍 Search":
    st.title("📊 Analyst Report Search")
    st.markdown("""
    Find analyst reports from top firms like Gartner, Forrester, IDC, Everest Group, and Quadrant Knowledge Solutions.
    """)

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
                    "search_queries": result.get("search_queries", []),
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
                else:
                    for query_group in result["search_results"]:
                        query = query_group.get("query", "")
                        results = query_group.get("results", [])
                        
                        st.markdown(f"**Query:** `{query}`")
                        
                        if not results:
                            st.warning("No results for this query.")
                        elif "error" in results[0]:
                            st.error(results[0]["error"])
                        else:
                            for i, res in enumerate(results, 1):
                                with st.expander(f"{i}. {res['title']}", expanded=i == 1):
                                    st.markdown(f"**Link:** [{res['link']}]({res['link']})")
                                    st.markdown(f"**Snippet:** {res['snippet']}")
                                    st.markdown(f"[Open Link]({res['link']})")
                        st.markdown("---")

            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to API: {str(e)}")
                st.error("Make sure the FastAPI server is running on http://localhost:8000")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

# History Page
elif page == "📜 History":
    st.title("📜 Search History")

    if not st.session_state.conversation_history:
        st.info("No search history yet. Go to the Search page to perform a search.")
    else:
        for idx, entry in enumerate(reversed(st.session_state.conversation_history), 1):
            with st.expander(f"Search #{idx}: {entry['query'][:50]}...", expanded=False):
                st.markdown(f"**Query:** {entry['query']}")

                if entry.get('official_site_query'):
                    st.markdown("**Step 1: Official Site Search**")
                    st.code(entry['official_site_query'], language="text")

                if entry.get('real_report_names'):
                    st.markdown("**Step 2: Real Report Names Found**")
                    for i, report in enumerate(entry['real_report_names'], 1):
                        if isinstance(report, dict):
                            st.markdown(f"{i}. **{report['name']}**")
                            st.markdown(f"   - Source: [{report['link']}]({report['link']})")
                        else:
                            st.markdown(f"{i}. **{report}**")

                if entry.get('search_queries'):
                    st.markdown("**Step 3: Search Queries for Free Versions**")
                    st.markdown(f"**Using {len(entry['search_queries'])} search queries:**")
                    for i, query in enumerate(entry['search_queries'], 1):
                        st.code(query, language="text")
                else:
                    st.markdown("**Step 3: Search Query for Free Versions**")
                    st.code(entry['search_query'], language="text")

                st.markdown("**Step 4: Final Search Results**")
                if not entry['results']:
                    st.warning("No results found.")
                else:
                    for query_group in entry['results']:
                        query = query_group.get("query", "")
                        results = query_group.get("results", [])
                        
                        st.markdown(f"**Query:** `{query}`")
                        
                        if not results:
                            st.warning("No results for this query.")
                        elif "error" in results[0]:
                            st.error(results[0]['error'])
                        else:
                            for i, res in enumerate(results, 1):
                                st.markdown(f"{i}. **{res['title']}**")
                                st.markdown(f"   - Link: [{res['link']}]({res['link']})")
                                st.markdown(f"   - Snippet: {res['snippet'][:100]}...")
                        st.markdown("---")

        if st.button("🗑️ Clear All History"):
            st.session_state.conversation_history = []
            st.rerun()
