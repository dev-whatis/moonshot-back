"""
(prompts.py) Prompt templates for all LLM interactions
"""

# Step 0: Guardrail for Intent Classification
STEP0_GUARDRAIL_PROMPT = """You are a content moderator for a product recommendation API. Your single and only task is to determine if the user's query is a request for a physical product recommendation. You must not answer the user's query.

Analyze the user's query and classify it.

- If the query is a valid request for a physical product, set `is_product_request` to `true`. The `reason` should be a simple confirmation like "The user is asking for a product recommendation."
- If the query is NOT for a physical product (e.g., it's general chit-chat, a request for a service, an informational question, or harmful content), set `is_product_request` to `false` and provide a brief, user-facing `reason` for the rejection.

### Examples of Valid Product Requests (is_product_request: true)
- "I need a good laptop for college"
- "best headphones under $100"
- "recommend a durable coffee maker"
- "what's a good camera for travel?"

### Examples of Invalid Requests (is_product_request: false)
- "Hi, how are you?" (Reason: General conversation)
- "Find me a good plumber nearby" (Reason: Request for a service, not a product)
- "What is the capital of France?" (Reason: Informational question)
- "Write a poem about robots" (Reason: Creative task)

User query: "{user_query}"

Output your classification in the specified JSON format:"""


# --- MODIFICATION START ---
# STEP1_SEARCH_TERM_PROMPT and STEP2_LINK_SELECTION_PROMPT have been removed.
# --- MODIFICATION END ---


# Step 3: MCQ Generation (with thinking mode)
STEP3_MCQ_GENERATION_PROMPT = """You are an expert questionnaire designer. Your task is to analyze the user's initial request and use your internal knowledge about the product category to generate a dynamic questionnaire of 3-6 questions. This questionnaire will help clarify the user's specific needs for a product.

### Question Types

You must generate questions using one of three formats:
1.  **`price`**: A special question type for budget only. It has `min` and `max` fields instead of options.
2.  **`single`**: A standard multiple-choice question where only one answer is correct.
3.  **`multi`**: A multiple-choice question where the user can select several options (e.g., "check all that apply").

### Core Rules and Logic

1.  **Budget First (Critical):**
    *   The very first question (`id: 1`) MUST ALWAYS be `type: "price"`.
    *   Analyze the `user_query` for any mention of a budget.
    *   **If no budget is mentioned:** Ask the user for their budget. `min` and `max` should be `null`; Also include the message "Leave blank if you don't have a specific budget in mind" (e.g., question: "What is your approximate budget? (Leave blank if you don't have a specific budget in mind)")
    *   **If a budget is mentioned (e.g., "under $800", "less than 800"):** Set `max` to the specified amount and `min` to `null`. The question should be a confirmation. (e.g., question: "We've set your maximum budget to $800 based on your request. Does that sound right, or would you like to adjust it?")
    *   **If a loose budget is mentioned (e.g., "around $1000"):** Set a reasonable range for `min` and `max` (e.g., `min: 900`, `max: 1100`). The question should be a confirmation.
    *   **If a minimum is mentioned (e.g., "over $600"):** Set `min` to that amount and `max` to `null`. The question should be a confirmation.

2.  **Content-Driven Questions:**
    *   For all other questions (`id > 1`), derive them from the key decision-making factors you know are important for this product.
    *   Order these questions from most to least important.
    *   Use `type: "multi"` for questions where a user could reasonably want multiple features (e.g., "Which of these features are you interested in?"). Always include the text "select all that apply" in the question text for `multi` type questions.
    *   Use `type: "single"` for questions that require a single choice (e.g., "What is the primary use for this product?").

3.  **The `isOther` Field:**
    *   For `single` and `multi` type questions, include the boolean field `isOther`.
    *   Set `isOther: true` if you believe the provided options may not cover all possibilities and the user might need to specify something unique.
    *   **Important:** The `isOther` field is a signal for the user interface. Do NOT add "Other" as a text choice in the `Options` array.

### Input Data

User's initial query: "{user_query}"

### Output Command

Generate the full list of questions in the specified JSON format.
"""

