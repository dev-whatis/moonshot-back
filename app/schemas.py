"""
(schemas.py) Defines Pydantic models for API requests/responses and
internal OpenAPI schemas for structured outputs from Gemini.
"""

from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel
from typing import List, Optional, Literal, Union
from datetime import datetime

# ==============================================================================
# Pydantic Models for the FastAPI Application
# These define the public-facing API data contracts.
# ==============================================================================

# --- Request Models ---

class StartRequest(BaseModel):
    """Data model for the /start endpoint request body."""
    user_query: str = Field(..., example="I need a good laptop for college")

    # This config makes the API consistent, accepting camelCase for this model too.
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# --- New Answer Models for FinalizeRequest ---

class AnswerOption(BaseModel):
    """Data model for a single selected option within a user's answer."""
    text: str = Field(..., description="The concise label for the option.")
    description: str = Field(..., description="A short explanation of this choice.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class PriceAnswer(BaseModel):
    """
    Data model for the user's answer to the budget question.
    It includes the original question text for full context.
    """
    question_type: Literal["price"] = Field(..., alias="questionType")
    question: str = Field(..., description="The exact question text that was asked.")
    min: Optional[float] = Field(None, description="The minimum budget selected by the user.")
    max: Optional[float] = Field(None, description="The maximum budget selected by the user.")
    
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class DiagnosticAnswer(BaseModel):
    """
    Data model for the user's answer to a single or multi-choice question.
    This structure mirrors the DiagnosticQuestion model, but replaces the full
    list of 'options' with the user's selected 'userAnswers'.
    """
    question_type: Literal["single", "multi"] = Field(..., alias="questionType")
    question: str = Field(..., description="The exact question text that was asked.")
    description: str = Field(..., description="The explanation of why this question was important.")
    user_answers: List[AnswerOption] = Field(
        ..., alias="userAnswers", description="A list of the option(s) the user selected."
    )
    
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

# --- Updated FinalizeRequest to use the new answer models ---
class FinalizeRequest(BaseModel):
    """Data model for the /finalize endpoint request body."""
    conversation_id: Optional[str] = Field(
        None, alias="conversationId", description="The unique ID for the conversation flow. Optional for local testing."
    )
    user_query: str = Field(
        ..., alias="userQuery", description="The original user query, passed back by the client."
    )
    user_answers: List[Union[PriceAnswer, DiagnosticAnswer]] = Field(
        ..., alias="userAnswers", description="A list of the user's answers, matching the new rich format."
    )

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class EnrichRequest(BaseModel):
    """Data model for the /enrich endpoint request body."""
    conversation_id: Optional[str] = Field(
        None, alias="conversationId", description="The ID of the recommendation conversation this enrichment is for. Optional for local testing."
    )
    product_names: List[str] = Field(
        ..., alias="productNames", description="A list of product names to be enriched with images and shopping links."
    )

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class ShareCreateRequest(BaseModel):
    """Data model for the POST /api/share endpoint request body."""
    conversation_id: str = Field(..., alias="conversationId", description="The ID of the conversation to be shared.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class DeepResearchRequest(BaseModel):
    """Data model for the POST /api/research endpoint request body."""
    # This model remains the same
    conversation_id: str = Field(..., alias="conversationId", description="The ID of the conversation to provide user context.")
    product_name: str = Field(..., alias="productName", description="The specific product name to be researched.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class DeepResearchResponse(BaseModel):
    """
    Data model for the immediate, asynchronous response from the POST /api/research endpoint.
    It acknowledges the request and provides the UNIQUE ID to poll for status.
    """
    # --- THIS MODEL IS CHANGED ---
    # It now correctly returns `researchId` instead of `conversationId`.
    research_id: str = Field(..., alias="researchId")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class DeepResearchResultResponse(BaseModel):
    """Data model for the GET /api/research/result/{research_id} endpoint response."""
    # This model remains the same
    report: str = Field(..., description="The full, comprehensive deep research report in Markdown format.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# --- Response Models ---

# NEW MODEL for the asynchronous /finalize endpoint response
class FinalizeResponse(BaseModel):
    """
    Data model for the immediate, asynchronous response from the POST /finalize endpoint.
    It acknowledges the request and provides the ID to poll for status.
    """
    conversation_id: str = Field(..., alias="conversationId")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

# NEW MODEL for the status polling endpoint
class StatusResponse(BaseModel):
    """
    Data model for the GET /status/{conversation_id} endpoint, providing the
    current state of the background job.
    """
    status: str = Field(..., description="The current status of the job (e.g., 'processing', 'complete', 'failed').")


# RENAMED from RecommendationsResponse to ResultResponse
class ResultResponse(BaseModel):
    """Data model for the GET /result/{conversation_id} endpoint response."""
    recommendations: str = Field(..., description="The full recommendation report in Markdown format.")
    product_names: List[str] = Field(..., alias="productNames", description="A list of extracted product names from the Report.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class BudgetObject(BaseModel):
    """Data model for the extracted budget values."""
    min: Optional[float] = None
    max: Optional[float] = None

class BudgetQuestion(BaseModel):
    """Data model for the budget-specific question."""
    question_type: Literal["price"] = Field(..., alias="questionType")
    question: str
    price: BudgetObject

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class DiagnosticQuestionOption(BaseModel):
    """Data model for an option within a diagnostic question."""
    text: str = Field(..., description="The concise label for the option.")
    description: str = Field(..., description="A short explanation of this choice.")

class DiagnosticQuestion(BaseModel):
    """Data model for a single diagnostic (non-budget) question."""
    question_type: Literal["single", "multi"] = Field(..., alias="questionType")
    question: str
    description: str = Field(..., description="An explanation of why this question is important.")
    options: List[DiagnosticQuestionOption]

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class StartResponse(BaseModel):
    """
    Data model for the /start endpoint response body, containing the full
    questionnaire split into budget and diagnostic sections.
    """
    conversation_id: str = Field(..., alias="conversationId")
    budget_question: BudgetQuestion = Field(..., alias="budgetQuestion")
    diagnostic_questions: List[DiagnosticQuestion] = Field(..., alias="diagnosticQuestions")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class StopResponse(BaseModel):
    """Data model for the /stop endpoint response body."""
    status: str = Field(..., example="stopped")
    message: str = Field(..., example="Your session has been terminated.")

class RejectionResponse(BaseModel):
    """
    Data model for the structured rejection response sent to the client
    when the user's query is out-of-scope.
    """
    message: str = "Query cannot be processed."
    reason: str


class ShoppingLink(BaseModel):
    """Data model for a single curated shopping link."""
    source: str = Field(..., description="The name of the store or vendor.", example="Dell.com")
    link: str = Field(..., description="The direct URL to the product page.", example="https://www.dell.com/en-us/shop/...")
    price: str = Field(..., description="The price of the product as a string.", example="$1,199.00")
    delivery: str = Field(..., description="Delivery information, e.g., 'Free shipping'.", example="Free shipping")

class EnrichedProduct(BaseModel):
    """Data model for a single product enriched with images and shopping links."""
    product_name: str = Field(..., alias="productName", description="The name of the product.")
    images: List[str] = Field(..., description="A list of curated image URLs for the product.")
    shopping_links: List[ShoppingLink] = Field(..., alias="shoppingLinks", description="A list of curated shopping links for the product.")
    
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class EnrichResponse(BaseModel):
    """Data model for the /enrich endpoint response body."""
    enriched_products: List[EnrichedProduct] = Field(..., alias="enrichedProducts")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class ShareCreateResponse(BaseModel):
    """Data model for the POST /api/share endpoint response body."""
    share_id: str = Field(..., alias="shareId", description="The unique, public ID for the shared recommendation.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class DeepResearchShareData(BaseModel):
    """Data model for a single deep research report included in a share response."""
    product_name: str = Field(..., alias="productName", description="The name of the product that was researched.")
    report: str = Field(..., description="The full Markdown report for the product.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class ShareDataResponse(BaseModel):
    """
    Data model for the public GET /api/share/{shareId} endpoint.
    Contains all the data needed to render a shared recommendation page,
    including any associated deep research reports.
    """
    user_query: str = Field(..., alias="userQuery", description="The original user query that initiated the recommendation.")
    recommendations: str = Field(..., description="The full recommendation report in Markdown format.")
    product_names: List[str] = Field(..., alias="productNames", description="A list of extracted product names from the Report.")
    enriched_products: List[EnrichedProduct] = Field(..., alias="enrichedProducts", description="The enriched data for the recommended products.")
    deep_research_reports: List[DeepResearchShareData] = Field(
        ..., alias="deepResearchReports", description="A list of all completed deep research reports associated with the conversation."
    )

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class HistoryUpdateRequest(BaseModel):
    """Data model for the PATCH /api/history/{conversationId} endpoint body."""
    title: str = Field(..., description="The new user-defined title for the conversation.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class HistorySummaryItem(BaseModel):
    """Data model for a single item in the user's history list."""
    conversation_id: str = Field(..., alias="conversationId")
    title: str = Field(..., description="The title of the conversation, either user-defined or the original query.")
    created_at: datetime = Field(..., alias="createdAt", description="The timestamp when the conversation was started.")
    status: str = Field(..., description="The final status of the conversation (e.g., 'complete', 'failed').")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class HistoryListResponse(BaseModel):
    """Data model for the GET /api/history endpoint response."""
    history: List[HistorySummaryItem]
    next_cursor: Optional[str] = Field(None, alias="nextCursor", description="The cursor to use for fetching the next page of results. Null if this is the last page.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

# ==============================================================================
# Internal OpenAPI Schemas for Gemini Interactions
# ==============================================================================

# Step 0: Guardrail for Intent Classification
GUARDRAIL_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_product_request": {
            "type": "boolean",
            "description": "True if the query is a request for a physical product, otherwise False."
        },
        "reason": {
            "type": "string",
            "description": "A brief, user-facing explanation for why the query was rejected."
        }
    },
    "required": ["is_product_request", "reason"]
}

# Schemas for Step 1 (GUIDE_SEARCH_TERM_SCHEMA) and Step 2 (GUIDE_SEARCH_URLS_SCHEMA)
# have been removed as they are no longer in use.


# Step 3a: Budget Question Generation
BUDGET_QUESTION_SCHEMA = {
  "type": "object",
  "properties": {
    "questionType": {
      "type": "string",
      "description": "The type of question, which is always 'price' for this step.",
      "enum": ["price"]
    },
    "question": {
      "type": "string",
      "description": "The budget-related question to ask the user. This text will vary based on whether a budget was found in the initial query."
    },
    "price": {
      "type": "object",
      "description": "The budget values extracted from the query.",
      "properties": {
        "min": {
          "type": "number",
          "nullable": True,
          "description": "The minimum budget. Use null if not specified."
        },
        "max": {
          "type": "number",
          "nullable": True,
          "description": "The maximum budget. Use null if not specified."
        }
      },
      "required": ["min","max"]
    }
  },
  "required": ["questionType","question","price"]
}

# Step 3b: Diagnostic Question Generation
DIAGNOSTIC_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "description": "An array of 3-4 non-budget-related questions to ask the user.",
            "items": {
                "type": "object",
                "properties": {
                    "questionType": {
                        "type": "string",
                        "description": "The type of question.",
                        "enum": ["single", "multi"]
                    },
                    "question": {
                        "type": "string",
                        "description": "The main text of the question presented to the user."
                    },
                    "description": {
                        "type": "string",
                        "description": "A brief explanation of why this question is important, educating the user on the key consideration it addresses."
                    },
                    "options": {
                        "type": "array",
                        "description": "A list of choices for the question.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "The concise label for the option (e.g., 'All-day Comfort')."
                                },
                                "description": {
                                    "type": "string",
                                    "description": "A short explanation of this specific choice, often highlighting a key benefit or trade-off."
                                }
                            },
                            "required": ["text", "description"]
                        }
                    }
                },
                "required": ["questionType", "question", "description", "options"]
            }
        }
    },
    "required": ["questions"]
}


