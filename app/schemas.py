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


class PriceAnswer(BaseModel):
    """Data model for a price range answer."""
    min: Optional[float] = None
    max: Optional[float] = None

    # This config allows the model to accept camelCase JSON
    # and map it to snake_case attributes.
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class UserAnswer(BaseModel):
    """
    Data model for a single Question & Answer pair provided by the user.
    """
    question: str = Field(..., description="The exact question text that was asked.")
    type: Literal["single", "multi", "price"] = Field(..., description="The type of question that was asked.")
    is_other: Optional[bool] = Field(False, alias="isOther", description="True if the user provided a custom 'other' value.")
    
    answer: Union[str, List[str], PriceAnswer] = Field(..., description="The user's answer, formatted based on the question type.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

class FinalizeRequest(BaseModel):
    """Data model for the /finalize endpoint request body."""
    user_answers: List[UserAnswer] = Field(..., description="A list of the user's answers to the questionnaire.")

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# --- Response Models ---

class QuestionOption(BaseModel):
    """Data model for a single MCQ option. The client is responsible for assigning letters (A, B, C) or numbers."""
    text: str

class Question(BaseModel):
    """
    Data model for a single question sent to the user.
    """
    id: int
    question: str
    type: Literal["single", "multi", "price"]
    Options: Optional[List[QuestionOption]] = None
    is_other: Optional[bool] = Field(None, alias="isOther", description="For single/multi questions, true if a free-text 'Other' option is appropriate.")
    min: Optional[float] = None
    max: Optional[float] = None

class QuestionsResponse(BaseModel):
    """Data model for the /start endpoint response body."""
    questions: List[Question]

class RecommendationsResponse(BaseModel):
    """Data model for the /finalize endpoint response body."""
    recommendations: str

class StopResponse(BaseModel):
    """Data model for the /stop endpoint response body."""
    status: str = Field(..., example="stopped")
    message: str = Field(..., example="Your session has been terminated.")

# --- MODIFICATION START ---
class RejectionResponse(BaseModel):
    """
    Data model for the structured rejection response sent to the client
    when the user's query is out-of-scope.
    """
    message: str = "Query cannot be processed."
    reason: str

# --- MODIFICATION END ---

# ==============================================================================
# Internal OpenAPI Schemas for Gemini Interactions
# ==============================================================================

# --- MODIFICATION START ---
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
# --- MODIFICATION END ---

# Step 1: Initial Search Term Generation
GUIDE_SEARCH_TERM_SCHEMA = {
    "type": "object",
    "properties": {
        "guide_search_term": {
            "type": "string"
        }
    },
    "required": ["guide_search_term"]
}

# Step 2: Link Selection
GUIDE_SEARCH_URLS_SCHEMA = {
    "type": "object",
    "properties": {
        "guide_search_urls": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": ["guide_search_urls"]
}


# Step 3: MCQ Generation
MCQ_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "description": "An array of 3-6 questions to ask the user.",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "question": {"type": "string"},
                    "type": {
                        "type": "string",
                        "description": "The type of question.",
                        "enum": ["single", "multi", "price"]
                    },
                    "Options": {
                        "type": "array",
                        "description": "List of choices for 'single' or 'multi' questions. Omit for 'price'.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"}
                            },
                            "required": ["text"]
                        }
                    },
                    "isOther": {
                        "type": "boolean",
                        "description": "For 'single'/'multi', set to true if a free-text 'Other' option is appropriate. Omit for 'price'."
                    },
                    "min": {
                        "type": "number",
                        "nullable": True,
                        "description": "For 'price' questions, the pre-populated minimum. Omit for other types."
                    },
                    "max": {
                        "type": "number",
                        "nullable": True,
                        "description": "For 'price' questions, the pre-populated maximum. Omit for other types."
                    }
                },
                "required": ["id", "question", "type"]
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