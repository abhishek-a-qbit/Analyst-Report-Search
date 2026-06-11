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

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")


def tweak_search_query(original_query: str, attempt: int) -> str:
    """Use LLM to progressively simplify the search query when no results are found."""
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=OPENAI_MODEL,
        temperature=0.3
    )
    
    system_message = """You are an expert at simplifying search queries to find results when the original query returns no results.

Your task is to simplify the given search query by progressively removing specific elements while keeping the core search intent.

Rules:
1. Remove analyst firm names from quoted titles (e.g., change "Critical Capabilities for Account-Based Marketing Platforms - Gartner" to "Critical Capabilities for Account-Based Marketing Platforms")
2. Remove specific report type qualifiers if they're too specific
3. Keep the "pdf" keyword
4. Keep the "-site:domain" exclusion if present
5. Make the query more general but still relevant
6. Return ONLY the simplified query, nothing else

Example:
Input: "Critical Capabilities for Account-Based Marketing Platforms - Gartner" pdf -site:gartner.com
Output: "Critical Capabilities for Account-Based Marketing Platforms" pdf -site:gartner.com

Input: "Gartner Magic Quadrant for Account-Based Marketing Platforms 2023" pdf -site:gartner.com
Output: "Magic Quadrant Account-Based Marketing Platforms" pdf -site:gartner.com"""
    
    result = llm.invoke([
        {"role": "system", "content": system_message},
        {"role": "user", "content": f"Original query: {original_query}\nAttempt number: {attempt}\n\nSimplify this query to find results."}
    ])
    
    tweaked_query = result.content.strip()
    print(f"DEBUG: Tweaked query (attempt {attempt}): {tweaked_query}")
    return tweaked_query


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
    all_queries_used: List[str]


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
            "slideshare_search",
            "academic_repository_search",
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
        """Generate search queries based on the selected strategy."""
        strategy_prompts = {
            "direct_pdf_search": """Generate 3-5 search queries to find PDF copies of analyst reports.
Focus on finding actual PDF files hosted on third-party sites.
Include: report name in quotes, "pdf", exclude official analyst site, year filtering (2023 OR 2024 OR 2025).
Example: "Gartner Magic Quadrant CRM" pdf -site:gartner.com (2023 OR 2024 OR 2025)""",
            
            "vendor_blog_search": """Generate 3-5 search queries to find analyst reports mentioned in vendor blogs.
Vendors often share analyst reports on their blogs to show their achievements.
Include: vendor terms, analyst firm name, report type, "blog" or "news", year filtering (2023 OR 2024 OR 2025).
Example: "Gartner Magic Quadrant" CRM vendor blog OR news (2023 OR 2024 OR 2025)""",
            
            "slideshare_search": """Generate 3-5 search queries to find analyst reports on SlideShare.
Many reports are shared as presentations on SlideShare.
Include: report name, "slideshare", "presentation", "deck", year filtering (2023 OR 2024 OR 2025).
Example: "Gartner Magic Quadrant CRM" site:slideshare.net (2023 OR 2024 OR 2025)""",
            
            "academic_repository_search": """Generate 3-5 search queries to find analyst reports in academic repositories.
Sometimes reports are archived in research repositories.
Include: report name, "repository", "archive", "research", year filtering (2023 OR 2024 OR 2025).
Example: "Gartner Magic Quadrant CRM" repository OR archive (2023 OR 2024 OR 2025)""",
            
            "general_web_search": """Generate 3-5 broad search queries to find any mentions of the analyst report.
Use general terms and variations.
Include: report name, analyst firm, category, year filtering (2023 OR 2024 OR 2025).
Example: "Gartner Magic Quadrant CRM platforms" (2023 OR 2024 OR 2025)"""
        }
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are an expert at generating search queries for finding analyst reports.
            
{strategy_prompts.get(state['search_strategy'], strategy_prompts['direct_pdf_search'])}

Context:
- Analyst Firm: {state['analyst_firm']}
- Report Type: {state['report_type']}
- Category: {state['category']}

IMPORTANT: Always include year filtering (2023 OR 2024 OR 2025) to ensure results are from 2023 or later.

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
        """Execute search queries using Serper API with query tweaking if no results found."""
        all_results = []
        all_queries_used = []
        
        for query in state["search_queries"]:
            current_query = query
            all_queries_used.append(current_query)
            max_retries = 1  # Reduced from 3 to 1 to prevent indefinite tweaking
            
            for attempt in range(max_retries):
                try:
                    url = "https://google.serper.dev/search"
                    headers = {
                        "X-API-KEY": SERPER_API_KEY,
                        "Content-Type": "application/json"
                    }
                    payload = {
                        "q": current_query,
                        "num": 10
                    }
                    
                    response = requests.post(url, headers=headers, json=payload, timeout=30)
                    response.raise_for_status()
                    data = response.json()
                    
                    results_from_query = []
                    if "organic" in data:
                        for item in data["organic"]:
                            results_from_query.append({
                                "title": item.get("title", ""),
                                "link": item.get("link", ""),
                                "snippet": item.get("snippet", ""),
                                "query_used": current_query
                            })
                    
                    all_results.extend(results_from_query)
                    
                    # If we got results, move to next query
                    if results_from_query:
                        print(f"DEBUG: Query '{current_query[:50]}...' returned {len(results_from_query)} results")
                        break
                    
                    # If no results and not the last attempt, tweak the query
                    if attempt < max_retries - 1:
                        print(f"DEBUG: No results for query '{current_query[:50]}...', tweaking query (attempt {attempt + 1})")
                        current_query = tweak_search_query(current_query, attempt + 1)
                        all_queries_used.append(current_query)
                    else:
                        print(f"DEBUG: No results after {max_retries} attempts for query '{query[:50]}...'")
                        
                except Exception as e:
                    print(f"Search failed for query '{current_query}': {e}")
                    # If error and not the last attempt, try tweaking
                    if attempt < max_retries - 1:
                        current_query = tweak_search_query(current_query, attempt + 1)
                        all_queries_used.append(current_query)
        
        # Store all queries used for tracking
        state["all_queries_used"] = all_queries_used
        state["search_results"] = all_results
        state["reasoning"] = f"Executed search with {len(all_queries_used)} total queries (original + tweaked), found {len(all_results)} raw results"
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
        
        def is_recent_year(result: Dict) -> bool:
            """Check if result contains years 2023, 2024, or 2025."""
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            combined_text = f"{title} {snippet}".lower()
            
            # Check for recent years
            recent_years = ['2023', '2024', '2025']
            has_recent_year = any(year in combined_text for year in recent_years)
            
            return has_recent_year
        
        filtered = [r for r in state["search_results"] if is_likely_pdf_or_report(r) and is_recent_year(r)]
        
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
            "reasoning": "",
            "all_queries_used": []
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
        return state.get("all_queries_used", state.get("search_queries", []))
    
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
