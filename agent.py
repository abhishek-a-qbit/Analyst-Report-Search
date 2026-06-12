import os
from typing import List, Dict, Any, TypedDict, Annotated
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import requests
import json
from dotenv import load_dotenv
import re
from cache_utils import get_cached_results, cache_results

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")


class AgentState(TypedDict):
    """State for the analyst report search agent."""
    user_query: str
    analyst_firm: str
    report_type: str
    category: str
    search_strategy: str
    search_queries: List[str]
    search_results: List[Dict]
    validated_results: List[Dict]
    iteration: int
    max_iterations: int
    found_valid_results: bool
    reasoning: str


class AnalystReportAgent:
    """Intelligent agent for finding analyst report PDFs across the web."""
    
    def __init__(self):
        self.llm = ChatOpenAI(
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
            temperature=0.1
        )
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("analyze_query", self.analyze_query)
        workflow.add_node("select_strategy", self.select_strategy)
        workflow.add_node("generate_queries", self.generate_queries)
        workflow.add_node("execute_search", self.execute_search)
        workflow.add_node("validate_results", self.validate_results)
        workflow.add_node("decide_next_action", self.decide_next_action)
        workflow.add_node("refine_search", self.refine_search)
        
        # Set entry point
        workflow.set_entry_point("analyze_query")
        
        # Add edges
        workflow.add_edge("analyze_query", "select_strategy")
        workflow.add_edge("select_strategy", "generate_queries")
        workflow.add_edge("generate_queries", "execute_search")
        workflow.add_edge("execute_search", "validate_results")
        workflow.add_edge("validate_results", "decide_next_action")
        
        # Conditional edges
        workflow.add_conditional_edges(
            "decide_next_action",
            self.should_continue,
            {
                "continue": "refine_search",
                "success": END,
                "exhausted": END
            }
        )
        workflow.add_edge("refine_search", "generate_queries")
        
        return workflow.compile(checkpointer=MemorySaver())
    
    def analyze_query(self, state: AgentState) -> AgentState:
        """Analyze the user query to extract key information."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert at analyzing queries for analyst research reports.
            
Extract the following information from the user query:
1. Analyst firm (e.g., Gartner, Forrester, IDC, Everest Group, etc.)
2. Report type (e.g., Magic Quadrant, Wave, MarketScape, PEAK Matrix, etc.)
3. Category/technology area (e.g., ABM, CRM, RPA, cloud security, etc.)

Return ONLY a JSON object with keys: "analyst_firm", "report_type", "category".
If any field is not mentioned, set it to null."""),
            ("user", "{query}")
        ])
        
        chain = prompt | self.llm | StrOutputParser()
        result = chain.invoke({"query": state["user_query"]})
        
        try:
            parsed = json.loads(result)
            state["analyst_firm"] = parsed.get("analyst_firm") or ""
            state["report_type"] = parsed.get("report_type") or ""
            state["category"] = parsed.get("category") or ""
        except:
            state["analyst_firm"] = ""
            state["report_type"] = ""
            state["category"] = ""
        
        state["reasoning"] = f"Analyzed query: firm={state['analyst_firm']}, type={state['report_type']}, category={state['category']}"
        return state
    
    def select_strategy(self, state: AgentState) -> AgentState:
        """Select the best search strategy based on query analysis."""
        strategies = [
            "direct_pdf_search",
            "vendor_blog_search",
            "general_web_search"
        ]
        
        # Start with direct PDF search
        if state["iteration"] == 0:
            state["search_strategy"] = "direct_pdf_search"
        else:
            # Cycle through strategies
            idx = state["iteration"] % len(strategies)
            state["search_strategy"] = strategies[idx]
        
        state["reasoning"] = f"Selected strategy: {state['search_strategy']}"
        return state
    
    def generate_queries(self, state: AgentState) -> AgentState:
        """Generate search queries based on the selected strategy with year filtering (2023-2026)."""
        strategy_prompts = {
            "direct_pdf_search": """Generate 3-5 search queries to find PDF copies of analyst reports.
Focus on finding actual PDF files hosted on vendor sites and legitimate sources.
Include: report name in quotes, "pdf", exclude official analyst site, ALWAYS include year filter (2023 OR 2024 OR 2025 OR 2026).
Exclude: slideshare, scribd, researchgate, medium, blogs, reviews.
Example: "Gartner Magic Quadrant CRM" (2023 OR 2024 OR 2025 OR 2026) pdf -site:gartner.com -site:slideshare.net -site:scribd.com -site:researchgate.net""",
            
            "vendor_blog_search": """Generate 3-5 search queries to find analyst reports mentioned in vendor resources.
Vendors often share analyst reports on their resources/whitepapers pages to show their achievements.
Include: vendor terms, analyst firm name, report type, "resources" or "whitepapers" or "analyst-reports", ALWAYS include year filter (2023 OR 2024 OR 2025 OR 2026).
Exclude: personal blogs, medium, reviews, slideshare, scribd, researchgate.
Example: "Gartner Magic Quadrant" CRM (2023 OR 2024 OR 2025 OR 2026) vendor resources OR whitepapers""",
            
            "general_web_search": """Generate 3-5 broad search queries to find legitimate analyst report sources.
Focus on vendor sites, company resources pages, and legitimate report repositories.
Include: report name, analyst firm, category, ALWAYS include year filter (2023 OR 2024 OR 2025 OR 2026).
Exclude: slideshare, scribd, researchgate, medium, blogs, reviews, social media.
Example: "Gartner Magic Quadrant CRM platforms" (2023 OR 2024 OR 2025 OR 2026) -site:slideshare.net -site:scribd.com -site:researchgate.net"""
        }
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are an expert at generating search queries for finding analyst reports from legitimate sources.
            