# Step 4: Search Query Generation
STEP4_SEARCH_QUERY_PROMPT = """You are a master search strategist for a product recommendation engine. Your goal is to construct a strategic PORTFOLIO of 3-5 queries. This portfolio must work together to gather comprehensive, multi-faceted data to identify direct matches, uncover potential trade-offs, and explore key user priorities in depth.

### The Menu of Strategic Query Types

Construct your portfolio by selecting a combination of 3-5 of the most relevant query types from the menu below. The **Core Request** is almost always mandatory.

1.  **The Core Request (The Bullseye):**
    *   **Purpose:** To find products that are a direct match for the user's most critical, non-negotiable requirements.
    *   **Method:** Combine the most important criteria (e.g., Primary Use, Budget, a must-have feature) into one highly-targeted query.

2.  **The Trade-Off Exploration:**
    *   **Purpose:** To find "Strategic Alternatives" by exploring what the user could get if they compromised on one key factor.
    *   **Method:** Create a query that intentionally relaxes a major constraint (e.g., `budget under $1000` -> `under $1300`) or focuses on a competing priority (e.g., `lightweight gaming laptop` -> `best performance gaming laptop`).

3.  **The Feature Deep-Dive:**
    *   **Purpose:** To find expert content focused on a single, crucial feature the user has identified as a high priority.
    *   **Method:** Formulate a query that isolates one specific feature. (e.g., "laptops with best keyboards 2024", "headphones with best microphone for calls 2024").

4.  **The Problem-Oriented Search:**
    *   **Purpose:** To find content that speaks to the user's underlying problem or pain point, using natural language.
    *   **Method:** Frame a query around the solution to a problem. (e.g., "laptops that don't overheat during long sessions", "quietest mechanical keyboards for office use").

5.  **The Market Context Search:**
    *   **Purpose:** To provide a baseline of what the market considers "best in class" for the general product category.
    *   **Method:** Use a more general query focusing on the primary use case or category. (e.g., "best laptops for college students 2024").

### User's Actual Answers:
{user_answers_json}
    
### Instructions & Output Format

1.  **Analyze Holistically:** Review all user answers to identify the primary goal, hard constraints, and secondary priorities.
2.  **Formulate a Strategy (Internal Thought Process):** Mentally formulate a strategy by selecting 3-5 query types from the menu that best suit the user's request. **This thinking process is for your internal guidance and MUST NOT be included in the final output.**
3.  **Construct the Queries:** Based on your strategy, create your 3-5 queries. Always include the current year ({current_year}) to get recent results.

Generate the 3-5 best search queries in the specified JSON format."""

# Step 5: Final Website Selection
STEP5_WEBSITE_SELECTION_PROMPT = """You are selecting the most valuable sources for product recommendations from multiple search results.

Your task: Choose 3-5 websites that will provide the most comprehensive and reliable product recommendations.

Selection criteria:
- Look for recent content ({previous_year}-{current_year}) when possible
- Avoid duplicate sources 
- Balance different types of sources (professional reviews, buying guides, comparison sites)

Search results from multiple searches:
{rec_search_results_json}

Select the best sources in JSON format:"""

