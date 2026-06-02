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


class SearchResponse(BaseModel):
    search_query: str
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
4. Make each query variation slightly different
5. Return each query on a separate line

Example:
User: "ABM category from Gartner"
Output:
site:gartner.com "Magic Quadrant" "Account-Based Marketing"
site:gartner.com "Magic Quadrant" ABM
site:gartner.com "Account Based Marketing" report

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
5. Make each query variation slightly different (different wording, synonyms, etc.)
6. Return each query on a separate line

Example:
User: "what are the typical names of analyst reports for abm category from gartner?"
Output:
"Gartner Magic Quadrant for Account-Based Marketing Platforms" pdf -site:gartner.com
"Gartner Magic Quadrant ABM platforms" pdf -site:gartner.com
"Gartner Account Based Marketing Magic Quadrant" pdf -site:gartner.com

Return ONLY the search queries, one per line, nothing else."""
    
    result = llm.invoke([
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_query}
    ])
    
    queries_text = result.content
    # Parse the queries (one per line)
    queries = [q.strip() for q in queries_text.strip().split("\n") if q.strip()]
    return queries[:5]  # Limit to 5 queries


def perform_serper_search(search_query: str) -> List[dict]:
    """Execute Serper search with a single query."""
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "q": search_query,
        "num": 10
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = []
        if "organic" in data:
            for item in data["organic"][:10]:
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", "")
                })
        
        return results
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


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
            for query in official_queries[:3]:  # Limit to 3 queries
                print(f"DEBUG: Searching with query: {query}")  # Debug logging
                results = perform_serper_search(query)
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
            for report in real_report_names[:10]:  # Use top 10 report names for better coverage
                domain_to_exclude = firm_info["domain"] if firm_info["domain"] else ""
                if domain_to_exclude:
                    query = f'"{report["name"]}" pdf -site:{domain_to_exclude}'
                else:
                    query = f'"{report["name"]}" pdf'
                search_queries.append(query)
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
        
        # Step 4: Run searches for free versions in parallel
        all_results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_query = {executor.submit(perform_serper_search, q): q for q in search_queries}
            
            for future in future_to_query:
                try:
                    results = future.result(timeout=45)
                    all_results.extend(results)
                except Exception as e:
                    all_results.append({"error": f"Search failed: {str(e)}"})
        
        # Deduplicate results by link
        seen_links = set()
        deduplicated_results = []
        for result in all_results:
            if "error" in result:
                deduplicated_results.append(result)
            elif result.get("link") and result["link"] not in seen_links:
                seen_links.add(result["link"])
                deduplicated_results.append(result)
        
        return {
            "search_query": search_queries[0] if search_queries else user_query,
            "official_site_query": official_site_query,
            "real_report_names": real_report_names,
            "search_results": deduplicated_results
        }
    except Exception as e:
        # Return error information for debugging
        return {
            "search_query": user_query,
            "official_site_query": "",
            "real_report_names": [],
            "search_results": [{"error": f"Search failed: {str(e)}"}]
        }




@app.post("/search")
async def search_endpoint(request: SearchRequest):
    """FastAPI endpoint to search for analyst reports."""
    try:
        result = search_analyst_reports(request.query)
        return {
            "search_query": result["search_query"],
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


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Analyst Report Search API", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
