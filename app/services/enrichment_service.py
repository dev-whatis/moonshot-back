"""
(enrichment_service.py) Orchestrates the product enrichment feature.
This service fetches raw data and can use either an LLM or a deterministic
method to curate it, based on a configuration flag.
"""
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.search_functions import fetch_enrichment_data
from app.services.llm_calls import curate_images, curate_shopping_links
from app.schemas import EnrichResponse
from app.config import (
    PRODUCT_CHUNK_SIZE,
    LLM_TASK_CONCURRENCY,
    USE_LLM_FOR_ENRICHMENT
)


def _combine_curation_results(
    image_results: Dict,
    shopping_results: Dict
) -> Dict:
    """
    (Used by LLM path only)
    Merges the separate results from the image and shopping LLM calls
    into the final, combined structure.
    """
    # Create a lookup map for shopping links for efficient merging
    shopping_map = {
        item['productName']: item['shoppingLinks']
        for item in shopping_results.get('curatedShoppingLinks', [])
    }
    
    combined_products = []
    # Loop through the image results as the primary source of products
    for image_item in image_results.get('curatedImages', []):
        product_name = image_item['productName']
        combined_products.append({
            "productName": product_name,
            "images": image_item.get('images', []),
            # Look up the corresponding shopping links from the map
            "shoppingLinks": shopping_map.get(product_name, [])
        })
        
    return {"enrichedProducts": combined_products}


