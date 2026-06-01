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

st.sidebar.header("About")
st.sidebar.info("""
This tool helps you find analyst reports from any research firm by converting natural language queries into optimized searches.

The LLM uses its knowledge to identify the analyst firm and their specific report type automatically.

**Example Queries:**
- "What are the typical names of analyst reports for ABM category from Gartner?"
- "Find Forrester Wave reports for cloud security"
- "IDC MarketScape for CRM platforms"
- "Everest Group PEAK Matrix for RPA tools"
- "Gartner Magic Quadrant for cloud infrastructure"
""")

# Session state for conversation history
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []

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
                "results": result["search_results"]
            })
            
            # Display current search
            st.subheader("Search Query Generated")
            st.code(result["search_query"], language="text")
            
            st.subheader("Search Results")
            
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

# Display conversation history
if st.session_state.conversation_history:
    st.divider()
    st.subheader("📜 Search History")
    
    for idx, entry in enumerate(reversed(st.session_state.conversation_history), 1):
        with st.expander(f"Search #{idx}: {entry['query'][:50]}...", expanded=False):
            st.markdown(f"**Original Query:** {entry['query']}")
            st.markdown(f"**Generated Search Query:**")
            st.code(entry['search_query'], language="text")
            
            st.markdown("**Results:**")
            if entry['results']:
                for i, res in enumerate(entry['results'], 1):
                    st.markdown(f"{i}. **{res['title']}**")
                    st.markdown(f"   - Link: [{res['link']}]({res['link']})")
                    st.markdown(f"   - {res['snippet']}")
            else:
                st.markdown("No results found.")

st.divider()
