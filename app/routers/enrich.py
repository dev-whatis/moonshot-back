"""
(enrich.py) Defines the API route for the product enrichment feature.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks

# Import the main service function
from app.services.enrichment_service import enrich_products

# Import schemas (Pydantic models)
from app.schemas import EnrichTurnRequest, EnrichResponse

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# Import the logging functions
from app.services.logging_service import update_turn_with_enrichment

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
    request: EnrichTurnRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Accepts a list of product names and returns curated image and shopping
    link information for each. The enrichment data is then saved to the
    specific turn within the conversation.
    """
    conv_id = request.conversation_id
    turn_id = request.turn_id
    print(f"User {user_id} | Starting enrichment for conv {conv_id}, turn {turn_id}.")

    if not request.product_names:
        return {"enrichedProducts": []}

    try:
        # The core enrichment logic is unchanged
        enriched_data = await enrich_products(request.product_names)
        
        # Update the specific turn document in Firestore with enriched data
        background_tasks.add_task(
            update_turn_with_enrichment,
            conv_id,
            turn_id,
            enriched_data["enrichedProducts"]
        )
        
        return enriched_data
        
    except Exception as e:
        print(f"ERROR during enrichment for user {user_id}, conv {conv_id}, turn {turn_id}: {e}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during the enrichment process: {str(e)}"
        )