{strategy_prompts.get(state['search_strategy'], strategy_prompts['direct_pdf_search'])}

Context:
- Analyst Firm: {state['analyst_firm']}
- Report Type: {state['report_type']}
- Category: {state['category']}

IMPORTANT: 
1. ALWAYS include year filter (2023 OR 2024 OR 2025 OR 2026) in every query to find recent reports only
2. ALWAYS exclude low-quality sources: slideshare, scribd, researchgate, medium, personal blogs, reviews
3. Focus on vendor sites, company resources pages, and legitimate report repositories

Return ONLY the search queries, one per line, nothing else."""),
            ("user", "{query}")
        ])
        
        chain = prompt | self.llm | StrOutputParser()
        result = chain.invoke({"query": state["user_query"]})
        
        queries = [q.strip() for q in result.strip().split("\n") if q.strip()]
        state["search_queries"] = queries[:5]
        state["reasoning"] = f"Generated {len(state['search_queries'])} queries for strategy: {state['search_strategy']}"
        return state
    
    def execute_search(self, state: AgentState) -> AgentState:
        """Execute search queries using Serper API with caching."""
        all_results = []
        
        for query in state["search_queries"]:
            # Check cache first
            cached_results = get_cached_results(query)
            if cached_results is not None:
                print(f"DEBUG: Cache HIT for query: {query[:50]}...")
                for item in cached_results:
                    all_results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", ""),
                        "query_used": query
                    })
                continue
            
            # Cache miss - perform actual search
            try:
                url = "https://google.serper.dev/search"
                headers = {
                    "X-API-KEY": SERPER_API_KEY,
                    "Content-Type": "application/json"
                }
                payload = {
                    "q": query,
                    "num": 10
                }
                
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                query_results = []
                if "organic" in data:
                    for item in data["organic"]:
                        result = {
                            "title": item.get("title", ""),
                            "link": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                            "query_used": query
                        }
                        query_results.append(result)
                        all_results.append(result)
                
                # Cache the results
                cache_results(query, query_results)
                
            except Exception as e:
                print(f"Search failed for query '{query}': {e}")
        
        state["search_results"] = all_results
        state["reasoning"] = f"Executed search, found {len(all_results)} raw results"
        return state
    
    def validate_results(self, state: AgentState) -> AgentState:
        """Validate search results to filter relevant PDFs."""
        if not state["search_results"]:
            state["validated_results"] = []
            state["found_valid_results"] = False
            return state
        
        # First pass: filter by URL patterns
        url_patterns = [
            r'\.pdf$',
            r'slideshare\.net',
            r'researchgate\.net',
            r'academia\.edu',
            r'docdroid\.net',
            r'scribd\.com',
            r'issuu\.com',
            r'medium\.com',
            r'blog\.',
            r'/resources/',
            r'/whitepapers/',
            r'/reports/'
        ]
        
        def is_likely_pdf_or_report(result: Dict) -> bool:
            link = result.get("link", "").lower()
            title = result.get("title", "").lower()
            snippet = result.get("snippet", "").lower()
            
            # Check URL patterns
            for pattern in url_patterns:
                if re.search(pattern, link):
                    return True
            
            # Check for PDF indicators in title/snippet
            pdf_indicators = ['pdf', 'download', 'report', 'analysis', 'research', 'study']
            if any(indicator in title or indicator in snippet for indicator in pdf_indicators):
                return True
            
            # Check for analyst firm mentions
            if state["analyst_firm"].lower() in title or state["analyst_firm"].lower() in snippet:
                return True
            
            return False
        
        filtered = [r for r in state["search_results"] if is_likely_pdf_or_report(r)]
        
        # Second pass: use LLM to score relevance
        if filtered:
            results_text = "\n".join([
                f"{i+1}. Title: {r['title']}\n   Link: {r['link']}\n   Snippet: {r['snippet']}"
                for i, r in enumerate(filtered[:10])
            ])
            
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an expert at identifying legitimate sources for analyst reports.
                
Rate each result on a scale of 1-5 based on:
- Likelihood of containing the actual report or summary
- Credibility of the source
- Relevance to the query

Return ONLY a JSON array of numbers (ratings), one per result."""),
                ("user", "Query: {query}\n\nResults:\n{results}")
            ])
            
            try:
                chain = prompt | self.llm | StrOutputParser()
                ratings_text = chain.invoke({
                    "query": state["user_query"],
                    "results": results_text
                })
                
                ratings = json.loads(ratings_text)
                if isinstance(ratings, list):
                    # Keep only results with rating >= 3
                    validated = [
                        filtered[i] for i, rating in enumerate(ratings)
                        if i < len(filtered) and rating >= 3
                    ]
                    state["validated_results"] = validated
                else:
                    state["validated_results"] = filtered[:5]
            except:
                state["validated_results"] = filtered[:5]
        else:
            state["validated_results"] = []
        
        state["found_valid_results"] = len(state["validated_results"]) > 0
        state["reasoning"] = f"Validated results: {len(state['validated_results'])} valid out of {len(state['search_results'])} total"
        return state
    
    def decide_next_action(self, state: AgentState) -> AgentState:
        """Decide whether to continue searching or return results."""
        if state["found_valid_results"] and len(state["validated_results"]) >= 3:
            state["reasoning"] = "Found sufficient valid results, returning"
            return state
        
        if state["iteration"] >= state["max_iterations"]:
            state["reasoning"] = "Max iterations reached, returning current results"
            return state
        
        state["reasoning"] = f"Insufficient results, continuing (iteration {state['iteration']}/{state['max_iterations']})"
        return state
    
    def should_continue(self, state: AgentState) -> str:
        """Determine the next action."""
        if state["found_valid_results"] and len(state["validated_results"]) >= 3:
            return "success"
        if state["iteration"] >= state["max_iterations"]:
            return "exhausted"
        return "continue"
    
    def refine_search(self, state: AgentState) -> AgentState:
        """Refine the search for the next iteration."""
        state["iteration"] += 1
        
        # Learn from previous results to refine
        if state["search_results"]:
            # Extract patterns from what worked
            successful_domains = []
            for r in state["validated_results"]:
                try:
                    domain = r["link"].split("/")[2]
                    successful_domains.append(domain)
                except:
                    pass
            
            if successful_domains:
                state["reasoning"] = f"Refining search, successful domains: {successful_domains}"
            else:
                state["reasoning"] = f"Refining search with new strategy"
        else:
            state["reasoning"] = f"Refining search with new strategy"
        
        return state
    
    def search(self, user_query: str, max_iterations: int = 5) -> Dict[str, Any]:
        """Execute the agent search workflow."""
        initial_state: AgentState = {
            "user_query": user_query,
            "analyst_firm": "",
            "report_type": "",
            "category": "",
            "search_strategy": "",
            "search_queries": [],
            "search_results": [],
            "validated_results": [],
            "iteration": 0,
            "max_iterations": max_iterations,
            "found_valid_results": False,
            "reasoning": ""
        }
        
        config = {"configurable": {"thread_id": "analyst_search"}}
        final_state = self.graph.invoke(initial_state, config)
        
        return {
            "user_query": user_query,
            "analyst_firm": final_state["analyst_firm"],
            "report_type": final_state["report_type"],
            "category": final_state["category"],
            "iterations": final_state["iteration"],
            "validated_results": final_state["validated_results"],
            "all_search_queries": self._collect_all_queries(final_state),
            "reasoning_trace": self._build_reasoning_trace(final_state)
        }
    
    def _collect_all_queries(self, state: AgentState) -> List[str]:
        """Collect all queries used during the search."""
        # This would need to be tracked during execution
        # For now, return the last set
        return state.get("search_queries", [])
    
    def _build_reasoning_trace(self, state: AgentState) -> List[str]:
        """Build a trace of the agent's reasoning."""
        # This would need to be tracked during execution
        return [state.get("reasoning", "")]


# Convenience function for direct usage
def search_analyst_reports_deep(user_query: str, max_iterations: int = 5) -> Dict[str, Any]:
    """Search for analyst reports using the intelligent agent."""
    agent = AnalystReportAgent()
    return agent.search(user_query, max_iterations)


if __name__ == "__main__":
    # Test the agent
    result = search_analyst_reports_deep(
        "Gartner Magic Quadrant for Account-Based Marketing Platforms",
        max_iterations=3
    )
    print(json.dumps(result, indent=2))
