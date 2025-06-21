"""
(enrich.py) Defines the API route for the product enrichment feature.
"""

from fastapi import APIRouter, Depends, HTTPException, status

# Import the main service function
from app.services.enrichment_service import enrich_products

# Import schemas (Pydantic models)
from app.schemas import EnrichRequest, EnrichResponse

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# ==============================================================================
# Router Setup
# ==============================================================================

router = APIRouter(
    prefix="/api",
    tags=["Enrichment"]
)

# ==============================================================================
# API Endpoint
# ==============================================================================

@router.post(
    "/enrich",
    response_model=EnrichResponse
)
async def get_product_enrichment(
    request: EnrichRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Accepts a list of product names and returns curated image and shopping
    link information for each product.

    This endpoint orchestrates a multi-step process:
    1.  Performs parallel image and shopping searches for each product name.
    2.  Aggregates the raw search results.
    3.  Uses a single LLM call to curate the best images and shopping links
        based on a set of predefined rules.
    4.  Returns the structured, curated data.
    """
    print(f"User {user_id} | Starting enrichment for {len(request.product_names)} products.")

    if not request.product_names:
        # Handle the case of an empty request list to avoid unnecessary processing
        return {"enrichedProducts": []}

    try:
        # Call the main service function to handle the entire enrichment workflow
        enriched_data = await enrich_products(request.product_names)
        return enriched_data
    except Exception as e:
        # Catch any exceptions raised from the service layer (e.g., LLM failure, validation error)
        # and convert them into a standard HTTP 500 error.
        print(f"ERROR during enrichment process for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the enrichment process: {str(e)}"
        )