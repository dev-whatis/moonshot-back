"""
(schemas.py) Defines Pydantic models for API requests/responses and
internal OpenAPI schemas for structured outputs from Gemini.
"""

from pydantic import BaseModel, Field, ConfigDict
from pydantic.alias_generators import to_camel
from typing import List, Optional, Literal, Union
from datetime import datetime


# ********************************************************************************
# --- Request Models ---
# ********************************************************************************



# ==============================================================================
# --- Request Model for Starting a Conversation ---
# ==============================================================================

class StartRequest(BaseModel):
    """Data model for the /start endpoint request body."""
    user_query: str = Field(..., example="I need a good laptop for college")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ==============================================================================
# --- Request Models for Product Discovery Path ---
# ==============================================================================

class PriceAnswer(BaseModel):
    """
    Data model for the user's answer to the budget question.
    It includes the original question text for full context.
    """
    question_type: Literal["price"] = Field(..., alias="questionType")
    question: str = Field(..., description="The exact question text that was asked.")
    min: Optional[float] = Field(None, description="The minimum budget selected by the user.")
    max: Optional[float] = Field(None, description="The maximum budget selected by the user.")
    
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class AnswerOption(BaseModel):
    """Data model for a single selected option within a user's answer."""
    text: str = Field(..., description="The concise label for the option.")
    description: str = Field(..., description="A short explanation of this choice.")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

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
    
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TurnRequest(BaseModel):
    """
    Data model for the POST /api/conversations/turn endpoint.
    Handles both the creation of a new conversation and adding turns to an existing one.
    """
    conversation_id: Optional[str] = Field(
        None, alias="conversationId", description="The ID of the conversation. If null, a new conversation is created."
    )
    user_query: str = Field(
        ..., alias="userQuery", description="The user's prompt for this specific turn."
    )
    user_answers: Optional[List[Union["PriceAnswer", "DiagnosticAnswer"]]] = Field(
        None, alias="userAnswers", description="The user's answers from the initial questionnaire. Only provided for the first turn."
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ==============================================================================
# Request Models for Enriching Product Recommendations
# ==============================================================================

class EnrichTurnRequest(BaseModel):
    """Data model for the /enrich endpoint request body."""
    conversation_id: str = Field(
        ..., alias="conversationId", description="The ID of the recommendation conversation."
    )
    turn_id: str = Field(
        ..., alias="turnId", description="The specific turn ID within the conversation to which this enrichment belongs."
    )
    product_names: List[str] = Field(
        ..., alias="productNames", description="A list of product names to be enriched with images and shopping links."
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ==============================================================================
# Request Models for Quick Decision Path
# ==============================================================================

class QuickAnswerOption(BaseModel):
    """Data model for a single selected option in a quick decision answer."""
    text: str = Field(..., description="The concise label for the option.")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class QuickDecisionAnswer(BaseModel):
    """
    Data model for the user's answer to a single quick decision question.
    """
    question_type: Literal["single", "multi"] = Field(..., alias="questionType")
    question: str = Field(..., description="The exact question text that was asked.")
    user_answers: List[QuickAnswerOption] = Field(
        ..., alias="userAnswers", description="A list of the option(s) the user selected."
    )
    
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class QuickDecisionTurnRequest(BaseModel):
    """
    Data model for the POST /api/quick-decisions/turn endpoint.
    Handles both creating and adding turns to a Quick Decision conversation.
    """
    conversation_id: Optional[str] = Field(
        None, alias="conversationId", description="The ID of the conversation. If null, a new conversation is created."
    )
    user_query: str = Field(
        ..., alias="userQuery", description="The user's prompt for this specific turn."
    )
    need_location: Optional[bool] = Field(
        None, alias="needLocation", description="Flag for location context. Only for the first turn."
    )
    user_answers: Optional[List[QuickDecisionAnswer]] = Field(
        None, alias="userAnswers", description="Optional answers from the questionnaire. Only for the first turn."
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# ==============================================================================
# Request Model for Sharing Conversations
# ==============================================================================

class ShareCreateRequest(BaseModel):
    """Data model for the POST /api/share endpoint request body."""
    conversation_id: str = Field(..., alias="conversationId", description="The ID of the conversation to be shared.")

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)



# ********************************************************************************
# --- Response Models ---
# ********************************************************************************



class TurnCreationResponse(BaseModel):
    """
    Data model for the immediate response from POST /api/conversations/turn.
    Acknowledges the request and provides IDs to poll for status.
    """
    conversation_id: str = Field(..., alias="conversationId")
    turn_id: str = Field(..., alias="turnId")
    status: str = Field(..., description="The initial status of the job (e.g., 'processing').")
    
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class TurnStatusResponse(BaseModel):
    """
    Data model for the GET /api/conversations/turn_status/{turnId} endpoint.
    Provides the current state and final content of a specific turn's background job.
    """
    status: str = Field(..., description="The current status of the job (e.g., 'processing', 'complete', 'failed').")
    
    # These fields will be populated once the status is 'complete' or 'failed'.
    model_response: Optional[str] = Field(
        None, alias="modelResponse", description="If complete, the full Markdown response from the LLM."
    )
    product_names: Optional[List[str]] = Field(
        None, alias="productNames", description="If complete, the list of recommended products."
    )
    error: Optional[str] = Field(
        None, description="If the status is 'failed', this will contain the error message."
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Turn(BaseModel):
    """Data model representing a single turn within a conversation."""
    turn_id: str = Field(..., alias="turnId")
    turn_index: int = Field(..., alias="turnIndex")
    status: str
    user_query: str = Field(..., alias="userQuery")
    model_response: Optional[str] = Field(None, alias="modelResponse")
    product_names: List[str] = Field(default=[], alias="productNames")
    enriched_products: List["EnrichedProduct"] = Field(default=[], alias="enrichedProducts")
    created_at: datetime = Field(..., alias="createdAt")
    error: Optional[str] = None
    
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class ConversationResponse(BaseModel):
    """
    Data model for the response from GET /api/history/{conversationId}
    and GET /api/share/{shareId}, containing the entire conversation.
    """
    conversation_id: str = Field(..., alias="conversationId")
    user_id: str = Field(..., alias="userId")
    title: str
    conversation_type: Literal["PRODUCT_DISCOVERY", "QUICK_DECISION", "UNKNOWN"] = Field(
        ..., alias="conversationType", description="The type of conversation, for routing follow-ups on the client."
    )
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    turns: List[Turn]

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class BudgetObject(BaseModel):
    """Data model for the extracted budget values."""
    min: Optional[float] = None
    max: Optional[float] = None

class BudgetQuestion(BaseModel):
    """Data model for the budget-specific question."""
    question_type: Literal["price"] = Field(..., alias="questionType")
    question: str
    price: BudgetObject

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

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

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class QuickQuestionOption(BaseModel):
    """Data model for a simple option in a quick question (text only)."""
    text: str = Field(..., description="The concise label for the option.")

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)


class QuickQuestion(BaseModel):
    """Data model for a single, simple question in the Quick Decision path."""
    question_type: Literal["single", "multi"] = Field(..., alias="questionType")
    question: str
    options: List[QuickQuestionOption]

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class ProductDiscoveryPayload(BaseModel):
    """
    Data model for the Product Discovery response body, containing the full
    questionnaire split into budget and diagnostic sections.
    """
    budget_question: BudgetQuestion = Field(..., alias="budgetQuestion")
    diagnostic_questions: List[DiagnosticQuestion] = Field(..., alias="diagnosticQuestions")

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class QuickDecisionPayload(BaseModel):
    """The data payload returned for the QUICK_DECISION route."""
    need_location: bool = Field(..., alias="needLocation")
    quick_questions: List[QuickQuestion] = Field(..., alias="quickQuestions", description="A list of simple, optional follow-up questions. Can be an empty list.")
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

class StartResponse(BaseModel):
    route: Literal["PRODUCT_DISCOVERY", "QUICK_DECISION"]
    payload: Union[ProductDiscoveryPayload, QuickDecisionPayload]
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

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
    
    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class EnrichResponse(BaseModel):
    """Data model for the /enrich endpoint response body."""
    enriched_products: List[EnrichedProduct] = Field(..., alias="enrichedProducts")

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class ShareCreateResponse(BaseModel):
    """Data model for the POST /api/share endpoint response body."""
    share_id: str = Field(..., alias="shareId", description="The unique, public ID for the shared recommendation.")
    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class ShareDataResponse(ConversationResponse):
    """
    Data model for the public GET /api/share/{shareId} endpoint.
    It contains all the data needed to render a shared conversation page.
    This model inherits all fields from ConversationResponse.
    """
    pass # Inherits everything from ConversationResponse

class HistoryUpdateRequest(BaseModel):
    """Data model for the PATCH /api/history/{conversationId} endpoint body."""
    title: str = Field(..., description="The new user-defined title for the conversation.")

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class HistorySummaryItem(BaseModel):
    """Data model for a single item in the user's history list."""
    conversation_id: str = Field(..., alias="conversationId")
    title: str = Field(..., description="The title of the conversation, either user-defined or the original query.")
    created_at: datetime = Field(..., alias="createdAt", description="The timestamp when the conversation was started.")
    status: str = Field(..., description="The final status of the conversation (e.g., 'complete', 'failed').")

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

class HistoryListResponse(BaseModel):
    """Data model for the GET /api/history endpoint response."""
    history: List[HistorySummaryItem]
    next_cursor: Optional[str] = Field(None, alias="nextCursor", description="The cursor to use for fetching the next page of results. Null if this is the last page.")

    model_config = ConfigDict( alias_generator=to_camel, populate_by_name=True)

# ==============================================================================
# Internal OpenAPI Schemas for Gemini Interactions
# ==============================================================================

# Step 0: Router for Intent Classification
ROUTER_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "route": {
            "type": "string",
            "description": "The determined route for the user's query.",
            "enum": ["PRODUCT_DISCOVERY", "QUICK_DECISION", "REJECT"]
        }
    },
    "required": ["route"]
}

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

