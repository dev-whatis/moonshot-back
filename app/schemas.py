"""
(schemas.py) Defines Pydantic models for API requests/responses and
internal OpenAPI schemas for structured outputs from Gemini.
"""

from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel
from typing import List, Optional, Literal, Union

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


class BudgetAnswer(BaseModel):
    """Data model for a price range answer provided by the user."""
    min: Optional[float] = None
    max: Optional[float] = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class UserAnswer(BaseModel):
    """
    Data model for a single Question & Answer pair provided by the user.
    This model is flexible to handle different answer types from the new questionnaire.
    """
    question: str = Field(..., description="The exact question text that was asked.")
    question_type: Literal["price", "single", "multi"] = Field(
        ..., alias="questionType", description="The type of question that was asked."
    )
    is_other: Optional[bool] = Field(
        False, alias="isOther", description="True if the user selected an 'Other' option to provide a custom value."
    )
    answer: Union[str, List[str], BudgetAnswer] = Field(
        ..., description="The user's answer, formatted based on the question type."
    )

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class FinalizeRequest(BaseModel):
    """Data model for the /finalize endpoint request body."""
    conversation_id: Optional[str] = Field(
        None, alias="conversationId", description="The unique ID for the conversation flow. Optional for local testing."
    )
    user_query: str = Field(
        ..., alias="userQuery", description="The original user query, passed back by the client."
    )
    user_answers: List[UserAnswer] = Field(
        ..., description="A list of the user's answers to the questionnaire."
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


# --- Response Models ---

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


class RecommendationsResponse(BaseModel):
    """Data model for the /finalize endpoint response body."""
    recommendations: str = Field(..., description="The full recommendation report in Markdown format.")
    product_names: List[str] = Field(..., alias="productNames", description="A list of extracted product names from the 'Top Recommendations' section.")
    strategic_alternatives: List[str] = Field(..., alias="strategicAlternatives", description="A list of extracted product names from the 'Strategic Alternatives' section.")

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


# Step 4: Search Query Generation
REC_SEARCH_TERMS_SCHEMA = {
    "type": "object",
    "properties": {
        "rec_search_terms": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": ["rec_search_terms"]
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


# --- MODIFICATION START: Schemas for the new Dual-LLM Enrichment feature ---
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
# --- MODIFICATION END ---