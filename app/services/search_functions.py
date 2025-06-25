"""
(search_functions.py) Search and scraping functions using Serper API
"""
import httpx
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any

from app.config import SERPER_API_KEY, MAX_CONCURRENT_REQUESTS

# --- Function to scrape a single URL using Serper API ---
def _scrape_url(url: str) -> str:
    """
    Helper function to scrape a URL using Serper API. This must be called
    one URL at a time.
    
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
        payload = {"url": url, "includeMarkdown": True}

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


# --- MODIFICATION START: OPTIMIZED BATCH SEARCH ---

def search_product_recommendations(rec_search_terms: list) -> list:
    """
    Step 4.5: Search for product recommendations using a single BATCH request (OPTIMIZED).
    
    Args:
        rec_search_terms (list): List of search terms for finding product recommendations.
    
    Returns:
        list: A list of search result objects, formatted to match the application's
              expected structure: [{"query": str, "results": list}, ...].
    """
    print(f"Performing batch Google search for recommendation terms: {rec_search_terms}")
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    # Create a list of query objects for the batch request
    payload = json.dumps([{"q": term} for term in rec_search_terms])
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post("https://google.serper.dev/search", content=payload, headers=headers)
            response.raise_for_status()
        
        # The result is a list of search result objects, one for each query
        batch_results = response.json()
        
        # Transform the raw batch response to the format expected by the rest of the application
        formatted_results = []
        for result in batch_results:
            original_query = result.get('searchParameters', {}).get('q', 'unknown')
            organic_results = result.get('organic', [])
            formatted_results.append({
                "query": original_query,
                "results": organic_results
            })
        
        return formatted_results

    except httpx.HTTPStatusError as e:
        print(f"Error during batch Google search: HTTP {e.response.status_code} - {e.response.text}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during batch Google search: {e}")
        return []

# --- MODIFICATION END ---


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
    This function remains unchanged as scraping must be done one URL at a time.
    
    Args:
        rec_search_urls (list): List of URL objects with title and url keys.
    
    Returns:
        list: Scraped content from each URL.
    """
    print(f"Scraping recommendation URLs: {[url_obj['url'] for url_obj in rec_search_urls]}")
    
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_REQUESTS) as executor:
        # Process all URLs in parallel
        scraped_contents = list(executor.map(_scrape_single_recommendation_url, rec_search_urls))
    
    return scraped_contents

# --- Functions for the Enrichment feature (already optimized) ---

def search_images_for_products(product_names: List[str]) -> List[Dict[str, Any]]:
    """
    Performs a batch image search for a list of product names using Serper.
    
    Args:
        product_names: A list of product name strings to search for.
        
    Returns:
        A list of Serper's raw image search results for each product.
    """
    print(f"Performing batch image search for: {product_names}")
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    # Create a list of query objects for the batch request
    payload = json.dumps([{"q": name, "num": 10} for name in product_names])
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post("https://google.serper.dev/images", content=payload, headers=headers)
            response.raise_for_status()
        # The result is a list of search result objects, one for each query
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
    print(f"Performing batch shopping search for: {product_names}")
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    # Create a list of query objects for the batch request
    payload = json.dumps([{"q": name} for name in product_names])
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post("https://google.serper.dev/shopping", content=payload, headers=headers)
            response.raise_for_status()
        # The result is a list of search result objects, one for each query
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
        # Submit both the image and shopping batch searches to run in parallel
        future_images = executor.submit(search_images_for_products, product_names)
        future_shopping = executor.submit(search_shopping_for_products, product_names)
        
        # Wait for both batch calls to complete and get their results
        image_results = future_images.result()
        shopping_results = future_shopping.result()

    # Create a dictionary to map product names to their results for easy aggregation
    # The query field in the Serper response lets us map results back to the original name
    image_map = {result.get('searchParameters', {}).get('q'): result.get('images', []) for result in image_results}
    shopping_map = {result.get('searchParameters', {}).get('q'): result.get('shopping', []) for result in shopping_results}
    
    # Aggregate the data into the final structure
    aggregated_data = []
    for name in product_names:
        aggregated_data.append({
            "productName": name,
            "imageData": image_map.get(name, []),
            "shoppingData": shopping_map.get(name, [])
        })
        
    print(f"Successfully aggregated enrichment data for {len(product_names)} products.")
    return aggregated_data