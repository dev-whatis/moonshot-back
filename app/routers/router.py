"""
(router.py) Defines the initial "path routing" endpoint for the API.
This router analyzes the user's initial query and determines which
workflow to start (e.g., a product discovery or a quick decision).
"""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List

# Import services and handlers
from app.services import llm_calls

# Import the Pydantic schemas for this specific flow
from app.schemas import (
    StartRequest,
    StartResponse,
    RejectionResponse,
    ProductDiscoveryPayload,
    QuickDecisionPayload,
    StandardMCQ,
    StandardOption
)

# Import the dependency for authentication
from app.middleware.auth import get_current_user

# ==============================================================================
# Router Setup
# ==============================================================================

router = APIRouter(
    prefix="/api/routes",
    tags=["Path Routing"]
)

# ==============================================================================
# Path Routing Endpoint
# ==============================================================================

@router.post(
    "/start",
    response_model=StartResponse,
    summary="Route user query to the correct starting path",
    responses={
        422: {"model": RejectionResponse, "description": "Query was rejected as out-of-scope."}
    }
)
async def route_user_query(
    request: StartRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Analyzes the user's initial query and routes it to the appropriate starting path.

    - **PRODUCT_DISCOVERY**: For queries involving product discovery.
    - **QUICK_DECISION**: For queries involving quick decisions.
    - **REJECT**: For queries that are out-of-scope.
    """
    print(f"User {user_id} | Path Router | Routing query: '{request.user_query}'")

    # --- STEP 1: Get the route from the LLM Router ---
    router_result = llm_calls.run_query_router(request.user_query)
    route = router_result.get("route")

    # --- STEP 2: Execute logic based on the determined route ---

    # --- Path 1: REJECT ---
    if route == "REJECT":
        print(f"User {user_id} | Path: REJECT | Query rejected.")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Query cannot be processed.",
                "reason": "The query was determined to be out-of-scope."
            }
        )

    # --- Path 2: PRODUCT_DISCOVERY (The full questionnaire flow) ---
    elif route == "PRODUCT_DISCOVERY":
        print(f"User {user_id} | Path: PRODUCT_DISCOVERY | Generating questionnaire...")
        try:
            # Run the two question-generation tasks concurrently for speed
            budget_task = asyncio.to_thread(
                llm_calls.generate_budget_question, request.user_query
            )
            diagnostics_task = asyncio.to_thread(
                llm_calls.generate_diagnostic_questions, request.user_query
            )

            budget_question, raw_diagnostic_questions = await asyncio.gather(
                budget_task,
                diagnostics_task
            )

            # --- START: Transformation "Stop-Gap" Logic ---
            # The LLM still returns descriptions, but we transform the data to
            # our new, clean `StandardMCQ` schema before sending it to the client.
            standardized_diagnostic_questions: List[StandardMCQ] = []
            for raw_q in raw_diagnostic_questions:
                # 1. Create standardized options, discarding descriptions.
                standard_options = [StandardOption(text=opt['text']) for opt in raw_q.get('options', [])]
                
                # 2. Create the standardized question, discarding its description.
                standard_question = StandardMCQ(
                    question_type=raw_q.get('questionType'),
                    question=raw_q.get('question'),
                    options=standard_options
                )
                standardized_diagnostic_questions.append(standard_question)
            # --- END: Transformation Logic ---


            # Assemble the payload using the NEWLY standardized questions.
            payload = ProductDiscoveryPayload(
                budget_question=budget_question,
                diagnostic_questions=standardized_diagnostic_questions
            )

            return StartResponse(route="PRODUCT_DISCOVERY", payload=payload)

        except Exception as e:
            print(f"ERROR during PRODUCT_DISCOVERY generation for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred while generating the questionnaire: {e}"
            )

    # --- Path 3: QUICK_DECISION ---
    elif route == "QUICK_DECISION":
        print(f"User {user_id} | Path: QUICK_DECISION | Analyzing for questions and location needs...")
        try:
            # The LLM call for this path has been simplified to directly produce
            # data that conforms to the new StandardMCQ schema. No transformation is needed.
            quick_decision_analysis = await asyncio.to_thread(
                llm_calls.generate_quick_questions, request.user_query
            )
            
            # Extract the list of questions (may be empty)
            questions_list = quick_decision_analysis.get("questions", [])
            
            # Extract the location flag (defaults to False for safety)
            location_needed = quick_decision_analysis.get("needLocation", False)

            print(f"User {user_id} | Analysis complete: needLocation={location_needed}, num_questions={len(questions_list)}")

            # Assemble the payload. Pydantic will validate that `questions_list`
            # now correctly matches the `List[StandardMCQ]` type.
            payload = QuickDecisionPayload(
                need_location=location_needed,
                quick_questions=questions_list
            )

            # Return the response. The frontend now has all the info it needs to proceed.
            return StartResponse(route="QUICK_DECISION", payload=payload)

        except Exception as e:
            print(f"ERROR during QUICK_DECISION generation for user {user_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred during the quick decision analysis: {e}"
            )

    # --- Fallback: Handle unexpected route values ---
    else:
        print(f"ERROR: Unrecognized route '{route}' returned by the LLM for user {user_id}.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"The routing process failed due to an unrecognized route: {route}"
        )