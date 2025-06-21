"""
(enrichment_service.py) Orchestrates the product enrichment feature.
This service fetches raw data and uses an LLM to curate it.
"""
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.services.search_functions import fetch_enrichment_data
from app.services.llm_handler import curate_images, curate_shopping_links
from app.schemas import EnrichResponse
from app.config import PRODUCT_CHUNK_SIZE, LLM_TASK_CONCURRENCY


def _combine_curation_results(
    image_results: Dict,
    shopping_results: Dict
) -> Dict:
    """
    Merges the separate results from the image and shopping LLM calls
    into the final, combined structure. This function remains the same, but it
    now receives aggregated results from multiple smaller LLM calls.
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


async def enrich_products(product_names: List[str]) -> Dict[str, Any]:
    """
    The main orchestration function for the product enrichment feature.
    
    This function has been refactored to perform the following steps:
    1.  Fetches raw image and shopping data for all products in one batch call.
    2.  Chunks the list of products into smaller groups (of size 2).
    3.  Creates a list of all required LLM curation tasks (images & shopping for each chunk).
    4.  Executes these tasks in parallel with a fixed concurrency limit (of 6).
    5.  Aggregates the results from all the parallel calls.
    6.  Merges the aggregated results into the final response format.
    7.  Validates the final combined data using the Pydantic model.
    
    Args:
        product_names: A list of product names to enrich.
        
    Returns:
        A dictionary containing the curated and validated product information,
        ready to be sent as a JSON response.
    """
    print(f"Starting enrichment process for products: {product_names}")

    # Step 1: Fetch raw image and shopping data in parallel from Serper. This is still efficient.
    raw_aggregated_data = fetch_enrichment_data(product_names)

    if not raw_aggregated_data:
        print("Warning: Failed to fetch any enrichment data from search services.")
        return {"enrichedProducts": []}
    
    # --- MODIFICATION START ---

    # Step 2: Chunk the raw data into smaller lists based on PRODUCT_CHUNK_SIZE.
    product_chunks = [
        raw_aggregated_data[i:i + PRODUCT_CHUNK_SIZE]
        for i in range(0, len(raw_aggregated_data), PRODUCT_CHUNK_SIZE)
    ]
    print(f"Split {len(product_names)} products into {len(product_chunks)} chunks of size {PRODUCT_CHUNK_SIZE}.")

    # Step 3: Generate all the individual LLM tasks that need to be run.
    llm_tasks = []
    for chunk in product_chunks:
        # The LLM prompts expect a specific input format, so we prepare it for each chunk.
        image_input_for_chunk = [
            {"productName": item["productName"], "imageData": item["imageData"]}
            for item in chunk
        ]
        shopping_input_for_chunk = [
            {"productName": item["productName"], "shoppingData": item["shoppingData"]}
            for item in chunk
        ]
        
        # Add a tuple of (function_to_call, data_for_function) to our task list.
        llm_tasks.append((curate_images, image_input_for_chunk))
        llm_tasks.append((curate_shopping_links, shopping_input_for_chunk))
    
    print(f"Generated a total of {len(llm_tasks)} LLM tasks to be executed.")

    # Step 4 & 5: Execute tasks in parallel and aggregate results.
    all_curated_images = []
    all_curated_shopping_links = []

    with ThreadPoolExecutor(max_workers=LLM_TASK_CONCURRENCY) as executor:
        # Submit all tasks to the executor.
        future_to_task = {executor.submit(func, data): func.__name__ for func, data in llm_tasks}
        
        # Process results as they complete.
        for future in as_completed(future_to_task):
            task_name = future_to_task[future]
            try:
                result = future.result()
                # Sort the results into their respective lists.
                if 'curatedImages' in result:
                    all_curated_images.extend(result['curatedImages'])
                elif 'curatedShoppingLinks' in result:
                    all_curated_shopping_links.extend(result['curatedShoppingLinks'])
                else:
                    print(f"Warning: Task '{task_name}' returned an unexpected result format.")
            except Exception as e:
                # Log the error for the failed task but allow others to continue.
                print(f"ERROR: LLM curation task '{task_name}' failed: {e}")

    if not all_curated_images and not all_curated_shopping_links:
        print("Warning: All LLM curation tasks failed. Returning empty result.")
        return {"enrichedProducts": []}

    # Step 6: Assemble the aggregated results into the format expected by the merge function.
    final_image_results = {"curatedImages": all_curated_images}
    final_shopping_results = {"curatedShoppingLinks": all_curated_shopping_links}

    # --- MODIFICATION END ---

    # Step 7: Merge the results from the aggregated calls.
    final_combined_data = _combine_curation_results(final_image_results, final_shopping_results)

    # Step 8: Validate the final combined data against the Pydantic response model.
    try:
        validated_response = EnrichResponse.model_validate(final_combined_data)
        return validated_response.model_dump(by_alias=True)
    except Exception as e:
        print(f"ERROR: Pydantic validation failed for the final combined enrichment response. Details: {e}")
        print(f"Combined data that failed validation: {final_combined_data}")
        raise Exception("Failed to validate the final combined data structure.")