# api/utils/router.py
import json
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import requests
import os
from enum import Enum

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
        """Route query to appropriate tool or general chat"""
        
        # First try rule-based routing (fast and free)
        rule_decision = self._rule_based_routing(query)
        if rule_decision.confidence > 0.9:
            return rule_decision
        
        # If uncertain, use LLM routing
        try:
            llm_decision = self._llm_routing(query, context)
            # Combine rule-based and LLM insights
            if rule_decision.confidence > 0.7:
                # Trust rules for high-confidence matches
                return rule_decision
            return llm_decision
        except Exception as e:
            print(f"LLM routing failed: {e}")
            # Fallback to rule-based
            return rule_decision
    
    def _rule_based_routing(self, query: str) -> RoutingDecision:
        """Fast rule-based routing using keywords and patterns"""
        query_lower = query.lower().strip()
        
        # Sticky notes patterns
        note_patterns = [
            r'\b(add|save|write|create|store)\s+(note|reminder)',
            r'\b(read|show|get|list|find)\s+(notes?|reminders?)',
            r'\bnote\s+(that|this|about)',
            r'\b(remember|remind me)',
            r'\bsticky\s+notes?',
            r'\bsearch\s+(notes?|my notes)',
            r'\b(delete|remove|clear)\s+(note|notes)',
        ]
        
        for pattern in note_patterns:
            if re.search(pattern, query_lower):
                return RoutingDecision(
                    query_type=QueryType.STICKY_NOTES,
                    tool_name="sticky_notes",
                    confidence=0.95,
                    reasoning=f"Matched note pattern: {pattern}"
                )
        
        # Doc search patterns
        doc_patterns = [
            r'\b(search|find|look up|lookup)\s+(docs?|documentation|manual)',
            r'\bhow\s+to\s+.+(in|with|using)\s+\w+',
            r'\b(api|documentation|reference|guide)\s+(for|about)',
            r'\bofficial\s+(docs?|documentation)',
        ]
        
        for pattern in doc_patterns:
            if re.search(pattern, query_lower):
                return RoutingDecision(
                    query_type=QueryType.DOC_SEARCH,
                    tool_name="docs_search",
                    confidence=0.85,
                    reasoning=f"Matched doc search pattern: {pattern}"
                )
        
        # Math patterns
        math_patterns = [
            r'\b(derivative|differentiate|d/dx)\b',
            r'\b(integral|integrate|∫)\b',
            r'\b(calculate|compute|solve)\s+.*(derivative|integral)',
            r'\bfind\s+the\s+(derivative|integral)',
            r'∫|∂|d/dx|dx|dy',
        ]
        
        for pattern in math_patterns:
            if re.search(pattern, query_lower):
                return RoutingDecision(
                    query_type=QueryType.MATH,
                    tool_name="math",
                    confidence=0.9,
                    reasoning=f"Matched math pattern: {pattern}"
                )
        
        # General chat (default)
        return RoutingDecision(
            query_type=QueryType.GENERAL_CHAT,
            confidence=0.6,
            reasoning="No specific tool patterns matched, defaulting to general chat"
        )
    
    def _llm_routing(self, query: str, context: str = "") -> RoutingDecision:
        """Use LLM to make routing decision"""
        
        # Try Ollama first (local, free)
        try:
            return self._route_with_ollama(query, context)
        except Exception as e:
            print(f"Ollama routing failed: {e}")
        
        # Fallback to OpenRouter (may have free tier)
        if self.openrouter_key:
            try:
                return self._route_with_openrouter(query, context)
            except Exception as e:
                print(f"OpenRouter routing failed: {e}")
        
        # Ultimate fallback
        return RoutingDecision(
            query_type=QueryType.GENERAL_CHAT,
            confidence=0.5,
            reasoning="LLM routing unavailable, defaulting to chat"
        )
    
    def _route_with_ollama(self, query: str, context: str = "") -> RoutingDecision:
        """Route using local Ollama"""
        
        prompt = self._build_routing_prompt(query, context)
        
        response = requests.post(
            f"{self.ollama_base_url}/api/generate",
            json={
                "model": "llama3.2:3b",  # Small, fast model
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
        """Route using OpenRouter (free tier)"""
        
        prompt = self._build_routing_prompt(query, context)
        
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.openrouter_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "meta-llama/llama-3.2-3b-instruct:free",  # Free model
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
        """Build routing prompt for LLM"""
        
        available_tools = """
Available tools:
1. sticky_notes - Add, read, search, or manage personal notes
2. docs_search - Search documentation and web resources  
3. math - Calculate derivatives, integrals, and math operations
4. general_chat - Normal conversation and questions

Context from recent conversation:
{context}

User Query: {query}

Analyze the query and respond with JSON only:
{{
    "tool": "sticky_notes|docs_search|math|general_chat",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}}

Examples:
- "add a note about the meeting" → {{"tool": "sticky_notes", "confidence": 0.95, "reasoning": "clear note creation request"}}
- "find React documentation" → {{"tool": "docs_search", "confidence": 0.9, "reasoning": "documentation search request"}}  
- "what's the derivative of x^2" → {{"tool": "math", "confidence": 0.95, "reasoning": "mathematical calculation request"}}
- "how are you today?" → {{"tool": "general_chat", "confidence": 0.9, "reasoning": "casual conversation"}}
""".format(context=context[:500], query=query)
        
        return available_tools
    
    def _parse_routing_response(self, response: str) -> RoutingDecision:
        """Parse LLM routing response"""
        
        try:
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response)
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
                tool_name=tool_name if tool_name != "general_chat" else None,
                confidence=float(data.get("confidence", 0.7)),
                reasoning=data.get("reasoning", "LLM routing decision")
            )
            
        except Exception as e:
            print(f"Failed to parse routing response: {e}")
            return RoutingDecision(
                query_type=QueryType.GENERAL_CHAT,
                confidence=0.5,
                reasoning="Failed to parse LLM response"
            )

class SimpleRouter:
    """Simplified router for development/testing"""
    
    def route_query(self, query: str, context: str = "") -> RoutingDecision:
        """Simple keyword-based routing"""
        query_lower = query.lower()
        
        # Direct keyword matches
        if any(word in query_lower for word in ['note', 'reminder', 'remember', 'write down']):
            return RoutingDecision(QueryType.STICKY_NOTES, "sticky_notes", 0.8)
        
        if any(word in query_lower for word in ['search', 'docs', 'documentation', 'api']):
            return RoutingDecision(QueryType.DOC_SEARCH, "docs_search", 0.8)
        
        if any(word in query_lower for word in ['derivative', 'integral', 'calculate', 'math']):
            return RoutingDecision(QueryType.MATH, "math", 0.8)
        
        return RoutingDecision(QueryType.GENERAL_CHAT, None, 0.7)

# Initialize router based on environment
def get_router():
    """Get appropriate router based on available services"""
    if os.getenv("USE_SIMPLE_ROUTER", "false").lower() == "true":
        return SimpleRouter()
    return LocalLLMRouter()

router = get_router()