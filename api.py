import os
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import requests
import json
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from bs4 import BeautifulSoup
import trafilatura
import re
from agent import AnalystReportAgent, tweak_search_query

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

app = FastAPI(title="Analyst Report Search API")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchRequest(BaseModel):
    query: str


class DeepSearchRequest(BaseModel):
    query: str
    max_iterations: int = 5


class CategorySearchRequest(BaseModel):
    category: str
    search_official_sites: bool = False


class WideNetSearchRequest(BaseModel):
    category: str = ""
    year: str = ""


class SearchResponse(BaseModel):
    search_query: str
    search_queries: list = []  # All search queries used
    official_site_query: str
    real_report_names: list  # List of dicts with 'name' and 'link'
    search_results: list


def identify_analyst_firm(user_query: str) -> dict:
    """Identify the analyst organization and their domain from the user query."""
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        temperature=0.1
    )
    
    system_message = """You are an expert at identifying analyst research organizations from user queries.

Identify the analyst organization mentioned and return their official domain.

Common organizations and their domains:
- Gartner: gartner.com
- Forrester: forrester.com
- IDC: idc.com
- Everest Group: everestgrp.com
- Quadrant Knowledge Solutions: quadrant-solutions.com
- G2: g2.com
- Capterra: capterra.com
- Omdia: omdia.com
- 451 Research: 451research.com
- Frost & Sullivan: frost.com
- Aberdeen: aberdeen.com
- Nucleus Research: nucleusresearch.com
- KLAS Research: klasresearch.com
- Deloitte: deloitte.com
- PwC: pwc.com
- EY: ey.com
- KPMG: kpmg.com

Return ONLY a JSON object with keys "organization" and "domain". If no specific organization is mentioned, return {"organization": "general", "domain": ""}."""
    
    result = llm.invoke([
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_query}
    ])
    
    try:
        import json
        data = json.loads(result.content)
        # Convert "organization" key to "firm" for compatibility
        if "organization" in data:
            return {"firm": data["organization"], "domain": data["domain"]}
        return data
    except:
        return {"firm": "general", "domain": ""}


def search_official_site(user_query: str, firm_info: dict) -> List[str]:
    """Search official analyst firm site for real report names."""
    if firm_info["domain"] == "":
        return []
    
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        temperature=0.3
    )
    
    system_message = """You are an expert at generating search queries to find real analyst report names on official firm websites.

Generate 3-5 search queries that will find actual report titles on the official analyst firm website.

Rules:
1. Include the vendor name and their specific report type (e.g., Magic Quadrant, The Wave, MarketScape, etc.)
2. Include the category/technology area
3. Add "site:" followed by the domain to search only the official site
4. Add year filtering: include "(2023 OR 2024 OR 2025)" to ensure results are from 2023 or later
5. Make each query variation slightly different
6. Return each query on a separate line

Example:
User: "ABM category from Gartner"
Output:
site:gartner.com "Magic Quadrant" "Account-Based Marketing" (2023 OR 2024 OR 2025)
site:gartner.com "Magic Quadrant" ABM (2023 OR 2024 OR 2025)
site:gartner.com "Account Based Marketing" report (2023 OR 2024 OR 2025)

Return ONLY the search queries, one per line, nothing else."""
    
    user_message = f"User query: {user_query}\nVendor: {firm_info['firm']}\nDomain: {firm_info['domain']}"
    
    result = llm.invoke([
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ])
    
    queries_text = result.content
    queries = [q.strip() for q in queries_text.strip().split("\n") if q.strip()]
    return queries[:5]


def scrape_report_titles(url: str) -> List[dict]:
    """Scrape report titles from a webpage and return with source link."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Use trafilatura to extract main content (better than BeautifulSoup for content extraction)
        page_text = trafilatura.extract(response.text, include_comments=False, include_tables=False)
        
        if not page_text:
            # Fallback to BeautifulSoup if trafilatura fails
            soup = BeautifulSoup(response.text, 'html.parser')
            page_text = soup.get_text(separator=' ', strip=True)
        
        # Limit text length to avoid token limits
        page_text = page_text[:5000]
        
        # Use LLM to extract actual report titles
        llm = ChatOpenAI(
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
            temperature=0.1
        )
        
        system_message = """You are an expert at extracting analyst report titles from web pages.

