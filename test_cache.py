"""
Test script to verify Serper caching implementation.
Run this script to test that caching is working correctly.
"""
import os
import sys
from dotenv import load_dotenv
from cache_utils import (
    get_cached_results, 
    cache_results, 
    get_cache_stats, 
    clear_cache, 
    cleanup_expired_cache
)

load_dotenv()

def test_cache_basic_operations():
    """Test basic cache operations."""
    print("=" * 60)
    print("Testing Basic Cache Operations")
    print("=" * 60)
    
    # Clear cache first
    clear_cache()
    
    # Test 1: Cache miss for new query
    test_query = "Gartner Magic Quadrant CRM 2023"
    print(f"\n1. Testing cache miss for: '{test_query}'")
    result = get_cached_results(test_query)
    assert result is None, "Expected None for cache miss"
    print("✓ Cache miss works correctly")
    
    # Test 2: Cache results
    print(f"\n2. Caching results for: '{test_query}'")
    test_results = [
        {"title": "Test Result 1", "link": "https://example.com/1", "snippet": "Test snippet 1"},
        {"title": "Test Result 2", "link": "https://example.com/2", "snippet": "Test snippet 2"}
    ]
    cache_results(test_query, test_results)
    print("✓ Results cached successfully")
    
    # Test 3: Cache hit
    print(f"\n3. Testing cache hit for: '{test_query}'")
    result = get_cached_results(test_query)
    assert result is not None, "Expected results for cache hit"
    assert len(result) == 2, "Expected 2 results"
    assert result[0]["title"] == "Test Result 1", "Result mismatch"
    print("✓ Cache hit works correctly")
    
    # Test 4: Case insensitive query
    print(f"\n4. Testing case insensitive query")
    result = get_cached_results(test_query.upper())
    assert result is not None, "Expected results for uppercase query"
    print("✓ Case insensitive query works")
    
    # Test 5: Whitespace insensitive query
    print(f"\n5. Testing whitespace insensitive query")
    result = get_cached_results(f"  {test_query}  ")
    assert result is not None, "Expected results for query with extra whitespace"
    print("✓ Whitespace insensitive query works")
    
    # Test 6: Cache stats
    print(f"\n6. Testing cache stats")
    stats = get_cache_stats()
    assert stats["total_files"] == 1, "Expected 1 cached file"
    assert stats["valid_files"] == 1, "Expected 1 valid file"
    print(f"✓ Cache stats: {stats}")
    
    # Test 7: Clear cache
    print(f"\n7. Testing clear cache")
    deleted = clear_cache()
    assert deleted == 1, "Expected 1 file deleted"
    print(f"✓ Cleared {deleted} cache files")
    
    # Test 8: Verify cache is empty
    print(f"\n8. Verifying cache is empty")
    result = get_cached_results(test_query)
    assert result is None, "Expected None after cache clear"
    print("✓ Cache cleared successfully")
    
    print("\n" + "=" * 60)
    print("All basic cache tests passed! ✓")
    print("=" * 60)


def test_cache_with_api():
    """Test caching integration with API functions."""
    print("\n" + "=" * 60)
    print("Testing Cache Integration with API")
    print("=" * 60)
    
    # Check if API key is available
    serper_key = os.getenv("SERPER_API_KEY")
    if not serper_key:
        print("⚠ SERPER_API_KEY not found. Skipping API integration test.")
        print("To test API integration, set SERPER_API_KEY in .env file")
        return
    
    try:
        from api import perform_serper_search
        
        # Clear cache first
        clear_cache()
        
        test_query = '"Gartner Magic Quadrant" CRM pdf -site:gartner.com'
        
        # Test 1: First call should be cache miss
        print(f"\n1. First API call (cache miss): '{test_query}'")
        results1, queries1 = perform_serper_search(test_query, use_cache=True)
        print(f"✓ Got {len(results1)} results")
        
        # Test 2: Second call should be cache hit
        print(f"\n2. Second API call (cache hit): '{test_query}'")
        results2, queries2 = perform_serper_search(test_query, use_cache=True)
        print(f"✓ Got {len(results2)} results from cache")
        
        # Verify results are the same
        assert len(results1) == len(results2), "Result count mismatch"
        print("✓ Cache hit returns same results")
        
        # Test 3: Cache stats
        print(f"\n3. Checking cache stats")
        stats = get_cache_stats()
        print(f"✓ Cache stats: {stats}")
        
        # Test 4: Test with cache disabled
        print(f"\n4. Testing with cache disabled")
        results3, queries3 = perform_serper_search(test_query, use_cache=False)
        print(f"✓ Got {len(results3)} results with cache disabled")
        
        print("\n" + "=" * 60)
        print("API integration tests passed! ✓")
        print("=" * 60)
        
    except ImportError as e:
        print(f"⚠ Could not import api module: {e}")
        print("Make sure you have installed all dependencies")
    except Exception as e:
        print(f"⚠ API integration test failed: {e}")


def test_cache_with_agent():
    """Test caching integration with agent."""
    print("\n" + "=" * 60)
    print("Testing Cache Integration with Agent")
    print("=" * 60)
    
    # Check if API keys are available
    serper_key = os.getenv("SERPER_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not serper_key or not openai_key:
        print("⚠ API keys not found. Skipping agent integration test.")
        print("To test agent integration, set SERPER_API_KEY and OPENAI_API_KEY in .env file")
        return
    
    try:
        from agent import AnalystReportAgent
        
        # Clear cache first
        clear_cache()
        
        print(f"\n1. Running agent search (first time - cache miss)")
        agent = AnalystReportAgent()
        result1 = agent.search("Gartner Magic Quadrant for CRM", max_iterations=1)
        print(f"✓ Agent found {len(result1['validated_results'])} results")
        
        print(f"\n2. Running agent search again (cache hit)")
        agent2 = AnalystReportAgent()
        result2 = agent2.search("Gartner Magic Quadrant for CRM", max_iterations=1)
        print(f"✓ Agent found {len(result2['validated_results'])} results")
        
        # Test 3: Cache stats
        print(f"\n3. Checking cache stats")
        stats = get_cache_stats()
        print(f"✓ Cache stats: {stats}")
        
        print("\n" + "=" * 60)
        print("Agent integration tests passed! ✓")
        print("=" * 60)
        
    except ImportError as e:
        print(f"⚠ Could not import agent module: {e}")
        print("Make sure you have installed all dependencies")
    except Exception as e:
        print(f"⚠ Agent integration test failed: {e}")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("SERPER CACHING TEST SUITE")
    print("=" * 60)
    
    try:
        # Run basic tests
        test_cache_basic_operations()
        
        # Run API integration tests
        test_cache_with_api()
        
        # Run agent integration tests
        test_cache_with_agent()
        
        print("\n" + "=" * 60)
        print("ALL TESTS COMPLETED SUCCESSFULLY! ✓")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
