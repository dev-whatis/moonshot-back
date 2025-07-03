"""
(dummy_main.py) A simple, self-contained dummy/mock backend for the
Product Recommendation API.

This server does not perform any logic. It simply returns pre-canned,
hardcoded data for each endpoint. It is intended for frontend development
and testing when the real backend is not available or needed.

To run:
1. Make sure the updated 'app/schemas.py' is available.
2. Install dependencies: pip install -r requirements_dummy.txt
3. Run the server: uvicorn dummy_main:app --reload
"""

import uuid
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# We import the same schemas to ensure the dummy data matches the real API contract.
# These imports are updated to reflect the new structure.
from app.schemas import (
    StartRequest,
    FinalizeRequest,
    EnrichRequest,
    StartResponse,
    FinalizeResponse,      # New
    StatusResponse,        # New
    ResultResponse,        # Renamed
    EnrichResponse,
    BudgetQuestion,
    DiagnosticQuestion
)

# ==============================================================================
# Canned Data Section
#
# All hardcoded responses are defined here.
# Simply edit these dictionaries to change what the dummy API returns.
# ==============================================================================

# --- Data for the /start endpoint ---
# This data now perfectly matches the structure of the StartResponse schema.
DUMMY_START_RESPONSE = {
    "conversationId": f"dummy-conv-{uuid.uuid4()}",
    "budgetQuestion": {
        "questionType": "price",
        "question": "What is your approximate budget? (This is a dummy response)",
        "price": {
            "min": None,
            "max": None,
        }
    },
    "diagnosticQuestions": [
        {
            "questionType": "single",
            "question": "Which statement best describes your primary use for these headphones?",
            "description": "This helps determine if you need features like noise cancellation for travel or a high-quality microphone for gaming.",
            "options": [
                {"text": "At-home focused listening", "description": "Prioritizes pure sound quality in a quiet environment."},
                {"text": "Commuting and travel", "description": "Prioritizes noise cancellation and portability."},
                {"text": "Fitness and exercise", "description": "Prioritizes sweat resistance and a secure fit."},
                {"text": "Gaming", "description": "Prioritizes a built-in microphone and surround sound."},
                {"text": "other", "description": "Please specify if your use case is not listed."}
            ]
        },
        {
            "questionType": "single",
            "question": "If you could perfect only ONE aspect of your headphones, which would it be?",
            "description": "Understanding your absolute top priority helps us make the right trade-offs in recommendations.",
            "options": [
                {"text": "Absolute best sound quality", "description": "Sound fidelity is more important than any other feature."},
                {"text": "Maximum noise cancellation", "description": "Blocking out the world is the most critical function."},
                {"text": "All-day comfort", "description": "A lightweight, comfortable design for long sessions is key."},
                {"text": "Ultimate durability", "description": "Build quality and longevity are the most important factors."}
            ]
        },
        {
            "questionType": "multi",
            "question": "Which of these features are important to you? (select all that apply)",
            "description": "Select any additional features that are must-haves for your new headphones.",
            "options": [
                {"text": "Wireless connectivity", "description": "Connect via Bluetooth without any cables."},
                {"text": "A built-in microphone for calls", "description": "Essential for taking phone or video calls."},
                {"text": "Long battery life (15+ hours)", "description": "Ensures your headphones last all day on a single charge."},
                {"text": "Other", "description": "Please specify if you have other must-have features."}
            ]
        }
    ]
}


# --- Data for the /finalize endpoint ---
# This is a new dummy markdown that matches the updated prompt structure.
DUMMY_FINALIZE_MARKDOWN = """
#### The Bottom Line
Alright, after digging through the expert reviews and looking at your needs, it's pretty clear. For your goal of finding comfortable headphones for at-home listening, the **Bose QuietComfort Ultra** is your best bet. If you're willing to prioritize a more studio-focused sound and save a bit, the **Sony WH-1000XM6** is an incredibly smart choice. Here's how I got there.

---

#### Your Top Pick: Bose QuietComfort Ultra
*   **The Vibe:** The reliable, no-drama workhorse.
*   **Why it's the one for you:**
    *   **Nails your #1 priority:** You said you needed all-day comfort. The review from The Verge confirms this, describing its fit as 'supremely comfortable for long sessions'.
    *   **Perfect for your needs:** You mentioned using it for focused listening, and its world-class noise cancellation is ideal for that, with Rtings noting it 'blocks out an outstanding amount of ambient noise.'
*   **Things to know before you buy:**
    *   **The Catch:** It's pricey. You're paying a premium for the Bose brand and its noise-cancellation tech.
    *   **Information Gap:** I couldn't find consistent data on its long-term durability past the one-year mark in the reviews I analyzed.

---

#### The Smart Alternative: Sony WH-1000XM6
*   **The Vibe:** The budget champion that punches way above its weight.
*   **The Trade-Off Story:** The main story here is **Noise Cancellation vs. Audio Purity**. With this option, you save approximately $50. In return, you're trading the absolute best noise cancellation of the Bose for a sound signature that many audio engineers prefer for its accuracy.
*   **The Main Caveat:** While still very comfortable, most reviews agree the Bose has a slight edge in plushness for multi-hour wear.

---

#### My Final Advice
This decision comes down to what you value more. If you want the best possible cone of silence for focus, the **Bose QuietComfort Ultra** is a confident 'buy-it-and-love-it' choice. If you are a discerning listener who appreciates a more neutral sound and wants to save some money, the **Sony WH-1000XM6** is the more pragmatic play. You can't go wrong.

---
### RECOMMENDATIONS
- Bose QuietComfort Ultra
- Sony WH-1000XM6
"""