# Step R2: Research Strategy Generation
RESEARCH_STRATEGY_SCHEMA = {
  "type": "object",
  "properties": {
    "deepDiveQueries": {
      "type": "array",
      "description": "A list of 2 strategic search queries designed to find products matching the user's synthesized needs and priorities.",
      "items": {
        "type": "string",
        "description": "A single, precise search query string"
      }
    }
  },
  "required": ["deepDiveQueries"]
}

# Step 5: Final Website Selection
REC_SEARCH_URLS_SCHEMA = {
    "type": "object",
    "properties": {
        "rec_search_urls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string"
                    },
                    "url": {
                        "type": "string"
                    }
                },
                "required": ["title", "url"]
            }
        }
    },
    "required": ["rec_search_urls"]
}


IMAGE_CURATION_SCHEMA = {
    "type": "object",
    "properties": {
        "curatedImages": {
            "type": "array",
            "description": "A list of image curation objects, one for each product in the input.",
            "items": {
                "type": "object",
                "properties": {
                    "productName": {
                        "type": "string",
                        "description": "The name of the product, copied from the input."
                    },
                    "images": {
                        "type": "array",
                        "description": "A list of 3-4 selected image URLs.",
                        "items": {"type": "string"}
                    }
                },
                "required": ["productName", "images"]
            }
        }
    },
    "required": ["curatedImages"]
}

SHOPPING_CURATION_SCHEMA = {
    "type": "object",
    "properties": {
        "curatedShoppingLinks": {
            "type": "array",
            "description": "A list of shopping link curation objects, one for each product in the input.",
            "items": {
                "type": "object",
                "properties": {
                    "productName": {
                        "type": "string",
                        "description": "The name of the product, copied from the input."
                    },
                    "shoppingLinks": {
                        "type": "array",
                        "description": "A list of the top 2 selected shopping links.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "link": {"type": "string"},
                                "price": {"type": "string"},
                                "delivery": {"type": "string"}
                            },
                            "required": ["source", "link", "price", "delivery"]
                        }
                    }
                },
                "required": ["productName", "shoppingLinks"]
            }
        }
    },
    "required": ["curatedShoppingLinks"]
}

# Step DR1: Deep Research Website Selection
DEEP_RESEARCH_URL_SELECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "selected_urls": {
            "type": "array",
            "description": "A list of the 3-5 most valuable and diverse websites for in-depth analysis.",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The title of the selected web page."
                    },
                    "url": {
                        "type": "string",
                        "description": "The URL of the selected web page."
                    }
                },
                "required": ["title", "url"]
            }
        }
    },
    "required": ["selected_urls"]
}