# --- MODIFICATION START: New deterministic helper function ---
def _curate_data_deterministically(raw_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    (Used by non-LLM path only)
    Curates raw image and shopping data using a fast, deterministic method.
    - Images: Sorts by aspect ratio closest to 1:1, then takes the top 4.
    - Shopping: Takes the very first link provided by the API.

    Args:
        raw_data: The aggregated raw data from the search service.

    Returns:
        A dictionary containing the curated product information.
    """
    enriched_products = []

    for product_data in raw_data:
        product_name = product_data["productName"]

        # --- Image Curation Logic ---
        curated_images = []
        raw_images = product_data.get("imageData", [])
        if raw_images:
            # Create a list of tuples for sorting: (closeness_to_square, position, url)
            sortable_images = []
            for img in raw_images:
                width = img.get("imageWidth", 0)
                height = img.get("imageHeight", 0)
                
                if width > 0 and height > 0:
                    aspect_ratio = width / height
                    # Closeness is the absolute difference from a 1:1 ratio
                    closeness = abs(aspect_ratio - 1)
                    sortable_images.append((closeness, img.get("position", 99), img.get("imageUrl")))

            # Sort by closeness (ascending), then by original position (ascending) as a tie-breaker
            sortable_images.sort(key=lambda x: (x[0], x[1]))
            
            # Take the image URLs of the top 4 results
            curated_images = [url for closeness, pos, url in sortable_images[:4] if url]

        # --- Shopping Link Curation Logic ---
        curated_shopping_links = []
        raw_shopping_results = product_data.get("shoppingData", [])
        if raw_shopping_results:
            # Take the very first result
            first_link = raw_shopping_results[0]
            curated_shopping_links.append({
                "source": first_link.get("source", "N/A"),
                "link": first_link.get("link", "#"),
                "price": first_link.get("price", "Price not available"),
                "delivery": first_link.get("delivery", "Delivery info not available")
            })

        enriched_products.append({
            "productName": product_name,
            "images": curated_images,
            "shoppingLinks": curated_shopping_links
        })

    return {"enrichedProducts": enriched_products}
# --- MODIFICATION END ---


async def enrich_products(product_names: List[str]) -> Dict[str, Any]:
    """
    The main orchestration function for the product enrichment feature.

    It can operate in two modes based on the `USE_LLM_FOR_ENRICHMENT` flag:
    1. LLM-based (True): Uses parallel LLM calls to curate data. Slower, more expensive.
    2. Deterministic (False): Uses a simple, fast algorithm to select data.
    
    Args:
        product_names: A list of product names to enrich.
        
    Returns:
        A dictionary containing the curated and validated product information,
        ready to be sent as a JSON response.
    """
    print(f"Starting enrichment process for products: {product_names}")

    # Step 1: Fetch raw image and shopping data in parallel from Serper. This is common to both paths.
    raw_aggregated_data = fetch_enrichment_data(product_names)

    if not raw_aggregated_data:
        print("Warning: Failed to fetch any enrichment data from search services.")
        return {"enrichedProducts": []}
    
    final_combined_data = {}

    # --- MODIFICATION: Switch between LLM and deterministic logic ---
    if USE_LLM_FOR_ENRICHMENT:
        print("INFO: Using LLM-based curation for enrichment.")
        # This is the original, now-bypassed code path.
        
        # Step 2: Chunk the raw data into smaller lists based on PRODUCT_CHUNK_SIZE.
        product_chunks = [
            raw_aggregated_data[i:i + PRODUCT_CHUNK_SIZE]
            for i in range(0, len(raw_aggregated_data), PRODUCT_CHUNK_SIZE)
        ]
        print(f"Split {len(product_names)} products into {len(product_chunks)} chunks of size {PRODUCT_CHUNK_SIZE}.")

        # Step 3: Generate all the individual LLM tasks that need to be run.
        llm_tasks = []
        for chunk in product_chunks:
            image_input_for_chunk = [
                {"productName": item["productName"], "imageData": item["imageData"]}
                for item in chunk
            ]
            shopping_input_for_chunk = [
                {"productName": item["productName"], "shoppingData": item["shoppingData"]}
                for item in chunk
            ]
            llm_tasks.append((curate_images, image_input_for_chunk))
            llm_tasks.append((curate_shopping_links, shopping_input_for_chunk))
        
        print(f"Generated a total of {len(llm_tasks)} LLM tasks to be executed.")

        # Step 4 & 5: Execute tasks in parallel and aggregate results.
        all_curated_images = []
        all_curated_shopping_links = []

        with ThreadPoolExecutor(max_workers=LLM_TASK_CONCURRENCY) as executor:
            future_to_task = {executor.submit(func, data): func.__name__ for func, data in llm_tasks}
            for future in as_completed(future_to_task):
                task_name = future_to_task[future]
                try:
                    result = future.result()
                    if 'curatedImages' in result:
                        all_curated_images.extend(result['curatedImages'])
                    elif 'curatedShoppingLinks' in result:
                        all_curated_shopping_links.extend(result['curatedShoppingLinks'])
                except Exception as e:
                    print(f"ERROR: LLM curation task '{task_name}' failed: {e}")

        if not all_curated_images and not all_curated_shopping_links:
            print("Warning: All LLM curation tasks failed. Returning empty result.")
            return {"enrichedProducts": []}

        # Step 6: Assemble the aggregated results into the format expected by the merge function.
        final_image_results = {"curatedImages": all_curated_images}
        final_shopping_results = {"curatedShoppingLinks": all_curated_shopping_links}

        # Step 7: Merge the results from the aggregated calls.
        final_combined_data = _combine_curation_results(final_image_results, final_shopping_results)

    else:
        # This is the new, fast, deterministic code path.
        print("INFO: Using deterministic (non-LLM) curation for enrichment.")
        final_combined_data = _curate_data_deterministically(raw_aggregated_data)
    # --- End of logic switch ---

    # Step 8: Validate the final combined data against the Pydantic response model.
    try:
        validated_response = EnrichResponse.model_validate(final_combined_data)
        return validated_response.model_dump(by_alias=True)
    except Exception as e:
        print(f"ERROR: Pydantic validation failed for the final combined enrichment response. Details: {e}")
        print(f"Combined data that failed validation: {final_combined_data}")
        raise Exception("Failed to validate the final combined data structure.")