DUMMY_RESULT_RESPONSE = {
    "recommendations": DUMMY_FINALIZE_MARKDOWN,
    "productNames": ["Bose QuietComfort Ultra", "Sony WH-1000XM6"],
}


# --- Data for the /enrich endpoint ---
DUMMY_ENRICH_RESPONSE = {
    "enrichedProducts": [
        {
            "productName": "Bose QuietComfort Ultra",
            "images": [
                "https://pisces.bbystatic.com/image2/BestBuy_US/images/products/51bd8caa-f809-4310-90b6-f02d576ca1ef.jpg;maxHeight=828;maxWidth=400?format=webp",
                "https://assets.bosecreative.com/transform/775c3e9a-fcd1-489f-a2f7-a57ac66464e1/SF_QCUH_deepplum_gallery_1_816x612_x2?quality=90&io=width:816,height:667,transform:fit&io=width:816,height:667,transform:fit",
                "https://assets.bosecreative.com/transform/1f0656f9-6d98-4082-b253-ba3655338262/SF_QCUH_lunarblue_gallery_1_816x612_x2?quality=100",
                "https://m.media-amazon.com/images/I/51ZR4lyxBHL.jpg"
            ],
            "shoppingLinks": [
                {
                    "source": "Bose",
                    "link": "https://www.bose.com/p/headphones/bose-quietcomfort-ultra-headphones/QCUH-HEADPHONEARN.html",
                    "price": "$449.00",
                    "delivery": "Free Shipping",
                }
            ],
        },
        {
            "productName": "Sony WH-1000XM6",
            "images": [
                "https://d1ncau8tqf99kp.cloudfront.net/converted/128978_original_local_1200x1050_v3_converted.webp",
                "https://d1ncau8tqf99kp.cloudfront.net/converted/128962_original_local_1200x1050_v3_converted.webp",
                "https://m.media-amazon.com/images/I/61nGlYFDZNL.jpg",
            ],
            "shoppingLinks": [
                {
                    "source": "Sony",
                    "link": "https://electronics.sony.com/audio/headphones/headband/p/wh1000xm6-b",
                    "price": "$449.99",
                    "delivery": "Free Standard US Shipping",
                }
            ],
        },
        {
            "productName": "Apple AirPods Max",
            "images": [
                "https://m.media-amazon.com/images/I/81thV7SoLZL._UF894,1000_QL80_.jpg",
                "https://www.pcrichard.com/dw/image/v2/BFXM_PRD/on/demandware.static/-/Sites-pcrichard-master-product-catalog/default/dw88ab344d/images/hires/Z_MWW43AM-A.jpg?sw=800&sh=800&sm=fit",
                "https://store.storeimages.cdn-apple.com/1/as-images.apple.com/is/og-airpods-max-202409?wid=1200&hei=630&fmt=jpeg&qlt=95&.v=1724144125817",
            ],
            "shoppingLinks": [
                {
                    "source": "Apple",
                    "link": "https://www.apple.com/airpods-max/",
                    "price": "$549.00",
                    "delivery": "$9.99 shipping",
                },
            ],
        },
        {
            "productName": "Sennheiser MOMENTUM 4",
            "images": [
            ],
            "shoppingLinks": [
            ],
        },
        # You can add the other two products here if desired
    ]
}


# ==============================================================================
# FastAPI App Initialization
# ==============================================================================

