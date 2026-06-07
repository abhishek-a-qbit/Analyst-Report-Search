"""Test script for the Analyst Report Agent."""
import os
import sys
from dotenv import load_dotenv
from agent import search_analyst_reports_deep
import json

load_dotenv()

def test_agent():
    """Test the agent with a sample query."""
    print("Testing Analyst Report Agent...")
    print("=" * 60)
    
    # Check API keys
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not found in environment")
        return False
    
    if not os.getenv("SERPER_API_KEY"):
        print("❌ SERPER_API_KEY not found in environment")
        return False
    
    print("✅ API keys found")
    print()
    
    # Test query
    test_query = "Gartner Magic Quadrant for Account-Based Marketing Platforms"
    print(f"Test Query: {test_query}")
    print("-" * 60)
    
    try:
        result = search_analyst_reports_deep(test_query, max_iterations=2)
        
        print("\n📊 Analysis Results:")
        print(f"  Analyst Firm: {result.get('analyst_firm', 'N/A')}")
        print(f"  Report Type: {result.get('report_type', 'N/A')}")
        print(f"  Category: {result.get('category', 'N/A')}")
        print(f"  Iterations: {result.get('iterations', 0)}")
        
        print(f"\n🔍 Search Queries Used: {len(result.get('search_queries', []))}")
        for i, query in enumerate(result.get('search_queries', []), 1):
            print(f"  {i}. {query}")
        
        print(f"\n📄 Validated Results: {len(result.get('validated_results', []))}")
        for i, res in enumerate(result.get('validated_results', []), 1):
            print(f"  {i}. {res.get('title', 'No title')}")
            print(f"     Link: {res.get('link', 'No link')}")
            print(f"     Snippet: {res.get('snippet', 'No snippet')[:100]}...")
        
        print(f"\n🧠 Reasoning Trace:")
        for i, reasoning in enumerate(result.get('reasoning_trace', []), 1):
            print(f"  {i}. {reasoning}")
        
        print("\n" + "=" * 60)
        print("✅ Agent test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_agent()
    sys.exit(0 if success else 1)