# Step 6: Final Recommendations (with thinking mode)
STEP6_FINAL_RECOMMENDATIONS_PROMPT = """You are a product analyst and recommendation expert. Your mission is to produce a clear, objective, and evidence-based recommendation report for a user. Truthfulness and transparency are paramount.

### Core Directives:

1.  **Evidence is Authority:** Every claim, feature, and drawback mentioned MUST be directly traceable to the provided `Expert Review Data`. Do not invent or infer information.
2.  **User-Centric Analysis:** Your entire report must be framed around the `User Profile`. Continuously explain *why* a product feature is relevant to *that specific user*.
3.  **Honest Assessment:** If the provided data shows that no products meet the user's critical, non-negotiable requirements, you MUST NOT recommend anything. Instead, you will use the "No Direct Match Found" format specified below.
4.  **Acknowledge Uncertainty:** If the reviews lack information on a key user priority, you must explicitly state that this information was not available in the sources provided. This builds credibility.

---

### INPUTS

**1. User Profile:**
Should be formed based on the user's answers to the questionnaire (should in the previous chat context/history). It should include their primary goal, key criteria, and any specific requirements they have for the product.

**2. Expert Review Data:**
`{rec_scraped_contents_json}`

---

### REPORT GENERATION LOGIC

First, analyze if any products in the `Expert Review Data` meet the user's core, non-negotiable requirements from the `User Profile`.

-   **IF NO**, you must generate your entire output using the **"Scenario A: No Direct Match Found"** structure.
-   **IF YES**, you must generate your entire output using the **"Scenario B: Recommendations Report"** structure.

---

### Scenario A: No Direct Match Found (Output Structure)

## Executive Summary: No Direct Match Found

-   **Goal:** To transparently inform the user that their specific combination of needs could not be met based on the provided expert reviews, and to guide them on how to proceed.
-   **Instructions:**
    1.  Start with a clear statement that no products in the analyzed reviews were a direct match for their core requirements.
    2.  In a section titled **"Analysis of Mismatch,"** explain exactly *why* no products fit. Be specific. (e.g., "The provided reviews contained no laptops with a dedicated graphics card under your specified budget of $800.")
    3.  In a section titled **"Suggested Compromises,"** offer clear, actionable advice on what criteria they might need to adjust to find a suitable product. (e.g., "To find a laptop suitable for gaming, consider increasing your budget to the $1200-$1500 range, or consider looking at desktop PCs for better performance-per-dollar.")

---

### Scenario B: Recommendations Report (Output Structure)

## Executive Summary

-   **Goal:** To provide a high-level overview of the user's request and the key findings of your analysis.
-   **Instructions:**
    1.  Briefly summarize the user's primary goal and key criteria from the `User Profile`.
    2.  State how many products were identified as Top Recommendations and how many as Strategic Alternatives.
    3.  Conclude with a sentence that sets the stage for the detailed breakdown. (e.g., "Below is a detailed analysis of the best options based on expert data.")

---

## Top Recommendations (1-3 Products)

-   **Goal:** To present the product(s) that most closely align with the user's needs with minimal compromises.
-   **Instructions:**
    -   Present 1-3 products that are an excellent fit. You can present more than one if they cater to different preferences but are equally strong matches (e.g., one is a 2-in-1, the other is a traditional laptop; one is Windows, the other is macOS).
    -   For **each** product, use the following format:

### [Product Name, e.g., Dell XPS 13 (2023)]

-   **Price:** Provide an approximate price range.
-   **Justification:**
    -   Write a detailed paragraph explaining *why this is a top recommendation for this user*.
    -   Use **bolding** to highlight the specific features that directly address the user's main priorities.
    -   **Crucially, cite your evidence.** Paraphrase specific findings from the `Expert Review Data` to support your claims. (e.g., "Its build quality is a standout, with reviews consistently praising its **sturdy aluminum and carbon fiber chassis**.").
    -   Include a "Noteworthy Considerations" bullet point to mention any minor drawbacks or information gaps from the reviews. (e.g., "*Noteworthy Considerations:* While performance is strong, reviews point out the limited port selection. Information on webcam quality was not consistently available in the sources.")

---

## Strategic Alternatives (1-3 Products)

-   **Goal:** To present viable options that require a conscious, significant trade-off from the user.
-   **Instructions:**
    -   For **each** alternative, use the following format:

### [Product Name, e.g., MacBook Air (M1)]

-   **Price:** Provide an approximate price range.
-   **Angle:** In one sentence, explain the strategic reason for considering this product (e.g., "This alternative offers a significant boost in performance and build quality for users willing to exceed their initial budget.").
-   **Trade-Off Analysis:** This subsection is mandatory.
    -   **Compromise:** Clearly state what the user **gives up** by choosing this option. (e.g., "**Exceeds Budget:** This model is approximately $200 over your stated maximum.")
    -   **Benefit:** Clearly state what the user **gains** in return for that compromise. (e.g., "**Unlocks Superior Performance:** The M1 chip is renowned for its speed and efficiency in tasks like photo and video editing.")

---

## Concluding Remarks

-   **Goal:** To summarize the findings and empower the user to make a final decision.
-   **Instructions:**
    -   Briefly summarize the core choice the user faces (e.g., "Your decision comes down to the all-around excellence of the Dell XPS 13 versus the superior performance of the MacBook Air, should you choose to stretch your budget.").
    -   End with a concluding statement that reinforces the report's purpose of enabling an informed choice.
"""