app = FastAPI(
    title="Dummy Product Recommendation API",
    description="A mock API that provides pre-canned data for frontend development.",
    version="1.0.0-dummy"
)

# --- CORS middleware ---
# This allows the frontend running on a different port/domain to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # local dev url
        "https://www.recmonkey.com"  # website url
    ],
    # Regex to allow any Cloudflare Pages preview deployment to access the API
    allow_origin_regex=r"^https://[A-Za-z0-9-]+\.moonshot-front-f4u\.pages\.dev$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Dummy API Endpoints
# ==============================================================================

@app.get("/", tags=["Health Check"])
async def root():
    """A simple health check endpoint."""
    return {"status": "ok", "message": "Welcome to the Dummy Product Recommendation API!"}


@app.post("/api/recommendations/start", response_model=StartResponse, tags=["Dummy Recommendations"])
async def dummy_start_recommendation(request: StartRequest):
    """
    Returns a hardcoded list of questions. Ignores the request body.
    """
    print(f"Received /start request for query: '{request.user_query}'. Returning dummy questions.")
    # We generate a new dummy conversation ID for each call to mimic real behavior
    response_data = DUMMY_START_RESPONSE.copy()
    response_data["conversationId"] = f"dummy-conv-{uuid.uuid4()}"
    time.sleep(5)  # Simulate a small processing delay
    return response_data


# --- MODIFICATION: New global state to track dummy jobs ---
# This dictionary will store the state of our "in-progress" jobs.
# The key is the conversation_id.
# The value is a dictionary like: {"status": "processing", "startTime": 12345.67}
dummy_jobs = {}

# The time in seconds the dummy finalize job should take to "complete".
DUMMY_PROCESSING_TIME_SECONDS = 5


@app.post("/api/recommendations/finalize", response_model=FinalizeResponse, status_code=202, tags=["Dummy Recommendations"])
async def dummy_finalize_recommendation(request: FinalizeRequest):
    """
    Accepts the finalize request, logs it, and simulates starting a background job.
    Returns immediately with a 202 Accepted.
    """
    conv_id = request.conversation_id
    print(f"Received /finalize request for conv_id: '{conv_id}'. Simulating job start.")
    # Log the received answers to the console to help with frontend debugging
    print("User answers received:")
    print(request.model_dump(by_alias=True)['userAnswers'])
    
    # Store the job's state
    dummy_jobs[conv_id] = {
        "status": "processing",
        "startTime": time.time()
    }
    
    return {"conversationId": conv_id}


@app.get("/api/recommendations/status/{conversation_id}", response_model=StatusResponse, tags=["Dummy Recommendations"])
async def dummy_get_job_status(conversation_id: str):
    """
    Checks the status of a simulated job.
    """
    job = dummy_jobs.get(conversation_id)

    if not job:
        # This case is unlikely if the frontend flow is correct, but good to have.
        return {"status": "failed"}

    if job["status"] == "complete":
        return {"status": "complete"}

    # Check if the processing time has elapsed
    if time.time() - job["startTime"] > DUMMY_PROCESSING_TIME_SECONDS:
        job["status"] = "complete" # Update the state to complete
        print(f"Job for conv_id '{conversation_id}' is now complete.")
        return {"status": "complete"}
    else:
        # If not enough time has passed, it's still processing
        return {"status": "processing"}


@app.get("/api/recommendations/result/{conversation_id}", response_model=ResultResponse, tags=["Dummy Recommendations"])
async def dummy_get_job_result(conversation_id: str):
    """
    Returns the hardcoded recommendation report if the job is 'complete'.
    """
    job = dummy_jobs.get(conversation_id)

    # Only return the result if the job is marked as complete
    if job and job.get("status") == "complete":
        print(f"Returning final result for conv_id: '{conversation_id}'.")
        return DUMMY_RESULT_RESPONSE
    else:
        # This simulates the real backend's 422 error if the result is not ready.
        job_status = job.get("status") if job else "not found"
        print(f"Result for conv_id '{conversation_id}' was requested, but job status is '{job_status}'.")
        raise HTTPException(
            status_code=422,
            detail=f"Job status is '{job_status}'. Result is not ready."
        )


@app.post("/api/enrich", response_model=EnrichResponse, tags=["Dummy Enrichment"])
async def dummy_get_product_enrichment(request: EnrichRequest):
    """
    Returns hardcoded enrichment data. Ignores the request body.
    """
    print(f"Received /enrich request for {len(request.product_names)} products. Returning dummy data.")
    time.sleep(5)  # Add a small delay to simulate processing time
    return DUMMY_ENRICH_RESPONSE