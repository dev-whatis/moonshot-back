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
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# We import the same schemas to ensure the dummy data matches the real API contract.
# These imports are updated to reflect the new structure.
from app.schemas import (
    StartRequest,
    FinalizeRequest,
    EnrichRequest,
    StartResponse,
    RecommendationsResponse,
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
# This is the exact Markdown from the example you provided earlier.
DUMMY_FINALIZE_MARKDOWN = """
## Executive Summary
This report analyzes expert reviews to identify the best headphone recommendations tailored to your specific needs. Your primary goal is to find headphones primarily for at-home focused listening or entertainment, with all-day comfort and a lightweight design being your absolute top priority. You also expressed a strong desire for durability, as past headphones have broken easily.

Based on a thorough review of the provided expert data, two products have been identified as Top Recommendations that closely align with your core requirements, offering exceptional comfort, durability, and sound quality suitable for home listening. Additionally, two Strategic Alternatives are presented, offering different value propositions or trade-offs while still addressing your key needs.

Below is a detailed analysis of the best options based on expert data.

## Top Recommendations
### Focal Utopia
- **Price:** Very Expensive (explicitly noted as "a shade under four grand" in one review)
- **Justification:** The Focal Utopia stands out as an exceptional choice for your desire for all-day comfort and lightweight design coupled with high-fidelity sound for focused listening. Expert reviews consistently praise its comfort, stating they are "comfortable for long listening sessions" and are "light and incredibly well-built." This directly addresses your priority for comfort and your concern about headphones breaking easily, as they are described as an "endgame product" that the reviewer would choose "for the rest of the time." Its open-back design and "endgame-level sound" with "natural acoustics and a huge, engaging soundstage" make it almost perfect for every musical genre and ideally suited for immersive at-home entertainment and focused listening. The premium materials like "Carbon/Metal/Leather Finishing" further reinforce its durability.
- **Noteworthy Considerations:** The most significant drawback is its extremely high cost, which is explicitly noted as "Expensive" and "out of reach for most headphone enthusiasts." While the product is lauded for its build quality, specific mention of sweat resistance for this high-end, at-home focused headphone was not a primary feature highlighted in the review data.

### Monolith by Monoprice M565C
- **Price:** Wired headphones, typically under $200 (implied by context of "affordable and sturdy enough that you won't be afraid to take them with you to work or school")
- **Justification:** The Monolith by Monoprice M565C is an excellent recommendation for its sturdy, comfortable build and suitability for focused listening. Reviews highlight its "sturdy, comfortable build" and, notably, offer a five-year warranty, which is "about the longest of any headphones we’ve seen." This directly addresses your frustration with headphones breaking easily, providing significant peace of mind regarding durability. The headphones feature "planar-magnetic drivers" housed in isolating closed-back ear cups, allowing you to "block out distractions and focus on enjoying your playlist" at home. Its sound is described as "exciting, detailed," and "suitable for any genre of music," ensuring a quality listening experience.
- **Noteworthy Considerations:** This model is noted as having a "bulkier design" and does not fold up compactly, which is less of a concern for at-home use. Some panelists noted it "doesn’t deliver quite as much presence in the mids as we’d like, and some of our panelists would have preferred a little extra sparkle on the highs." Information on sweat resistance was not available in the provided data.

## Strategic Alternatives
### Sony MDR-7506
- **Price:** Under $100 (explicitly stated in review data)
- **Angle:** This alternative offers exceptional reliability and comfort at a highly accessible price point, making it a robust, budget-friendly option for at-home use.
- **Trade-Off Analysis:**
    - **Compromise:** Wired Connection and Studio-Oriented Sound: This is a wired-only headphone, lacking the wireless freedom of some modern options. While providing "accurate-sounding bass, mids, and treble," its sound profile is primarily designed for "studio and live-audio" production, which might be less "musical" than audiophile-tuned headphones. The "long, coiled cable" can be "cumbersome for listening to music from your phone," but less so for stationary home use.
    - **Benefit:** Unmatched Durability and Proven Comfort: The Sony MDR-7506 has been a "longtime studio and live-audio staple" due to its durable, comfortable, and reliable nature, described as "industry standard for a reason." Its "lightweight plastic build is fairly comfortable," and its robust design directly addresses your concern about headphones breaking easily.

### Hifiman HE400SE
- **Price:** Affordable (described as "low price" and "entry-level audiophile headphone")
- **Angle:** This alternative provides an excellent entry into high-quality audiophile sound with a strong emphasis on all-day comfort and durability, all within a budget-friendly range.
- **Trade-Off Analysis:**
    - **Compromise:** Lacks Peak Technical Performance: While offering good sound, it "Lacks technical performance of more expensive models" and uses "More plastic... to keep price down" compared to premium options. Its open-back design means "sound leak," making it "Not the best for portable use" outside of a private home environment.
    - **Benefit:** Exceptional Comfort and Longevity for Value: These headphones are "Comfortable with good padding," weighs only 350g, so they can be worn all day and built to last for years. This directly satisfies your top priorities for comfort and durability. As an "entry-level audiophile headphone," it offers "Warm, detailed sound" and is an "excellent option" for focused listening at home, particularly for those wanting to "experiment with planar drivers" without a high investment.

## Concluding Remarks
Your decision hinges on balancing premium, "endgame-level" audio and build quality with potentially higher costs (Focal Utopia, Monolith M565C) against highly durable and comfortable, yet more budget-conscious, alternatives (Sony MDR-7506, Hifiman HE400SE). Each recommended product directly addresses your core needs for all-day comfort and durability for at-home focused listening. This report aims to empower you to make an informed choice based on verified expert insights.
"""

DUMMY_FINALIZE_RESPONSE = {
    "recommendations": DUMMY_FINALIZE_MARKDOWN,
    "productNames": [],
    "strategicAlternatives": ["Sony MDR-7506", "Hifiman HE400SE"],
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
                },
                {
                    "source": "Amazon.com",
                    "link": "https://www.amazon.com/Bose-QuietComfort-Wireless-Cancelling-Headphones/dp/B0CCZ1L489",
                    "price": "$449.00",
                    "delivery": "Free Shipping",
                },
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
                },
                 {
                    "source": "Amazon.com",
                    "link": "https://www.amazon.com/Sony-WH-1000XM6-Headphones-Microphones-Studio-Quality/dp/B0F3PQHWTZ",
                    "price": "$498.99",
                    "delivery": "FREE delivery",
                },
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
    return response_data


@app.post("/api/recommendations/finalize", response_model=RecommendationsResponse, tags=["Dummy Recommendations"])
async def dummy_finalize_recommendation(request: FinalizeRequest):
    """

    Returns a hardcoded recommendation report. Ignores the request body but prints it.
    """
    print(f"Received /finalize request for conv_id: '{request.conversation_id}'.")
    # Log the received answers to the console to help with frontend debugging
    print("User answers received:")
    # The .model_dump() method provides a clean dictionary representation of the Pydantic models
    print(request.model_dump(by_alias=True)['userAnswers'])
    time.sleep(15)  # Add a small delay to simulate processing time
    return DUMMY_FINALIZE_RESPONSE


@app.post("/api/enrich", response_model=EnrichResponse, tags=["Dummy Enrichment"])
async def dummy_get_product_enrichment(request: EnrichRequest):
    """
    Returns hardcoded enrichment data. Ignores the request body.
    """
    print(f"Received /enrich request for {len(request.product_names)} products. Returning dummy data.")
    time.sleep(1.5)  # Add a small delay to simulate processing time
    return DUMMY_ENRICH_RESPONSE