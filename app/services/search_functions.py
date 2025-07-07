"""
(search_functions.py) Search and scraping functions.
- Uses Tavily for the main recommendation search/scrape.
- Uses Serper for the enrichment (image/shopping) searches.
"""
import httpx
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any

# Import Tavily client and API key
from tavily import TavilyClient
from app.config import TAVILY_API_KEY

# Import Serper key and other configs for enrichment functions
from app.config import SERPER_API_KEY, MAX_CONCURRENT_REQUESTS


# ==============================================================================
# Recommendation Flow Functions (Using Tavily)
# ==============================================================================

def _search_single_tavily_query(
    term: str, 
    search_depth: str = "advanced", 
    max_results: int = 10, 
    country: str = "united states"
) -> Dict[str, Any]:
    """
    Helper function to perform a single search query using the Tavily client
    with configurable parameters.
    """
    print(f"Tavily: Searching for '{term}' with depth='{search_depth}', max_results={max_results}, country='{country}'")
    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(
            query=term,
            search_depth=search_depth,
            max_results=max_results,
            country=country
        )
        # The Tavily response format is already what we want to pass on.
        return response
    except Exception as e:
        print(f"ERROR: Tavily search for term '{term}' failed: {e}")
        # Return a structured error response that won't crash the calling loop
        return {"query": term, "results": []}


def search_product_recommendations(
    rec_search_terms: List[str],
    search_depth: str = "advanced",
    max_results_per_term: int = 10,
    country: str = "united states"
) -> List[Dict[str, Any]]:
    """
    Step 4.5: Search for product recommendations using parallel Tavily API calls
    with configurable parameters.
    
    Args:
        rec_search_terms (List[str]): List of search terms for finding product recommendations.
        search_depth (str): The depth of the search ('basic' or 'advanced').
        max_results_per_term (int): The number of results to return for each search term.
        country (str): The country to search from.
    
    Returns:
        List[Dict[str, Any]]: A list of Tavily search result objects, one for each term.
    """
    print(f"Performing parallel Tavily search for {len(rec_search_terms)} recommendation terms.")
    
    if not rec_search_terms:
        return []

    results = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        # Map each search term to the search function, passing the new parameters
        future_to_term = {
            executor.submit(
                _search_single_tavily_query, 
                term, 
                search_depth, 
                max_results_per_term, 
                country
            ): term 
            for term in rec_search_terms
        }
        
        for future in as_completed(future_to_term):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                term = future_to_term[future]
                print(f"ERROR: An exception was raised for Tavily search term '{term}': {e}")
                # Append a failure object to maintain list size if needed, but it's handled in the helper
    
    print(f"Tavily search completed. Got results for {len(results)} terms.")
    return results


