"""
(enrich.py) Defines the API route for the product enrichment feature.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

# Import the main service function
from app.services.enrichment_service import enrich_products

# Import schemas (Pydantic models)
from app.schemas import EnrichRequest, EnrichResponse

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# Import the logging functions
from app.services.logging_service import log_step, update_history_with_enrichment

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
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Accepts a list of product names and returns curated image and shopping
    link information for each. If a conversationId is provided, the
    enrichment data is logged and linked to the original recommendation.

    This endpoint orchestrates a multi-step process:
    1.  Performs parallel image and shopping searches for each product name.
    2.  Aggregates the raw search results.
    3.  Uses parallel LLM calls to curate the best images and shopping links.
    4.  Returns the structured, curated data and logs it in the background.
    """
    # The conversation ID from the request is now the primary identifier for logging.
    conv_id = request.conversation_id
    print(f"User {user_id} | Starting enrichment for {len(request.product_names)} products. Conv_id: {conv_id}")

    if not request.product_names:
        # Handle the case of an empty request list to avoid unnecessary processing
        return {"enrichedProducts": []}

    try:
        # Call the main service function to handle the entire enrichment workflow
        enriched_data = await enrich_products(request.product_names)
        
        # --- LOGGING ON SUCCESS ---
        # The logging functions will internally check if logging is enabled.
        
        # 1. Log the enrichment step trace to GCS
        enrich_log_payload = {
            "userId": user_id,
            "productNames": request.product_names,
            "enrichedProducts": enriched_data["enrichedProducts"]
        }
        background_tasks.add_task(log_step, conv_id, "03_enrich", enrich_log_payload)

        # 2. Update the existing history document in Firestore with enriched data
        background_tasks.add_task(
            update_history_with_enrichment,
            conv_id,
            enriched_data["enrichedProducts"]
        )
        # --- END LOGGING ---
        
        return enriched_data
        
    except Exception as e:
        # Catch any exceptions raised from the service layer and log them
        print(f"ERROR during enrichment process for user {user_id}, conv_id: {conv_id}: {e}")
        
        failure_log_payload = {
            "userId": user_id,
            "productNames": request.product_names,
            "error": str(e)
        }
        background_tasks.add_task(log_step, conv_id, "03_enrich_failure", failure_log_payload)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the enrichment process: {str(e)}"
        )