Extract actual analyst report titles from the provided page content. Look for:
- Full report names (e.g., "IDC MarketScape: Worldwide CRM Platforms 2023")
- Report types with years (e.g., "Magic Quadrant 2023", "The Wave 2024")
- Specific research document titles

DO NOT extract:
- Team names (e.g., "IDC Retail Insights Team")
- Generic phrases (e.g., "Achieving ROI with GenAI")
- Navigation elements
- Author names

Return ONLY a JSON array of report title strings. If no valid report titles are found, return an empty array []."""
        
        result = llm.invoke([
            {"role": "system", "content": system_message},
            {"role": "user", "content": f"Page URL: {url}\n\nPage Content:\n{page_text}"}
        ])
        
        print(f"DEBUG: LLM response for {url}: {result.content[:200]}")  # Debug logging
        
        try:
            import json
            titles = json.loads(result.content)
            if isinstance(titles, list):
                print(f"DEBUG: Extracted {len(titles)} titles from {url}")  # Debug logging
                return [{"name": title, "link": url} for title in titles[:5]]
        except Exception as e:
            print(f"DEBUG: Failed to parse JSON from LLM: {e}")  # Debug logging
            pass
        
        # Fallback to simple extraction if LLM fails
        soup = BeautifulSoup(response.text, 'html.parser')
        reports = []
        for tag in soup.find_all(['h1', 'h2', 'h3']):
            text = tag.get_text(strip=True)
            # Filter out common non-report patterns
            if (len(text) > 30 and len(text) < 200 and 
                not any(skip in text.lower() for skip in ['team', 'insights', 'analyst', 'author', 'about', 'contact'])):
                reports.append({"name": text, "link": url})
        
        print(f"DEBUG: Fallback extracted {len(reports)} titles from {url}")  # Debug logging
        return reports[:3]  # Return fewer results from fallback
    except Exception as e:
        print(f"DEBUG: Error scraping {url}: {e}")  # Debug logging
        return []


def generate_search_queries(user_query: str) -> List[str]:
    """Generate multiple search query variations using LLM."""
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        temperature=0.3
    )
    
    system_message = """You are an expert at converting natural language queries into optimized search queries for finding analyst reports from any research source.

Your task is to generate 3-5 different search query variations that will find PDF reports from analyst sources.

Use your knowledge to identify:
- The analyst source mentioned (e.g., Gartner, Forrester, IDC, Everest Group, Quadrant Knowledge Solutions, etc.)
- The specific report type for that source (e.g., Magic Quadrant, The Wave, MarketScape, PEAK Matrix, SPARK Matrix, etc.)
- The category/technology area being researched

Rules:
1. Include the analyst source name and their specific report type in quotes
2. Include the category/technology area
3. Add "pdf" to find PDF files
4. Add "-site:analystsource.com" to exclude the official site (this helps find free copies on other sites)
5. Add year filtering: include "(2023 OR 2024 OR 2025)" to ensure results are from 2023 or later
6. Make each query variation slightly different (different wording, synonyms, etc.)
7. Return each query on a separate line

Example:
User: "what are the typical names of analyst reports for abm category from gartner?"
Output:
"Gartner Magic Quadrant for Account-Based Marketing Platforms" pdf -site:gartner.com (2023 OR 2024 OR 2025)
"Gartner Magic Quadrant ABM platforms" pdf -site:gartner.com (2023 OR 2024 OR 2025)
"Gartner Account Based Marketing Magic Quadrant" pdf -site:gartner.com (2023 OR 2024 OR 2025)

