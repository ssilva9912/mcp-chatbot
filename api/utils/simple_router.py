import json
import re
import os
import requests
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class QueryType(Enum):
    GENERAL_CHAT = "general_chat"
    STICKY_NOTES = "sticky_notes"
    DOC_SEARCH = "doc_search"
    MATH = "math"
    TOOL_CALL = "tool_call"


@dataclass
class RoutingDecision:
    query_type: QueryType
    tool_name: Optional[str] = None
    confidence: float = 0.8
    reasoning: str = ""
    parameters: Optional[Dict] = None


class LocalLLMRouter:
    """Router using local or free LLM services"""

    def __init__(self):
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY")
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    def route_query(self, query: str, context: str = "") -> RoutingDecision:
        # First check if this is clearly conversational
        if self._is_conversational(query):
            return RoutingDecision(
                query_type=QueryType.GENERAL_CHAT,
                tool_name="general_chat",
                confidence=0.95,
                reasoning="Detected conversational intent"
            )

        # Then try rule-based routing for clear tool requests
        rule_decision = self._rule_based_routing(query)
        if rule_decision.confidence >= 0.85:  # Raised threshold
            return rule_decision

        # For ambiguous cases, use LLM
        try:
            llm_decision = self._llm_routing(query, context)
            return llm_decision
        except Exception as e:
            print(f"LLM routing failed: {e}")
            # Default to conversation for ambiguous cases
            return RoutingDecision(
                query_type=QueryType.GENERAL_CHAT,
                tool_name="general_chat",
                confidence=0.8,
                reasoning="Ambiguous query, defaulting to conversation"
            )

    def _is_conversational(self, query: str) -> bool:
        """Detect clearly conversational queries that shouldn't use tools"""
        query_lower = query.lower().strip()
        
        # Greetings and social interactions
        conversational_patterns = [
            r'^(hi|hello|hey|good\s+(morning|afternoon|evening))',
            r'^(how\s+are\s+you|what\'s\s+up|sup)',
            r'^(thanks?|thank\s+you|thx)',
            r'^(bye|goodbye|see\s+you|later)',
            r'^(yes|no|okay|ok|sure|maybe|perhaps)$',
            r'tell\s+me\s+(about|a\s+joke|something\s+interesting)',
            r'what\s+(do\s+you\s+think|is\s+your\s+opinion)',
            r'(i\s+think|i\s+believe|in\s+my\s+opinion)',
            r'(that\'s|this\s+is)\s+(interesting|cool|nice|great)',
        ]
        
        for pattern in conversational_patterns:
            if re.search(pattern, query_lower):
                return True
                
        # Short responses (likely conversational)
        if len(query.split()) <= 3 and not any(word in query_lower for word in 
                                               ['note', 'search', 'calculate', 'derivative']):
            return True
            
        return False

    def _rule_based_routing(self, query: str) -> RoutingDecision:
        query_lower = query.lower().strip()

        # More specific note patterns with action words
        note_patterns = [
            r'\b(create|add|save|write|make)\s+(a\s+)?(new\s+)?(note|reminder)',
            r'\b(show|list|display|get|find)\s+(my\s+)?(notes?|reminders?)',
            r'\bnote\s+down\s+',
            r'\bremind\s+me\s+(to|that|about)',
            r'\bsticky\s+notes?\b',
            r'\bsearch\s+(my\s+)?notes?\b',
            r'\b(delete|remove|clear)\s+(this\s+|that\s+|my\s+)?(note|reminder)',
            r'\bi\s+need\s+to\s+(remember|note|write\s+down)',
        ]
        for pattern in note_patterns:
            if re.search(pattern, query_lower):
                return RoutingDecision(
                    query_type=QueryType.STICKY_NOTES,
                    tool_name="sticky_notes",
                    confidence=0.9,
                    reasoning=f"Matched specific note action: {pattern}"
                )

        # More specific doc search patterns
        doc_patterns = [
            r'\b(search|find|lookup|look\s+up)\s+(the\s+)?(docs?|documentation|manual|api)',
            r'\bhow\s+(do\s+i|to)\s+.+(in|with|using)\s+\w+',
            r'\b(show\s+me\s+|find\s+)?documentation\s+(for|about|on)',
            r'\bapi\s+(reference|docs?|documentation)',
            r'\bofficial\s+(guide|docs?|documentation)',
            r'\bcheck\s+the\s+(docs?|manual|reference)',
        ]
        for pattern in doc_patterns:
            if re.search(pattern, query_lower):
                return RoutingDecision(
                    query_type=QueryType.DOC_SEARCH,
                    tool_name="docs_search",
                    confidence=0.9,
                    reasoning=f"Matched specific doc search: {pattern}"
                )

        # More specific math patterns
        math_patterns = [
            r'\b(calculate|compute|find|solve)\s+the\s+(derivative|integral)',
            r'\b(derivative|differentiate)\s+(of|with\s+respect\s+to)',
            r'\b(integrate|integral)\s+',
            r'\bderivative\s+of\b',
            r'\bd/dx\s+',
            r'∫|∂|d/dx',
            r'\bsolve\s+.*(equation|math|calculus)',
            r'\bwhat\s+is\s+the\s+(derivative|integral)\s+of',
        ]
        for pattern in math_patterns:
            if re.search(pattern, query_lower):
                return RoutingDecision(
                    query_type=QueryType.MATH,
                    tool_name="math",
                    confidence=0.9,
                    reasoning=f"Matched specific math operation: {pattern}"
                )

        # If no specific patterns matched, return general chat with high confidence
        return RoutingDecision(
            query_type=QueryType.GENERAL_CHAT,
            tool_name="general_chat",
            confidence=0.85,  # Higher confidence for conversation
            reasoning="No specific tool patterns matched, treating as conversation"
        )

    def _llm_routing(self, query: str, context: str = "") -> RoutingDecision:
        try:
            return self._route_with_ollama(query, context)
        except Exception as e:
            print(f"Ollama routing failed: {e}")

        if self.openrouter_key:
            try:
                return self._route_with_openrouter(query, context)
            except Exception as e:
                print(f"OpenRouter routing failed: {e}")

        return RoutingDecision(
            query_type=QueryType.GENERAL_CHAT,
            tool_name="general_chat",
            confidence=0.8,
            reasoning="LLM routing unavailable, defaulting to conversation"
        )

    def _route_with_ollama(self, query: str, context: str = "") -> RoutingDecision:
        prompt = self._build_routing_prompt(query, context)
        response = requests.post(
            f"{self.ollama_base_url}/api/generate",
            json={
                "model": "llama3.2:3b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 100
                }
            },
            timeout=10
        )
        response.raise_for_status()
        result = response.json()
        return self._parse_routing_response(result.get("response", ""))

    def _route_with_openrouter(self, query: str, context: str = "") -> RoutingDecision:
        prompt = self._build_routing_prompt(query, context)
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "meta-llama/llama-3.2-3b-instruct:free",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 100
            },
            timeout=15
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return self._parse_routing_response(content)

    def _build_routing_prompt(self, query: str, context: str = "") -> str:
        return f"""
You are a query router. The user wants to have natural conversations by default, and only use tools when specifically requested.

Available tools:
1. sticky_notes - For explicitly managing personal notes (add/save/create/list/search notes)
2. docs_search - For searching documentation when explicitly requested
3. math - For explicit math calculations (derivatives, integrals)
4. general_chat - For all conversations, questions, discussions

Key principles:
- Default to general_chat for conversations, questions, explanations
- Only use tools when the user explicitly requests an action
- "I want to remember X" = sticky_notes, but "I remember X" = general_chat
- "How does X work?" = general_chat, but "Search docs for X" = docs_search

Context: {context[:500]}
User Query: {query}

Respond with JSON only:
{{
    "tool": "sticky_notes|docs_search|math|general_chat",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}
"""

    def _parse_routing_response(self, response: str) -> RoutingDecision:
        try:
            json_match = re.search(r'\{.*?\}', response, re.DOTALL)
            if not json_match:
                raise ValueError("No JSON found in response")

            data = json.loads(json_match.group())

            tool_mapping = {
                "sticky_notes": QueryType.STICKY_NOTES,
                "docs_search": QueryType.DOC_SEARCH,
                "math": QueryType.MATH,
                "general_chat": QueryType.GENERAL_CHAT
            }

            tool_name = data.get("tool", "general_chat")
            query_type = tool_mapping.get(tool_name, QueryType.GENERAL_CHAT)

            return RoutingDecision(
                query_type=query_type,
                tool_name=tool_name,
                confidence=float(data.get("confidence", 0.7)),
                reasoning=data.get("reasoning", "LLM routing decision")
            )
        except Exception as e:
            print(f"Failed to parse routing response: {e}")
            return RoutingDecision(
                query_type=QueryType.GENERAL_CHAT,
                tool_name="general_chat",
                confidence=0.8,
                reasoning="Failed to parse LLM response, defaulting to conversation"
            )


class SimpleRouter:
    def route_query(self, query: str, context: str = "") -> RoutingDecision:
        query_lower = query.lower()
        
        # Check for explicit tool requests only
        if any(phrase in query_lower for phrase in ['save note', 'add note', 'create note', 'list notes', 'search notes']):
            return RoutingDecision(QueryType.STICKY_NOTES, "sticky_notes", 0.9)
        if any(phrase in query_lower for phrase in ['search docs', 'find documentation', 'lookup api']):
            return RoutingDecision(QueryType.DOC_SEARCH, "docs_search", 0.9)
        if any(phrase in query_lower for phrase in ['calculate derivative', 'find integral', 'solve equation']):
            return RoutingDecision(QueryType.MATH, "math", 0.9)
        
        # Default to conversation with high confidence
        return RoutingDecision(QueryType.GENERAL_CHAT, tool_name="general_chat", confidence=0.9)


def get_router():
    if os.getenv("USE_SIMPLE_ROUTER", "false").lower() == "true":
        return SimpleRouter()
    return LocalLLMRouter()


router = get_router()