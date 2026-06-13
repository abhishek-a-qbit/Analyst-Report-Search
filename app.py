import streamlit as st
import requests
import os
import json
from dotenv import load_dotenv
from datetime import datetime
from db_utils import save_search, get_all_searches, clear_all_history, get_search_stats

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

if "category_search_results" not in st.session_state:
    st.session_state.category_search_results = None

# Sidebar - Navigation
st.sidebar.header("📌 Navigation")
page = st.sidebar.radio("Go to", ["🔍 Search", "🤖 Deep Search", "📂 Category Search", "📜 History"])

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


def format_category_search_results_to_txt(result: dict) -> str:
    """Format category search results as a text file."""
    lines = []
    lines.append("=" * 80)
    lines.append("CATEGORY SEARCH RESULTS")
    lines.append("=" * 80)
    lines.append(f"Category: {result.get('category', 'N/A')}")
    lines.append(f"Firms Searched: {', '.join(result.get('firms_searched', []))}")
    lines.append(f"Official Site Search: {'Enabled' if result.get('search_official_sites') else 'Disabled'}")
    lines.append(f"Export Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 80)
    lines.append("")
    
    # Official site search details
    if result.get('search_official_sites') and result.get('official_site_queries'):
        lines.append("STEP 1: OFFICIAL SITE SEARCH")
        lines.append("-" * 80)
        lines.append("Official Site Queries:")
        for query_info in result.get('official_site_queries', []):
            lines.append(f"  - {query_info['query']}")
        lines.append("")
        
        lines.append("Real Report Names Found:")
        real_report_names = result.get('real_report_names', {})
        for firm_name, reports in real_report_names.items():
            if reports:
                lines.append(f"\n{firm_name}:")
                for i, report in enumerate(reports, 1):
                    lines.append(f"  {i}. {report['name']}")
                    lines.append(f"     Source: {report['link']}")
        lines.append("")
        lines.append("=" * 80)
        lines.append("")
    
    # Final search results
    lines.append("STEP 2: FINAL SEARCH RESULTS BY FIRM")
    lines.append("-" * 80)
    lines.append("")
    
    search_results = result.get("search_results", {})
    
    if "error" in search_results:
        lines.append(f"Error: {search_results['error']}")
    elif not search_results:
        lines.append("No results found.")
    else:
        for firm_name, firm_results in search_results.items():
            lines.append(f"\n{'=' * 80}")
            lines.append(f"FIRM: {firm_name}")
            lines.append("=" * 80)
            
            if not firm_results:
                lines.append("No results found for this firm.")
                continue
            
            for report_group in firm_results:
                report_type = report_group.get("report_type", "")
                query = report_group.get("query", "")
                results = report_group.get("results", [])
                source_link = report_group.get("source_link", "")
                
                lines.append(f"\nReport Type: {report_type}")
                if source_link:
                    lines.append(f"Source: {source_link}")
                lines.append(f"Query: {query}")
                lines.append("-" * 40)
                
                if not results:
                    lines.append("No results for this query.")
                elif "error" in results[0]:
                    lines.append(f"Error: {results[0]['error']}")
                else:
                    for i, res in enumerate(results, 1):
                        lines.append(f"\n{i}. {res.get('title', 'No title')}")
                        lines.append(f"   Link: {res.get('link', 'No link')}")
                        lines.append(f"   Snippet: {res.get('snippet', 'No snippet')}")
                lines.append("")
    
    lines.append("=" * 80)
    lines.append("END OF REPORT")
    lines.append("=" * 80)
    
    return "\n".join(lines)

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
                history_entry = {
                    "query": user_query,
                    "search_query": result["search_query"],
                    "search_queries": result.get("search_queries", []),
                    "official_site_query": result.get("official_site_query", ""),
                    "real_report_names": result.get("real_report_names", []),
                    "results": result["search_results"]
                }
                st.session_state.conversation_history.append(history_entry)
                
                # Save to database
                save_search(
                    query=user_query,
                    search_type="search",
                    results=history_entry,
                    metadata={"search_query": result["search_query"]}
                )

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

# Deep Search Page
elif page == "🤖 Deep Search":
    st.title("🤖 Deep Search")
    st.markdown("""
    Uses an AI agent to deeply search the web for analyst report PDFs using multiple strategies.
    The agent iteratively refines its search to find reports from various sources.
    """)

    # User input
    user_query = st.text_input(
        "Enter your query:",
        placeholder="e.g., Gartner Magic Quadrant for Account-Based Marketing Platforms",
        key="deep_query_input"
    )

    max_iterations = st.slider(
        "Max search iterations (more iterations = deeper search but slower):",
        min_value=1,
        max_value=10,
        value=5,
        step=1
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        search_button = st.button("🔍 Deep Search", type="primary")
    with col2:
        clear_button = st.button("🗑️ Clear History")

    if clear_button:
        st.session_state.conversation_history = []
        st.rerun()

    if search_button and user_query:
        with st.spinner("Agent is searching deeply for analyst reports..."):
            try:
                response = requests.post(
                    f"{API_URL}/deep-search",
                    json={"query": user_query, "max_iterations": max_iterations},
                    timeout=600
                )
                response.raise_for_status()
                result = response.json()

                # Add to conversation history
                history_entry = {
                    "query": user_query,
                    "search_type": "deep",
                    "analyst_firm": result.get("analyst_firm", ""),
                    "report_type": result.get("report_type", ""),
                    "category": result.get("category", ""),
                    "iterations": result.get("iterations", 0),
                    "search_queries": result.get("search_queries", []),
                    "reasoning_trace": result.get("reasoning_trace", []),
                    "results": result.get("search_results", [])
                }
                st.session_state.conversation_history.append(history_entry)
                
                # Save to database
                save_search(
                    query=user_query,
                    search_type="deep",
                    results=history_entry,
                    metadata={
                        "analyst_firm": result.get("analyst_firm", ""),
                        "report_type": result.get("report_type", ""),
                        "category": result.get("category", ""),
                        "iterations": result.get("iterations", 0)
                    }
                )

                # Display analysis
                st.subheader("📊 Query Analysis")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Analyst Firm", result.get("analyst_firm", "Not identified"))
                with col2:
                    st.metric("Report Type", result.get("report_type", "Not identified"))
                with col3:
                    st.metric("Category", result.get("category", "Not identified"))

                st.subheader("🔄 Search Process")
                st.metric("Iterations Completed", result.get("iterations", 0))

                if result.get("reasoning_trace"):
                    with st.expander("View Agent Reasoning Trace"):
                        for i, reasoning in enumerate(result["reasoning_trace"], 1):
                            st.markdown(f"**Step {i}:** {reasoning}")

                st.subheader("🔍 Search Queries Used")
                if result.get("search_queries"):
                    for i, query in enumerate(result["search_queries"], 1):
                        st.code(query, language="text")
                else:
                    st.info("No search queries recorded")

                st.subheader("📄 Validated Results")
                if not result.get("search_results"):
                    st.warning("No valid results found. Try increasing iterations or rephrasing your query.")
                else:
                    for i, res in enumerate(result["search_results"], 1):
                        with st.expander(f"{i}. {res.get('title', 'No title')}", expanded=i == 1):
                            st.markdown(f"**Link:** [{res.get('link', 'No link')}]({res.get('link', '#')})")
                            st.markdown(f"**Snippet:** {res.get('snippet', 'No snippet')}")
                            if res.get("query_used"):
                                st.markdown(f"**Found via:** `{res['query_used']}`")
                            st.markdown(f"[Open Link]({res.get('link', '#')})")

            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to API: {str(e)}")
                st.error("Make sure the FastAPI server is running on http://localhost:8000")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

# Category Search Page
elif page == "📂 Category Search":
    st.title("📂 Category Search")
    st.markdown("""
    Search for analyst reports across multiple firms (Gartner, Forrester, IDC, Everest Group, Quadrant Knowledge Solutions) for a specific category.
    """)

    # User input
    category_input = st.text_input(
        "Enter category:",
        placeholder="e.g., CRM, ABM, RPA, Cloud Security",
        key="category_input"
    )

    # Official site search toggle
    search_official_sites = st.checkbox(
        "🔍 Search official sites for real report names (slower but more accurate)",
        value=False,
        help="When enabled, this will first search official analyst firm websites to find actual report names before generating search queries."
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        search_button = st.button("🔍 Search Category", type="primary")
    with col2:
        clear_button = st.button("🗑️ Clear History")

    if clear_button:
        st.session_state.conversation_history = []
        st.rerun()

    if search_button and category_input:
        with st.spinner("Searching for analyst reports across multiple firms..."):
            try:
                response = requests.post(
                    f"{API_URL}/category-search",
                    json={"category": category_input, "search_official_sites": search_official_sites},
                    timeout=600 if search_official_sites else 180
                )
                response.raise_for_status()
                result = response.json()

                # Store results in session state for export
                st.session_state.category_search_results = result

                # Add to conversation history
                history_entry = {
                    "query": category_input,
                    "search_type": "category",
                    "search_official_sites": search_official_sites,
                    "firms_searched": result.get("firms_searched", []),
                    "official_site_queries": result.get("official_site_queries", []),
                    "real_report_names": result.get("real_report_names", {}),
                    "results": result.get("search_results", {})
                }
                st.session_state.conversation_history.append(history_entry)
                
                # Save to database
                save_search(
                    query=category_input,
                    search_type="category",
                    results=history_entry,
                    metadata={
                        "search_official_sites": search_official_sites,
                        "firms_searched": result.get("firms_searched", [])
                    }
                )

                # Display category searched
                st.subheader(f"📊 Category: {result['category']}")
                st.markdown(f"**Firms Searched:** {', '.join(result['firms_searched'])}")
                st.markdown(f"**Official Site Search:** {'Enabled' if result.get('search_official_sites') else 'Disabled'}")

                # Display official site search results if enabled
                if result.get('search_official_sites') and result.get('official_site_queries'):
                    st.subheader("🔍 Step 1: Official Site Search")
                    
                    official_queries = result.get('official_site_queries', [])
                    for query_info in official_queries:
                        st.code(query_info['query'], language="text")
                    
                    # Display real report names found
                    st.subheader("📋 Step 2: Real Report Names Found")
                    real_report_names = result.get('real_report_names', {})
                    
                    if not real_report_names:
                        st.info("No real report names found from official sites. Will use predefined report types.")
                    else:
                        for firm_name, reports in real_report_names.items():
                            if reports:
                                st.markdown(f"### {firm_name}")
                                for i, report in enumerate(reports, 1):
                                    st.markdown(f"{i}. **{report['name']}**")
                                    st.markdown(f"   - Source: [{report['link']}]({report['link']})")
                            else:
                                st.info(f"No report names found for {firm_name}")

                # Display final search results
                st.subheader("🔍 Step 3: Final Search Results by Firm")
                
                search_results = result.get("search_results", {})
                
                if "error" in search_results:
                    st.error(f"Error: {search_results['error']}")
                elif not search_results:
                    st.warning("No results found. Try a different category.")
                else:
                    for firm_name, firm_results in search_results.items():
                        st.markdown(f"### {firm_name}")
                        
                        if not firm_results:
                            st.info(f"No results found for {firm_name}")
                            continue
                        
                        for report_group in firm_results:
                            report_type = report_group.get("report_type", "")
                            query = report_group.get("query", "")
                            results = report_group.get("results", [])
                            source_link = report_group.get("source_link", "")
                            
                            st.markdown(f"**Report Type:** {report_type}")
                            if source_link:
                                st.markdown(f"**Source:** [{source_link}]({source_link})")
                            st.code(query, language="text")
                            
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

                # Export button
                st.markdown("---")
                if st.session_state.category_search_results:
                    txt_content = format_category_search_results_to_txt(st.session_state.category_search_results)
                    filename = f"category_search_{result['category']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                    st.download_button(
                        label="📥 Export to TXT",
                        data=txt_content,
                        file_name=filename,
                        mime="text/plain"
                    )

            except requests.exceptions.RequestException as e:
                st.error(f"Failed to connect to API: {str(e)}")
                st.error("Make sure the FastAPI server is running on http://localhost:8000")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

# History Page
elif page == "📜 History":
    st.title("📜 Search History")
    
    # Load search history from database
    db_searches = get_all_searches(limit=100)
    
    # Display statistics
    stats = get_search_stats()
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Searches", stats["total_searches"])
    with col2:
        st.metric("Searches This Session", len(st.session_state.conversation_history))
    with col3:
        if stats["last_search_timestamp"]:
            st.metric("Last Search", stats["last_search_timestamp"][:16])
        else:
            st.metric("Last Search", "Never")
    
    # Show searches by type
    if stats["searches_by_type"]:
        st.markdown("**Searches by Type:**")
        type_cols = st.columns(len(stats["searches_by_type"]))
        for i, (search_type, count) in enumerate(stats["searches_by_type"].items()):
            with type_cols[i]:
                st.metric(search_type.replace("_", " ").title(), count)
    
    st.markdown("---")
    
    # Clear all button
    if st.button("🗑️ Clear All History (Database)", type="secondary"):
        if st.confirm("Are you sure you want to delete all search history from the database? This cannot be undone."):
            deleted = clear_all_history()
            st.success(f"Cleared {deleted} records from database")
            st.rerun()
    
    if not db_searches:
        st.info("No search history in database yet. Go to the Search page to perform a search.")
    else:
        for idx, entry in enumerate(db_searches, 1):
            # Get the results from the entry
            results_data = entry.get("results", {})
            
            with st.expander(f"Search #{idx}: {entry['query'][:60]}... ({entry['timestamp'][:16]})", expanded=False):
                # Add download button
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.markdown(f"**Query:** {entry['query']}")
                    st.markdown(f"**Type:** {entry['search_type'].replace('_', ' ').title()}")
                    st.markdown(f"**Timestamp:** {entry['timestamp']}")
                with col2:
                    # Extract links from results
                    results_data = entry.get("results", {})
                    links = []
                    
                    # Handle different search types to extract links
                    if entry.get('search_type') == 'deep':
                        for res in results_data.get('results', []):
                            if isinstance(res, dict) and res.get('link'):
                                links.append(res['link'])
                    elif entry.get('search_type') == 'category':
                        for firm_results in results_data.values():
                            if isinstance(firm_results, list):
                                for report_group in firm_results:
                                    if isinstance(report_group, dict):
                                        for res in report_group.get('results', []):
                                            if isinstance(res, dict) and res.get('link'):
                                                links.append(res['link'])
                    else:  # regular search
                        for query_group in results_data:
                            if isinstance(query_group, dict):
                                for res in query_group.get('results', []):
                                    if isinstance(res, dict) and res.get('link'):
                                        links.append(res['link'])
                    
                    # Remove duplicates while preserving order
                    seen = set()
                    unique_links = []
                    for link in links:
                        if link not in seen:
                            seen.add(link)
                            unique_links.append(link)
                    
                    # Create text file content
                    text_content = f"Query: {entry['query']}\n"
                    text_content += f"Search Type: {entry['search_type']}\n"
                    text_content += f"Timestamp: {entry['timestamp']}\n"
                    text_content += f"Total Links: {len(unique_links)}\n"
                    text_content += "-" * 50 + "\n\n"
                    text_content += "\n".join(unique_links)
                    
                    st.download_button(
                        label="📥 Download Links",
                        data=text_content,
                        file_name=f"search_{entry['id']}_{entry['search_type']}_links.txt",
                        mime="text/plain",
                        key=f"download_{entry['id']}"
                    )
                
                # Handle deep search results
                if entry.get('search_type') == 'deep':
                    st.markdown("**🤖 Deep Search Results**")
                    
                    if results_data.get('analyst_firm'):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Firm", results_data['analyst_firm'])
                        with col2:
                            st.metric("Type", results_data['report_type'])
                        with col3:
                            st.metric("Category", results_data['category'])
                    
                    st.markdown(f"**Iterations:** {results_data.get('iterations', 0)}")
                    
                    if results_data.get('reasoning_trace'):
                        with st.expander("Reasoning Trace"):
                            for i, reasoning in enumerate(results_data['reasoning_trace'], 1):
                                st.markdown(f"{i}. {reasoning}")
                    
                    if results_data.get('search_queries'):
                        with st.expander("Search Queries"):
                            for i, query in enumerate(results_data['search_queries'], 1):
                                st.code(query, language="text")
                    
                    st.markdown("**Results:**")
                    if not results_data.get('results'):
                        st.warning("No results found.")
                    else:
                        for i, res in enumerate(results_data['results'], 1):
                            st.markdown(f"{i}. **{res.get('title', 'No title')}**")
                            st.markdown(f"   - Link: [{res.get('link', 'No link')}]({res.get('link', '#')})")
                            st.markdown(f"   - Snippet: {res.get('snippet', 'No snippet')[:100]}...")
                # Handle category search results
                elif entry.get('search_type') == 'category':
                    st.markdown("**📂 Category Search Results**")
                    
                    if results_data.get('firms_searched'):
                        st.markdown(f"**Firms Searched:** {', '.join(results_data['firms_searched'])}")
                    
                    if results_data.get('search_official_sites'):
                        st.markdown(f"**Official Site Search:** {'Enabled' if results_data['search_official_sites'] else 'Disabled'}")
                    
                    # Show official site search details if enabled
                    if results_data.get('search_official_sites') and results_data.get('official_site_queries'):
                        with st.expander("View Official Site Search Details", expanded=False):
                            st.markdown("**Official Site Queries:**")
                            for query_info in results_data['official_site_queries']:
                                st.code(query_info['query'], language="text")
                            
                            st.markdown("**Real Report Names Found:**")
                            real_report_names = results_data.get('real_report_names', {})
                            for firm_name, reports in real_report_names.items():
                                if reports:
                                    st.markdown(f"### {firm_name}")
                                    for i, report in enumerate(reports, 1):
                                        st.markdown(f"{i}. **{report['name']}**")
                                        st.markdown(f"   - Source: [{report['link']}]({report['link']})")
                    
                    st.markdown("**Results by Firm:**")
                    search_results = results_data.get('results', {})
                    
                    if "error" in search_results:
                        st.error(f"Error: {search_results['error']}")
                    elif not search_results:
                        st.warning("No results found.")
                    else:
                        for firm_name, firm_results in search_results.items():
                            with st.expander(f"{firm_name}", expanded=False):
                                for report_group in firm_results:
                                    report_type = report_group.get("report_type", "")
                                    query = report_group.get("query", "")
                                    results = report_group.get("results", [])
                                    source_link = report_group.get("source_link", "")
                                    
                                    st.markdown(f"**Report Type:** {report_type}")
                                    if source_link:
                                        st.markdown(f"**Source:** [{source_link}]({source_link})")
                                    st.code(query, language="text")
                                    
                                    if not results:
                                        st.warning("No results for this query.")
                                    elif "error" in results[0]:
                                        st.error(results[0]["error"])
                                    else:
                                        for i, res in enumerate(results, 1):
                                            st.markdown(f"{i}. **{res.get('title', 'No title')}**")
                                            st.markdown(f"   - Link: [{res.get('link', 'No link')}]({res.get('link', '#')})")
                                            st.markdown(f"   - Snippet: {res.get('snippet', 'No snippet')[:100]}...")
                                    st.markdown("---")
                else:
                    # Handle regular search results
                    if results_data.get('official_site_query'):
                        st.markdown("**Step 1: Official Site Search**")
                        st.code(results_data['official_site_query'], language="text")

                    if results_data.get('real_report_names'):
                        st.markdown("**Step 2: Real Report Names Found**")
                        for i, report in enumerate(results_data['real_report_names'], 1):
                            if isinstance(report, dict):
                                st.markdown(f"{i}. **{report['name']}**")
                                st.markdown(f"   - Source: [{report['link']}]({report['link']})")
                            else:
                                st.markdown(f"{i}. **{report}**")

                    if results_data.get('search_queries'):
                        st.markdown("**Step 3: Search Queries for Free Versions**")
                        st.markdown(f"**Using {len(results_data['search_queries'])} search queries:**")
                        for i, query in enumerate(results_data['search_queries'], 1):
                            st.code(query, language="text")
                    else:
                        st.markdown("**Step 3: Search Query for Free Versions**")
                        st.code(results_data['search_query'], language="text")

                    st.markdown("**Step 4: Final Search Results**")
                    if not results_data['results']:
                        st.warning("No results found.")
                    else:
                        for query_group in results_data['results']:
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
