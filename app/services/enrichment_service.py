"""
(enrichment_service.py) Orchestrates the product enrichment feature.
This service fetches raw search data and uses a fast, deterministic method
to curate it.
"""
from typing import List, Dict, Any

# Import the service to fetch raw data and the schema for the final response
from app.services.search_functions import fetch_enrichment_data
from app.schemas import EnrichResponse


def _curate_data_deterministically(raw_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Curates raw image and shopping data using a fast, deterministic algorithm.
    - Images: Sorts by aspect ratio closest to 1:1, then takes the top 4.
    - Shopping: Takes the very first link provided by the search API.

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
            
            # Take the image URLs of the top 4 results, ensuring a URL exists
            curated_images = [url for closeness, pos, url in sortable_images[:4] if url]

        # --- Shopping Link Curation Logic ---
        curated_shopping_links = []
        raw_shopping_results = product_data.get("shoppingData", [])
        if raw_shopping_results:
            # Take the very first result from the search API
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


async def enrich_products(product_names: List[str]) -> Dict[str, Any]:
    """
    The main orchestration function for the product enrichment feature.

    This simplified version follows a direct, deterministic path:
    1. Fetches raw image and shopping data in parallel from the search service.
    2. Curates the raw data using a simple, fast algorithm.
    3. Validates and returns the final data structure.
    
    Args:
        product_names: A list of product names to enrich.
        
    Returns:
        A dictionary containing the curated and validated product information,
        ready to be sent as a JSON response.
    """
    print(f"Starting enrichment process for products: {product_names}")

    # Step 1: Fetch raw image and shopping data in parallel from the search service.
    raw_aggregated_data = fetch_enrichment_data(product_names)

    if not raw_aggregated_data:
        print("Warning: Failed to fetch any enrichment data from search services.")
        return {"enrichedProducts": []}
    
    # Step 2: Curate the raw data using the simple, non-LLM method.
    print("INFO: Using deterministic (non-LLM) curation for enrichment.")
    final_combined_data = _curate_data_deterministically(raw_aggregated_data)

    # Step 3: Validate the final combined data against the Pydantic response model.
    # This ensures the output always matches the API's contract.
    try:
        validated_response = EnrichResponse.model_validate(final_combined_data)
        return validated_response.model_dump(by_alias=True)
    except Exception as e:
        print(f"ERROR: Pydantic validation failed for the final combined enrichment response. Details: {e}")
        print(f"Combined data that failed validation: {final_combined_data}")
        # Raising an exception here will be caught by the router and result in a 500 error.
        raise Exception("Failed to validate the final combined data structure.")