def scrape_recommendation_urls(rec_search_urls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Step 5.5: Scrape content from selected product recommendation URLs using a single
    batch request to the Tavily `extract` API.
    
    Args:
        rec_search_urls (List[Dict[str, Any]]): A list of objects selected by the LLM, each containing at least 'title' and 'url'.
    
    Returns:
        List[Dict[str, Any]]: A list of objects with 'title', 'url', and 'text' (scraped content).
    """
    print(f"Performing batch scrape of {len(rec_search_urls)} URLs with Tavily.")

    if not rec_search_urls:
        return []
    
    # Extract just the URLs for the batch API call
    urls_to_scrape = [item['url'] for item in rec_search_urls]
    
    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        # Make a single batch call to the extract endpoint
        scraped_data = client.extract(
            urls=urls_to_scrape,
            extract_depth="advanced"
        )
        
        # Create a lookup map for efficient merging: {url: scraped_content}
        content_map = {
            result['url']: result.get('raw_content', '')
            for result in scraped_data['results']
        }
        
        # Merge the scraped content back with the original titles
        final_scraped_contents = []
        for original_item in rec_search_urls:
            url = original_item['url']
            scraped_text = content_map.get(url, f"Failed to scrape content from {url}")
            
            final_scraped_contents.append({
                "title": original_item.get("title", "No Title"),
                "url": url,
                "text": scraped_text
            })
            
        print("Tavily batch scrape and merge completed successfully.")
        return final_scraped_contents

    except Exception as e:
        print(f"An unexpected error occurred during Tavily batch scrape: {e}")
        # If the whole batch fails, return a list with failure messages for each URL
        return [
            {"title": item.get("title"), "url": item['url'], "text": f"Scraping failed due to an API error: {e}"}
            for item in rec_search_urls
        ]
    
def execute_parallel_searches(search_queries: List[str]) -> str:
    """
    Takes a list of search queries from the LLM, executes them in parallel
    using Tavily, and returns a formatted JSON string of the aggregated results.
    This is designed to be the action for the `web_search` tool.

    Args:
        search_queries: A list of 1-3 search strings.

    Returns:
        A JSON string representing a list of search result objects,
        ready to be passed back to the LLM.
    """
    print(f"Executing parallel web search for {len(search_queries)} queries from LLM.")

    if not search_queries:
        return json.dumps([])

    all_results = []
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        # Use the existing Tavily search function for each query
        future_to_query = {
            executor.submit(
                search_product_recommendations,
                [query], # The function expects a list of terms
                search_depth="basic", # 'basic' is faster and sufficient for this
                max_results_per_term=5 # Limit results to keep context small
            ): query for query in search_queries
        }

        for future in as_completed(future_to_query):
            try:
                # The result is a list containing one search result object
                result_for_query = future.result()
                if result_for_query:
                    # Append the inner object to our final list
                    all_results.append(result_for_query[0])
            except Exception as e:
                query = future_to_query[future]
                print(f"ERROR: A search failed within execute_parallel_searches for query '{query}': {e}")
                # Optionally append an error message for the LLM
                all_results.append({"query": query, "error": str(e), "results": []})

    print(f"Parallel web search complete. Aggregated results from {len(all_results)} queries.")
    # Return a stringified JSON so the LLM can easily parse it
    return json.dumps(all_results, indent=2)


# ==============================================================================
# Enrichment Flow Functions (Still Using Serper) - UNCHANGED
# ==============================================================================

def search_images_for_products(product_names: List[str]) -> List[Dict[str, Any]]:
    """
    Performs a batch image search for a list of product names using Serper.
    
    Args:
        product_names: A list of product name strings to search for.
        
    Returns:
        A list of Serper's raw image search results for each product.
    """
    print(f"Serper: Performing batch image search for: {product_names}")
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    payload = json.dumps([{"q": name, "num": 10} for name in product_names])
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post("https://google.serper.dev/images", content=payload, headers=headers)
            response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        print(f"Error during batch image search: HTTP {e.response.status_code} - {e.response.text}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during batch image search: {e}")
        return []

def search_shopping_for_products(product_names: List[str]) -> List[Dict[str, Any]]:
    """
    Performs a batch shopping search for a list of product names using Serper.
    
    Args:
        product_names: A list of product name strings to search for.
        
    Returns:
        A list of Serper's raw shopping search results for each product.
    """
    print(f"Serper: Performing batch shopping search for: {product_names}")
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    payload = json.dumps([{"q": name} for name in product_names])
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post("https://google.serper.dev/shopping", content=payload, headers=headers)
            response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        print(f"Error during batch shopping search: HTTP {e.response.status_code} - {e.response.text}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during batch shopping search: {e}")
        return []

def fetch_enrichment_data(product_names: List[str]) -> List[Dict[str, Any]]:
    """
    Orchestrates parallel fetching of image and shopping data for a list of products.
    Aggregates the results into a structure ready for the LLM.
    
    Args:
        product_names: A list of product names.
        
    Returns:
        A list of dictionaries, where each dictionary contains the product name
        and its corresponding raw image and shopping data.
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_images = executor.submit(search_images_for_products, product_names)
        future_shopping = executor.submit(search_shopping_for_products, product_names)
        
        image_results = future_images.result()
        shopping_results = future_shopping.result()

    image_map = {result.get('searchParameters', {}).get('q'): result.get('images', []) for result in image_results}
    shopping_map = {result.get('searchParameters', {}).get('q'): result.get('shopping', []) for result in shopping_results}
    
    aggregated_data = []
    for name in product_names:
        aggregated_data.append({
            "productName": name,
            "imageData": image_map.get(name, []),
            "shoppingData": shopping_map.get(name, [])
        })
        
    print(f"Serper: Successfully aggregated enrichment data for {len(product_names)} products.")
    return aggregated_data