Return ONLY the search queries, one per line, nothing else."""
    
    result = llm.invoke([
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_query}
    ])
    
    queries_text = result.content
    # Parse the queries (one per line)
    queries = [q.strip() for q in queries_text.strip().split("\n") if q.strip()]
    return queries[:5]  # Limit to 5 queries


def perform_serper_search(search_query: str, max_retries: int = 4) -> tuple:
    """Execute Serper search with retry mechanism and query tweaking.
    
    Returns:
        tuple: (results: List[dict], all_queries_used: List[str])
    """
    all_queries_used = [search_query]
    
    for attempt in range(max_retries):
        url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": SERPER_API_KEY,
            "Content-Type": "application/json"
        }
        payload = {
            "q": search_query,
            "num": 5
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            results = []
            if "organic" in data:
                for item in data["organic"][:5]:
                    results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", "")
                    })
            
            print(f"DEBUG: Search attempt {attempt + 1} for '{search_query[:50]}...' returned {len(results)} results")
            
            # If we got results, return them
            if results:
                return results, all_queries_used
            
            # If no results and not the last attempt, tweak the query
            if attempt < max_retries - 1:
                print(f"DEBUG: No results found, tweaking query for next attempt")
                search_query = tweak_search_query(search_query, attempt + 1)
                all_queries_used.append(search_query)
            else:
                print(f"DEBUG: No results after {max_retries} attempts")
                return results, all_queries_used
                
        except Exception as e:
            print(f"DEBUG: Search failed on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                search_query = tweak_search_query(search_query, attempt + 1)
                all_queries_used.append(search_query)
            else:
                return [{"error": f"Search failed after {max_retries} attempts: {str(e)}"}], all_queries_used
    
    return [], all_queries_used


def search_analyst_reports(user_query: str):
    """Main function to search for analyst reports using two-step process."""
    try:
        # Step 1: Identify the analyst firm
        firm_info = identify_analyst_firm(user_query)
        
        # Step 2: Search official site for real report names
        real_report_names = []
        official_site_query = ""
        if firm_info["domain"]:
            official_queries = search_official_site(user_query, firm_info)
            official_site_query = official_queries[0] if official_queries else ""
            
            print(f"DEBUG: Official queries generated: {official_queries}")  # Debug logging
            
            # Search official site and scrape titles
            all_search_queries = []
            for query in official_queries[:3]:  # Limit to 3 queries
                print(f"DEBUG: Searching with query: {query}")  # Debug logging
                results, queries_used = perform_serper_search(query)
                all_search_queries.extend(queries_used)
                print(f"DEBUG: Got {len(results)} results from Serper")  # Debug logging
                
                for result in results:
                    if result.get("link"):
                        print(f"DEBUG: Scraping URL: {result['link']}")  # Debug logging
                        # First, try to use the title from Serper results directly
                        if result.get("title") and len(result["title"]) > 20:
                            real_report_names.append({"name": result["title"], "link": result["link"]})
                            print(f"DEBUG: Added title from Serper: {result['title'][:50]}")  # Debug logging
                        else:
                            # Only scrape if Serper title is not good enough
                            reports = scrape_report_titles(result["link"])
                            real_report_names.extend(reports)
            
            print(f"DEBUG: Total report names before dedup: {len(real_report_names)}")  # Debug logging
            
            # Deduplicate report names by name
            seen_names = set()
            deduplicated_reports = []
            for report in real_report_names:
                if isinstance(report, dict) and "name" in report:
                    if report["name"] not in seen_names:
                        seen_names.add(report["name"])
                        deduplicated_reports.append(report)
            real_report_names = deduplicated_reports
            
            print(f"DEBUG: Total report names after dedup: {len(real_report_names)}")  # Debug logging
        
        # Step 3: Generate search queries using real report names
        if real_report_names:
            # Use real report names to search for free versions
            search_queries = []
            print(f"DEBUG: Generating search queries from {len(real_report_names)} report names")  # Debug logging
            for report in real_report_names[:10]:  # Use top 10 report names for better coverage
                domain_to_exclude = firm_info["domain"] if firm_info["domain"] else ""
                if domain_to_exclude:
                    query = f'"{report["name"]}" pdf -site:{domain_to_exclude} (2023 OR 2024 OR 2025)'
                else:
                    query = f'"{report["name"]}" pdf (2023 OR 2024 OR 2025)'
                search_queries.append(query)
                print(f"DEBUG: Generated query: {query[:80]}...")  # Debug logging
            print(f"DEBUG: Total search queries generated: {len(search_queries)}")  # Debug logging
        else:
            # Fallback to original method if no real names found
            search_queries = generate_search_queries(user_query)
        
        if not search_queries:
            return {
                "search_query": user_query,
                "official_site_query": official_site_query,
                "real_report_names": real_report_names,
                "search_results": []
            }
        
        # Step 4: Run searches for free versions in parallel and group by query
        results_by_query = []
        all_queries_tried = search_queries.copy()  # Track all queries tried
        print(f"DEBUG: Running {len(search_queries)} search queries in parallel")  # Debug logging
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_query = {executor.submit(perform_serper_search, q): q for q in search_queries}
            
            for future in future_to_query:
                try:
                    results, queries_used = future.result(timeout=45)
                    query = future_to_query[future]
                    all_queries_tried.extend(queries_used[1:])  # Add tweaked queries (skip the first as it's already in search_queries)
                    print(f"DEBUG: Got {len(results)} results from query: {query[:50]}...")  # Debug logging
                    results_by_query.append({
                        "query": query,
                        "results": results,
                        "queries_used": queries_used  # Include all queries tried for this search
                    })
                except Exception as e:
                    query = future_to_query[future]
                    results_by_query.append({
                        "query": query,
                        "results": [{"error": f"Search failed: {str(e)}"}],
                        "queries_used": [query]
                    })
        
        print(f"DEBUG: Total query groups: {len(results_by_query)}")  # Debug logging
        
        return {
            "search_query": search_queries[0] if search_queries else user_query,
            "search_queries": all_queries_tried,  # Return all search queries including tweaked ones
            "official_site_query": official_site_query,
            "real_report_names": real_report_names,
            "search_results": results_by_query  # Return results grouped by query
        }
    except Exception as e:
        # Return error information for debugging
        return {
            "search_query": user_query,
            "search_queries": [],
            "official_site_query": "",
            "real_report_names": [],
            "search_results": [{"error": f"Search failed: {str(e)}"}]
        }


def wide_net_search(category: str = "", year: str = ""):
    """Cast a wide net to find analyst report PDFs across major firms and search for free copies on vendor sites."""
    try:
        # Parse comma-separated categories and years
        categories = [c.strip() for c in category.split(",") if c.strip()] if category else [""]
        years = [y.strip() for y in year.split(",") if y.strip()] if year else ["2023", "2024", "2025"]  # Default to recent years if not specified
        
        # Define analyst firms and their report types (restricted to 5 firms as requested)
        analyst_firms = [
            {"name": "Gartner", "domain": "gartner.com", "report_types": ["Magic Quadrant", "Market Guide", "Critical Capabilities", "Market Share", "Vendor Guide", "Hype Cycle", "Market Insight", "Emerging Technologies", "Strategic Planning Assumption", "Trend Insight"]},
            {"name": "Forrester", "domain": "forrester.com", "report_types": ["The Wave", "Now Tech", "New Wave", "Vendor Landscape", "Total Economic Impact", "Tech Radar", "Forrester Wave", "Now Tech", "Budget Planner"]},
            {"name": "IDC", "domain": "idc.com", "report_types": ["MarketScape", "Vendor Spotlight", "Worldwide", "Market Share", "FutureScape", "IDC PlanScape", "Market Note", "Executive Summary", "Forecast"]},
            {"name": "Everest Group", "domain": "everestgrp.com", "report_types": ["PEAK Matrix", "Market Vista", "Enterprise Insights", "Digital Impact", "Source", "Peak Matrix", "Market Assessment"]},
            {"name": "Quadrant Knowledge Solutions", "domain": "quadrant-solutions.com", "report_types": ["SPARK Matrix", "Market Share", "Market Landscape", "Strategic Assessment", "Competitive Landscape"]}
        ]
        
        # Step 1: Generate broad search queries to find report titles
        broad_search_queries = []
        
        for firm in analyst_firms:
            for report_type in firm["report_types"]:
                # Generate queries for all combinations of categories and years
                for cat in categories:
                    for yr in years:
                        # Generate queries to find actual report titles
                        if cat and yr:
                            query = f'"{firm["name"]} {report_type} {cat} {yr}"'
                        elif cat:
                            query = f'"{firm["name"]} {report_type} {cat}" (2023 OR 2024 OR 2025)'
                        elif yr:
                            query = f'"{firm["name"]} {report_type} {yr}"'
                        else:
                            query = f'"{firm["name"]} {report_type}" (2023 OR 2024 OR 2025)'
                        
                        broad_search_queries.append({
                            "query": query,
                            "firm": firm["name"],
                            "report_type": report_type,
                            "domain": firm["domain"],
                            "category": cat,
                            "year": yr
                        })
        
        print(f"DEBUG: Generated {len(broad_search_queries)} broad search queries")  # Debug logging
        
        # Step 2: Execute broad searches to find report titles with validation
        all_report_titles = []
        
        # Define domains to exclude (non-analyst sources)
        excluded_domains = [
            'reddit.com', 'twitter.com', 'x.com', 'facebook.com', 'linkedin.com',
            'medium.com', 'substack.com', 'wordpress.com', 'blogspot.com',
            'youtube.com', 'tiktok.com', 'instagram.com', 'pinterest.com',
            'quora.com', 'stackexchange.com', 'github.com', 'gitlab.com'
        ]
        
        def is_valid_analyst_source_for_title(result: dict) -> bool:
            """Check if a result is from a valid source for extracting report titles."""
            link = result.get("link", "").lower()
            
            # Exclude social media and low-quality sources
            for excluded in excluded_domains:
                if excluded in link:
                    return False
            
            # ONLY allow official analyst firm domains for title extraction
            # This prevents vendor pages from polluting the report titles list
            analyst_domains = ['gartner.com', 'forrester.com', 'idc.com', 'everestgrp.com', 
                            'quadrant-solutions.com']
            if any(domain in link for domain in analyst_domains):
                return True
            
            # NO vendor pages allowed for title extraction
            # Vendor pages will be searched in the free copy phase using -site: exclusion
            return False
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_query = {executor.submit(perform_serper_search, item["query"]): item for item in broad_search_queries[:50]}  # Limit to 50 for more comprehensive results
            
            for future in future_to_query:
                try:
                    results, queries_used = future.result(timeout=45)
                    item = future_to_query[future]
                    
                    print(f"DEBUG: Got {len(results)} results for {item['firm']} {item['report_type']}")  # Debug logging
                    
                    # Filter results to only include valid sources
                    valid_results = [r for r in results if is_valid_analyst_source_for_title(r)]
                    print(f"DEBUG: Filtered to {len(valid_results)} valid sources from {len(results)} total")  # Debug logging
                    
                    # Extract titles from valid results
                    for result in valid_results:
                        if result.get("title") and len(result["title"]) > 20:
                            all_report_titles.append({
                                "title": result["title"],
                                "firm": item["firm"],
                                "report_type": item["report_type"],
                                "domain": item["domain"],
                                "source_link": result.get("link", "")
                            })
                except Exception as e:
                    print(f"DEBUG: Error in broad search: {e}")  # Debug logging
        
        print(f"DEBUG: Found {len(all_report_titles)} report titles from broad search")  # Debug logging
        
        # Step 3: Deduplicate report titles
        seen_titles = set()
        deduplicated_titles = []
        for report in all_report_titles:
            title_lower = report["title"].lower()
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                deduplicated_titles.append(report)
        
        print(f"DEBUG: After deduplication: {len(deduplicated_titles)} unique titles")  # Debug logging
        
        # Step 4: Generate -site: queries to find free copies on vendor sites
        free_copy_queries = []
        
        for report in deduplicated_titles[:50]:  # Limit to top 50 for more comprehensive results
            # Generate query excluding the official analyst site
            query = f'"{report["title"]}" pdf -site:{report["domain"]}'
            free_copy_queries.append({
                "query": query,
                "original_title": report["title"],
                "firm": report["firm"],
                "report_type": report["report_type"],
                "source_link": report["source_link"]
            })
        
        print(f"DEBUG: Generated {len(free_copy_queries)} free copy search queries")  # Debug logging
        
        # Step 5: Execute free copy searches with validation
        free_copy_results = []
        
        # Define domains to exclude (non-analyst sources)
        excluded_domains = [
            'reddit.com', 'twitter.com', 'x.com', 'facebook.com', 'linkedin.com',
            'medium.com', 'substack.com', 'wordpress.com', 'blogspot.com',
            'youtube.com', 'tiktok.com', 'instagram.com', 'pinterest.com',
            'quora.com', 'stackexchange.com', 'github.com', 'gitlab.com'
        ]
        
        def is_valid_analyst_source(result: dict) -> bool:
            """Check if a result is from a valid analyst report source."""
            link = result.get("link", "").lower()
            title = result.get("title", "").lower()
            snippet = result.get("snippet", "").lower()
            
            # Exclude social media and low-quality sources
            for excluded in excluded_domains:
                if excluded in link:
                    return False
            
            # Check for PDF extension
            if link.endswith('.pdf'):
                return True
            
            # Check for vendor/resource pages (these often host reports)
            vendor_indicators = ['/resources/', '/whitepapers/', '/reports/', '/analyst-reports/', 
                               '/research/', '/insights/', '/assets/', '/downloads/']
            if any(indicator in link for indicator in vendor_indicators):
                return True
            
            # Check for PDF in title or snippet
            if 'pdf' in title or 'pdf' in snippet:
                return True
            
            # Check for analyst report indicators in title/snippet
            report_indicators = ['magic quadrant', 'the wave', 'marketscape', 'peak matrix', 
                                'spark matrix', 'vendor guide', 'market guide', 'analyst report']
            if any(indicator in title or indicator in snippet for indicator in report_indicators):
                return True
            
            return False
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_query = {executor.submit(perform_serper_search, item["query"]): item for item in free_copy_queries}
            
            for future in future_to_query:
                try:
                    results, queries_used = future.result(timeout=45)
                    item = future_to_query[future]
                    
                    print(f"DEBUG: Got {len(results)} free copy results for: {item['original_title'][:50]}...")  # Debug logging
                    
                    # Filter results to only include valid analyst sources
                    valid_results = [r for r in results if is_valid_analyst_source(r)]
                    print(f"DEBUG: Filtered to {len(valid_results)} valid results from {len(results)} total")  # Debug logging
                    
                    free_copy_results.append({
                        "original_title": item["original_title"],
                        "firm": item["firm"],
                        "report_type": item["report_type"],
                        "source_link": item["source_link"],
                        "search_query": item["query"],
                        "queries_used": queries_used,
                        "results": valid_results
                    })
                except Exception as e:
                    print(f"DEBUG: Error in free copy search: {e}")  # Debug logging
        
        print(f"DEBUG: Completed wide net search with {len(free_copy_results)} result groups")  # Debug logging
        
        return {
            "category": category,
            "year": year,
            "categories": categories,
            "years": years,
            "total_titles_found": len(deduplicated_titles),
            "total_searches_performed": len(free_copy_queries),
            "report_titles": deduplicated_titles,
            "free_copy_results": free_copy_results
        }
    except Exception as e:
        import traceback
        print(f"DEBUG: Wide net search error: {e}")  # Debug logging
        return {
            "category": category,
            "year": year,
            "categories": categories,
            "years": years,
            "total_titles_found": 0,
            "total_searches_performed": 0,
            "report_titles": [],
            "free_copy_results": [{"error": f"Wide net search failed: {str(e)}", "details": traceback.format_exc()}]
        }


def category_search(category: str, search_official_sites: bool = False):
    """Search for analyst reports across multiple firms for a given category."""
    try:
        # Define analyst firms and their domains
        analyst_firms = [
            {"name": "Gartner", "domain": "gartner.com", "report_types": ["Magic Quadrant", "Market Guide", "Critical Capabilities"]},
            {"name": "Forrester", "domain": "forrester.com", "report_types": ["The Wave", "Now Tech", "New Wave"]},
            {"name": "IDC", "domain": "idc.com", "report_types": ["MarketScape", "Vendor Spotlight", "Worldwide"]},
            {"name": "Everest Group", "domain": "everestgrp.com", "report_types": ["PEAK Matrix", "Market Vista"]},
            {"name": "Quadrant Knowledge Solutions", "domain": "quadrant-solutions.com", "report_types": ["SPARK Matrix"]}
        ]
        
        # Step 1: Search official sites for real report names if enabled
        real_report_names_by_firm = {}
        official_site_queries = []
        
        if search_official_sites:
            print(f"DEBUG: Searching official sites for real report names")  # Debug logging
            
            for firm in analyst_firms:
                firm_report_names = []
                for report_type in firm["report_types"]:
                    # Generate official site query with year filtering
                    official_query = f'site:{firm["domain"]} "{report_type}" "{category}" (2023 OR 2024 OR 2025)'
                    official_site_queries.append({
                        "query": official_query,
                        "firm": firm["name"],
                        "report_type": report_type
                    })
                    
                    # Search official site
                    try:
                        results, _ = perform_serper_search(official_query)
                        print(f"DEBUG: Got {len(results)} results from {firm['domain']} for {report_type}")  # Debug logging
                        
                        # Scrape report titles from results
                        for result in results:
                            if result.get("link"):
                                if result.get("title") and len(result["title"]) > 20:
                                    firm_report_names.append({"name": result["title"], "link": result["link"]})
                                else:
                                    reports = scrape_report_titles(result["link"])
                                    firm_report_names.extend(reports)
                    except Exception as e:
                        print(f"DEBUG: Error searching {firm['domain']}: {e}")  # Debug logging
                
                # Deduplicate report names
                seen_names = set()
                deduplicated = []
                for report in firm_report_names:
                    if isinstance(report, dict) and "name" in report:
                        if report["name"] not in seen_names:
                            seen_names.add(report["name"])
                            deduplicated.append(report)
                
                real_report_names_by_firm[firm["name"]] = deduplicated
                print(f"DEBUG: Found {len(deduplicated)} real report names for {firm['name']}")  # Debug logging
        
        # Step 2: Generate search queries
        all_search_queries = []
        
        if search_official_sites and real_report_names_by_firm:
            # Use real report names to generate queries
            for firm in analyst_firms:
                firm_names = real_report_names_by_firm.get(firm["name"], [])
                for report in firm_names[:5]:  # Use top 5 report names per firm
                    query = f'"{report["name"]}" pdf -site:{firm["domain"]} (2023 OR 2024 OR 2025)'
                    all_search_queries.append({
                        "query": query,
                        "firm": firm["name"],
                        "report_type": "Real Report Name",
                        "source_link": report.get("link", "")
                    })
        else:
            # Use predefined report types
            for firm in analyst_firms:
                for report_type in firm["report_types"]:
                    query = f'"{firm["name"]} {report_type} {category}" pdf -site:{firm["domain"]} (2023 OR 2024 OR 2025)'
                    all_search_queries.append({
                        "query": query,
                        "firm": firm["name"],
                        "report_type": report_type
                    })
        
        print(f"DEBUG: Generated {len(all_search_queries)} category search queries")  # Debug logging
        
        # Step 3: Run searches in parallel
        results_by_firm = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_firm = {executor.submit(perform_serper_search, item["query"]): item for item in all_search_queries}
            
            for future in future_to_firm:
                try:
                    results, queries_used = future.result(timeout=45)
                    item = future_to_firm[future]
                    firm_name = item["firm"]
                    report_type = item["report_type"]
                    
                    if firm_name not in results_by_firm:
                        results_by_firm[firm_name] = []
                    
                    print(f"DEBUG: Got {len(results)} results for {firm_name} {report_type}")  # Debug logging
                    
                    result_entry = {
                        "report_type": report_type,
                        "query": item["query"],
                        "results": results,
                        "queries_used": queries_used
                    }
                    
                    if "source_link" in item:
                        result_entry["source_link"] = item["source_link"]
                    
                    results_by_firm[firm_name].append(result_entry)
                except Exception as e:
                    item = future_to_firm[future]
                    firm_name = item["firm"]
                    report_type = item["report_type"]
                    
                    if firm_name not in results_by_firm:
                        results_by_firm[firm_name] = []
                    
                    results_by_firm[firm_name].append({
                        "report_type": report_type,
                        "query": item["query"],
                        "results": [{"error": f"Search failed: {str(e)}"}],
                        "queries_used": [item["query"]]
                    })
        
        print(f"DEBUG: Total firms searched: {len(results_by_firm)}")  # Debug logging
        
        return {
            "category": category,
            "firms_searched": [firm["name"] for firm in analyst_firms],
            "search_official_sites": search_official_sites,
            "official_site_queries": official_site_queries if search_official_sites else [],
            "real_report_names": real_report_names_by_firm if search_official_sites else {},
            "search_results": results_by_firm
        }
    except Exception as e:
        # Return error information for debugging
        return {
            "category": category,
            "firms_searched": [],
            "search_official_sites": search_official_sites,
            "official_site_queries": [],
            "real_report_names": {},
            "search_results": {"error": f"Category search failed: {str(e)}"}
        }




@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """FastAPI endpoint to search for analyst reports."""
    try:
        result = search_analyst_reports(request.query)
        return {
            "search_query": result["search_query"],
            "search_queries": result.get("search_queries", []),
            "official_site_query": result["official_site_query"],
            "real_report_names": result["real_report_names"],
            "search_results": result["search_results"]
        }
    except Exception as e:
        import traceback
        error_detail = {
            "error": str(e),
            "traceback": traceback.format_exc()
        }
        return {
            "search_query": request.query,
            "official_site_query": "",
            "real_report_names": [],
            "search_results": [{"error": f"API Error: {str(e)}", "details": traceback.format_exc()}]
        }


@app.post("/deep-search")
async def deep_search_endpoint(request: DeepSearchRequest):
    """FastAPI endpoint for intelligent deep search using the agent."""
    try:
        agent = AnalystReportAgent()
        result = agent.search(request.query, max_iterations=request.max_iterations)
        return {
            "user_query": result["user_query"],
            "analyst_firm": result["analyst_firm"],
            "report_type": result["report_type"],
            "category": result["category"],
            "iterations": result["iterations"],
            "search_queries": result["all_search_queries"],
            "reasoning_trace": result["reasoning_trace"],
            "search_results": result["validated_results"]
        }
    except Exception as e:
        import traceback
        return {
            "user_query": request.query,
            "analyst_firm": "",
            "report_type": "",
            "category": "",
            "iterations": 0,
            "search_queries": [],
            "reasoning_trace": [f"Error: {str(e)}"],
            "search_results": [{"error": f"Deep search failed: {str(e)}", "details": traceback.format_exc()}]
        }


@app.post("/category-search")
async def category_search_endpoint(request: CategorySearchRequest):
    """FastAPI endpoint for category-based search across multiple analyst firms."""
    try:
        result = category_search(request.category, request.search_official_sites)
        return {
            "category": result["category"],
            "firms_searched": result["firms_searched"],
            "search_official_sites": result["search_official_sites"],
            "official_site_queries": result["official_site_queries"],
            "real_report_names": result["real_report_names"],
            "search_results": result["search_results"]
        }
    except Exception as e:
        import traceback
        return {
            "category": request.category,
            "firms_searched": [],
            "search_official_sites": request.search_official_sites,
            "official_site_queries": [],
            "real_report_names": {},
            "search_results": {"error": f"Category search failed: {str(e)}", "details": traceback.format_exc()}
        }


@app.post("/wide-net-search")
async def wide_net_search_endpoint(request: WideNetSearchRequest):
    """FastAPI endpoint for wide-net search across all analyst firms to find free PDF copies."""
    try:
        result = wide_net_search(request.category, request.year)
        return {
            "category": result["category"],
            "year": result["year"],
            "categories": result.get("categories", []),
            "years": result.get("years", []),
            "total_titles_found": result["total_titles_found"],
            "total_searches_performed": result["total_searches_performed"],
            "report_titles": result["report_titles"],
            "free_copy_results": result["free_copy_results"]
        }
    except Exception as e:
        import traceback
        return {
            "category": request.category,
            "year": request.year,
            "categories": [],
            "years": [],
            "total_titles_found": 0,
            "total_searches_performed": 0,
            "report_titles": [],
            "free_copy_results": {"error": f"Wide net search failed: {str(e)}", "details": traceback.format_exc()}
        }


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Analyst Report Search API", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
