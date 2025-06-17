"""
(search_functions.py) Search and scraping functions using Serper API
"""
# --- MODIFICATION START ---
import httpx
from concurrent.futures import ThreadPoolExecutor
from app.config import SERPER_API_KEY, MAX_CONCURRENT_REQUESTS
# --- MODIFICATION END ---

# --- MODIFICATION START ---
# Refactored to use the httpx library for cleaner and more robust HTTP requests.
def _search_google(query: str) -> list:
    """
    Helper function to search Google using Serper API.
    
    Args:
        query (str): Search query.
    
    Returns:
        list: Organic search results, or an empty list on failure.
    """
    try:
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        payload = {"q": query}
        
        with httpx.Client() as client:
            response = client.post("https://google.serper.dev/search", json=payload, headers=headers)
            response.raise_for_status()  # Raise an exception for 4XX or 5XX status codes
            search_results = response.json()
        
        return search_results.get("organic", [])
        
    except httpx.HTTPStatusError as e:
        print(f"Error searching Google for query '{query}': HTTP {e.response.status_code} - {e.response.text}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during Google search for query '{query}': {e}")
        return []

def _scrape_url(url: str) -> str:
    """
    Helper function to scrape a URL using Serper API.
    
    Args:
        url (str): URL to scrape.
    
    Returns:
        str: Scraped text content, or an empty string on failure.
    """
    try:
        headers = {
            'X-API-KEY': SERPER_API_KEY,
            'Content-Type': 'application/json'
        }
        payload = {"url": url}

        with httpx.Client(timeout=20.0) as client: # Add a reasonable timeout
            response = client.post("https://scrape.serper.dev/", json=payload, headers=headers)
            response.raise_for_status()
            scrape_result = response.json()
        
        return scrape_result.get("text", "")
        
    except httpx.HTTPStatusError as e:
        print(f"Error scraping URL {url}: HTTP {e.response.status_code} - {e.response.text}")
        return ""
    except Exception as e:
        print(f"An unexpected error occurred while scraping URL {url}: {e}")
        return ""
# --- MODIFICATION END ---

def search_buying_guides(guide_search_term: str) -> dict:
    """
    Step 1.5: Search for buying guides using the guide search term.
    
    Args:
        guide_search_term (str): Search term for finding buying guides.
    
    Returns:
        dict: Search results in JSON format with organic results.
    """
    print(f"Searching for buying guides with term: {guide_search_term}")
    
    organic_results = _search_google(guide_search_term)
    
    return {"results": organic_results}

def _scrape_single_guide_url(url: str) -> str:
    """Helper function for parallel scraping of guide URLs."""
    print(f"Scraping: {url}")
    scraped_text = _scrape_url(url)
    
    if scraped_text:
        return f"\n\n--- Content from {url} ---\n\n{scraped_text}"
    else:
        print(f"Failed to scrape content from {url}")
        return ""

def scrape_guide_urls(guide_search_urls: list) -> str:
    """
    Step 2.5: Scrape content from selected buying guide URLs (PARALLELIZED).
    
    Args:
        guide_search_urls (list): List of URLs to scrape.
    
    Returns:
        str: Combined scraped content from the URLs.
    """
    print(f"Scraping guide URLs: {guide_search_urls}")
    
    # --- MODIFICATION START ---
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
    # --- MODIFICATION END ---
        # Process all URLs in parallel
        scraped_contents = list(executor.map(_scrape_single_guide_url, guide_search_urls))
    
    # Combine all content
    combined_content = "".join(content for content in scraped_contents if content)
    return combined_content.strip()

def _search_single_recommendation(query: str) -> dict:
    """Helper function for parallel product recommendation searching."""
    print(f"Searching for: {query}")
    organic_results = _search_google(query)
    
    return {
        "query": query,
        "results": organic_results
    }

def search_product_recommendations(rec_search_terms: list) -> list:
    """
    Step 4.5: Search for product recommendations using the recommendation search terms (PARALLELIZED).
    
    Args:
        rec_search_terms (list): List of search terms for finding product recommendations.
    
    Returns:
        list: Search results for each query.
    """
    print(f"Searching for product recommendations with terms: {rec_search_terms}")
    
    # --- MODIFICATION START ---
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
    # --- MODIFICATION END ---
        # Process all search terms in parallel
        results = list(executor.map(_search_single_recommendation, rec_search_terms))
    
    return results

def _scrape_single_recommendation_url(url_obj: dict) -> dict:
    """Helper function for parallel scraping of recommendation URLs."""
    url = url_obj["url"]
    title = url_obj["title"]
    
    print(f"Scraping: {title} - {url}")
    scraped_text = _scrape_url(url)
    
    return {
        "title": title,
        "url": url,
        "text": scraped_text if scraped_text else f"Failed to scrape content from {url}"
    }

def scrape_recommendation_urls(rec_search_urls: list) -> list:
    """
    Step 5.5: Scrape content from selected product recommendation URLs (PARALLELIZED).
    
    Args:
        rec_search_urls (list): List of URL objects with title and url keys.
    
    Returns:
        list: Scraped content from each URL.
    """
    print(f"Scraping recommendation URLs: {[url_obj['url'] for url_obj in rec_search_urls]}")
    
    # --- MODIFICATION START ---
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
    # --- MODIFICATION END ---
        # Process all URLs in parallel
        scraped_contents = list(executor.map(_scrape_single_recommendation_url, rec_search_urls))
    
    return scraped_contents