# Step QD1: Quick Question Generation
QUICK_QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "needLocation": {
            "type": "boolean",
            "description": "A background flag. Set to true ONLY if the decision is sensitive to real-world context (like weather) AND the user has NOT already provided a location. Otherwise, it must be false."
        },
        "questions": {
            "type": "array",
            "description": "A list of 0-3 friendly, conversational questions to help understand the user's context. An empty array [] is the correct output for mechanical queries (e.g., 'roll a dice').",
            "items": {
                "type": "object",
                "properties": {
                    "questionType": {
                        "type": "string",
                        "description": "The type of question. 'multi' is preferred for a low-pressure, friendly feel.",
                        "enum": ["single", "multi"]
                    },
                    "question": {
                        "type": "string",
                        "description": "The main text of the question presented to the user, phrased in a friendly, natural tone."
                    },
                    "options": {
                        "type": "array",
                        "description": "A list of simple choices for the question. MUST include an 'escape hatch' option like 'You decide for me'.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "text": {
                                    "type": "string",
                                    "description": "The concise, user-friendly label for the option."
                                }
                            },
                            "required": ["text"]
                        }
                    }
                },
                "required": ["questionType", "question", "options"]
            }
        }
    },
    "required": ["needLocation", "questions"]
}

# Step FS1: Fast Search Query Generation
FAST_SEARCH_QUERIES_SCHEMA = {
  "type": "object",
  "properties": {
    "searchQueries": {
      "type": "array",
      "description": "A list of 3-4 concise search queries",
      "items": {
        "type": "string",
        "description": "A single, human-like search query string"
      }
    }
  },
  "required": ["searchQueries"]
}