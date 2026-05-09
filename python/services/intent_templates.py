from __future__ import annotations

from typing import TypedDict

from models.schemas import IntentType


class IntentTemplateDef(TypedDict):
    intent: IntentType
    name: str
    description: str
    keywords: list[str]
    examples: list[str]
    target_agents: list[str]


INTENT_TEMPLATES: list[IntentTemplateDef] = [
    {
        "intent": IntentType.SEARCH,
        "name": "Product Search",
        "description": "Search for specific products by name, category, brand, or attributes. The user knows what they want and is narrowing down by criteria.",
        "keywords": [
            "find", "search", "looking for", "show me", "i need", "do you have",
            "where can i find", "i want", "list", "browse", "filter",
        ],
        "examples": [
            "find me a red dress under 50 dollars",
            "show me laptops with 16gb ram",
            "i'm looking for nike running shoes size 10",
            "do you have bluetooth headphones in stock",
            "search for winter jackets for men",
            "show me all smartphones under 500",
            "i need a coffee maker with timer",
            "display leather bags in brown color",
        ],
        "target_agents": ["product_rec", "inventory"],
    },
    {
        "intent": IntentType.RECOMMEND,
        "name": "Personalized Recommendation",
        "description": "Get personalized or general product suggestions. The user wants the system to suggest something based on preferences or trends.",
        "keywords": [
            "recommend", "suggestion", "suggest", "best", "popular", "what should",
            "for me", "gift for", "top rated", "trending", "pick for me",
            "surprise me",
        ],
        "examples": [
            "recommend something for summer vacation",
            "what's the best smartphone right now",
            "suggest a gift for my girlfriend's birthday",
            "what should i buy for my new apartment",
            "show me popular items this week",
            "pick something for me under 100",
            "recommend workout gear for beginners",
        ],
        "target_agents": ["user_profile", "product_rec", "marketing_copy"],
    },
    {
        "intent": IntentType.COMPARE,
        "name": "Product Comparison",
        "description": "Compare two or more products on features, price, or quality. The user is evaluating options before making a decision.",
        "keywords": [
            "compare", "vs", "versus", "difference", "differences", "better",
            "which one", "or", "alternative to", "similar to", "instead of",
        ],
        "examples": [
            "compare iphone 15 and samsung galaxy s24",
            "which is better macbook or dell xps",
            "what's the difference between airpods pro and airpods max",
            "compare these two coffee makers side by side",
            "dyson vs shark vacuum which one should i get",
            "alternatives to nike air force 1",
            "is this better than the previous model",
        ],
        "target_agents": ["product_rec", "marketing_copy"],
    },
    {
        "intent": IntentType.PURCHASE,
        "name": "Purchase Intent",
        "description": "The user wants to buy a product, make a transaction, or proceed to checkout.",
        "keywords": [
            "buy", "buy now", "purchase", "order", "checkout", "add to cart",
            "i want to buy", "i'll take it", "proceed to payment", "place order",
            "pay for", "complete purchase",
        ],
        "examples": [
            "i want to buy this laptop",
            "add it to my cart",
            "place an order for 2 of these",
            "i'll take the blue one",
            "proceed to checkout",
            "buy now with express delivery",
        ],
        "target_agents": ["inventory", "user_profile"],
    },
    {
        "intent": IntentType.PRICE_CHECK,
        "name": "Price & Deal Inquiry",
        "description": "Check pricing, ask about discounts, deals, coupons, or sales promotions.",
        "keywords": [
            "price", "cost", "how much", "discount", "deal", "coupon", "cheap",
            "sale", "promotion", "offer", "budget", "affordable", "clearance",
            "bargain", "save", "cheapest",
        ],
        "examples": [
            "how much does this cost",
            "are there any discounts available",
            "do you have a coupon code",
            "is this on sale",
            "what's the cheapest laptop you have",
            "show me deals under 20",
            "any promotions running right now",
            "is there a student discount",
        ],
        "target_agents": ["product_rec", "marketing_copy"],
    },
    {
        "intent": IntentType.ORDER_STATUS,
        "name": "Order Tracking",
        "description": "Track an order, check delivery status, estimate shipping time, or inquire about logistics.",
        "keywords": [
            "order status", "tracking", "shipment", "delivery", "when will",
            "my order", "where is", "shipping", "arrived", "delayed",
            "estimated delivery", "package", "logistics", "on its way",
            "out for delivery",
        ],
        "examples": [
            "where is my order",
            "track my shipment number 12345",
            "when will my package arrive",
            "has my order shipped yet",
            "what's the delivery status of my purchase",
            "my package is delayed what happened",
            "estimated delivery date for order 67890",
        ],
        "target_agents": [],
    },
    {
        "intent": IntentType.SUPPORT,
        "name": "Customer Support",
        "description": "Get help with issues, complaints, returns, refunds, or general customer service questions.",
        "keywords": [
            "help", "problem", "issue", "complain", "refund", "return",
            "broken", "damaged", "not working", "wrong", "cancel", "exchange",
            "warranty", "faulty", "defective", "missing", "didn't receive",
            "customer service", "support",
        ],
        "examples": [
            "i have a problem with my order",
            "this item arrived broken what do i do",
            "how do i return an item",
            "i want a refund for my purchase",
            "the product i received is defective",
            "cancel my order please",
            "i received the wrong item",
            "my package was missing items",
        ],
        "target_agents": [],
    },
    {
        "intent": IntentType.BROWSE,
        "name": "General Browsing & Discovery",
        "description": "Casual browsing, exploring new arrivals, checking trends, or undirected discovery.",
        "keywords": [
            "browse", "explore", "new", "trending", "discover", "what's new",
            "show me what", "latest", "collection", "featured", "inspire",
            "just looking", "what do you have", "hello", "hi", "hey",
        ],
        "examples": [
            "what's new today",
            "show me what's trending",
            "just browsing",
            "show me your latest collection",
            "what do you have in home decor",
            "hello what can you show me",
            "give me some inspiration for spring fashion",
            "surprise me with something cool",
        ],
        "target_agents": ["product_rec", "marketing_copy"],
    },
]


def get_template_by_intent(intent: IntentType) -> IntentTemplateDef | None:
    for template in INTENT_TEMPLATES:
        if template["intent"] == intent:
            return template
    return None


def get_all_intents() -> list[IntentType]:
    return [t["intent"] for t in INTENT_TEMPLATES]
