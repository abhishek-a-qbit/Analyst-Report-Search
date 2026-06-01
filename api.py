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
    search_results: list


def generate_search_queries(user_query: str) -> List[str]:
    """Generate multiple search query variations using LLM."""
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        temperature=0.3
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert at converting natural language queries into optimized search queries for finding analyst reports from any research firm.

Your task is to generate 3-5 different search query variations that will find PDF reports from analyst firms.

Use your knowledge to identify:
- The analyst firm mentioned (e.g., Gartner, Forrester, IDC, Everest Group, Quadrant Knowledge Solutions, etc.)
- The specific report type for that firm (e.g., Magic Quadrant, The Wave, MarketScape, PEAK Matrix, SPARK Matrix, etc.)
- The category/technology area being researched

Rules:
1. Include the analyst firm name and their specific report type in quotes
2. Include the category/technology area
3. Add "pdf" to find PDF files
4. Add "-site:analystfirm.com" to exclude the official site (this helps find free copies on other sites)
5. Make each query variation slightly different (different wording, synonyms, etc.)
6. Return each query on a separate line

Example:
User: "what are the typical names of analyst reports for abm category from gartner?"
Output:
"Gartner Magic Quadrant for Account-Based Marketing Platforms" pdf -site:gartner.com
"Gartner Magic Quadrant ABM platforms" pdf -site:gartner.com
"Gartner Account Based Marketing Magic Quadrant" pdf -site:gartner.com

Return ONLY the search queries, one per line, nothing else."""),
        ("human", "{user_query}")
    ])
    
    chain = prompt | llm | StrOutputParser()
    queries_text = chain.invoke({"user_query": user_query})
    
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
    """Main function to search for analyst reports using parallel queries."""
    # Generate multiple search query variations
    search_queries = generate_search_queries(user_query)
    
    if not search_queries:
        return {
            "search_query": user_query,
            "search_results": []
        }
    
    # Run searches in parallel using ThreadPoolExecutor
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
        "search_results": deduplicated_results
    }




@app.post("/search", response_model=SearchResponse)
async def search_endpoint(request: SearchRequest):
    """FastAPI endpoint to search for analyst reports."""
    try:
        result = search_analyst_reports(request.query)
        return SearchResponse(
            search_query=result["search_query"],
            search_results=result["search_results"]
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Analyst Report Search API", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
