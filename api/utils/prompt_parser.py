"""
Prompt Analysis and Parsing for Complex Prompts
File: utils/prompt_parser.py
"""

import re
from typing import List, Dict, Any
from dataclasses import dataclass
from enum import Enum

class PromptComplexity(Enum):
    SIMPLE = "simple"           # Single task/question
    COMPOUND = "compound"       # Multiple related tasks
    COMPLEX = "complex"         # Multiple unrelated tasks
    CONTEXTUAL = "contextual"   # Requires session context

@dataclass
class ParsedPrompt:
    original_text: str
    complexity: PromptComplexity
    tasks: List[Dict[str, Any]]
    requires_session_context: bool = False
    estimated_tokens: int = 0

class PromptParser:
    """Parse and analyze complex prompts"""
    
    def __init__(self):
        # Patterns for identifying different types of requests
        self.task_indicators = [
            r"(?:give me|show me|help me|create|make|build|implement)",
            r"(?:how to|way to|method to)",
            r"(?:tell me|explain|describe)",
            r"(?:find|search|look for)",
        ]
        
        self.separators = [
            r"(?:and then|then|also|additionally|furthermore)",
            r"(?:,\s*and|;\s*and|\.\s*and)",
            r"(?:by the way|oh and|one more thing)",
            r"(?:\.\s*my name is|\.\s*i'm|\.\s*btw)"
        ]
    
    def parse_prompt(self, text: str) -> ParsedPrompt:
        """Parse a prompt and identify its complexity and tasks"""
        # Clean and normalize text
        text = text.strip()
        
        # Identify tasks
        tasks = self._extract_tasks(text)
        
        # Determine complexity
        complexity = self._assess_complexity(text, tasks)
        
        # Check if session context is needed
        requires_context = self._needs_session_context(text)
        
        # Estimate token count (rough approximation)
        estimated_tokens = len(text.split()) * 1.3  # Rough approximation
        
        return ParsedPrompt(
            original_text=text,
            complexity=complexity,
            tasks=tasks,
            requires_session_context=requires_context,
            estimated_tokens=int(estimated_tokens)
        )
    
    def _extract_tasks(self, text: str) -> List[Dict[str, Any]]:
        """Extract individual tasks from the text"""
        tasks = []
        
        # Split by common separators
        segments = self._split_by_separators(text)
        
        for i, segment in enumerate(segments):
            task_type = self._identify_task_type(segment)
            tasks.append({
                "id": i + 1,
                "text": segment.strip(),
                "type": task_type,
                "priority": self._get_task_priority(segment, i),
                "estimated_complexity": self._estimate_task_complexity(segment)
            })
        
        return tasks
    
    def _split_by_separators(self, text: str) -> List[str]:
        """Split text by various separators"""
        # Start with the full text
        segments = [text]
        
        # Apply separator patterns
        for pattern in self.separators:
            new_segments = []
            for segment in segments:
                parts = re.split(pattern, segment, flags=re.IGNORECASE)
                new_segments.extend(parts)
            segments = new_segments
        
        # Filter out empty segments
        return [s.strip() for s in segments if s.strip()]
    
    def _identify_task_type(self, text: str) -> str:
        """Identify the type of task"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ["implement", "create", "build", "make"]):
            return "creation"
        elif any(word in text_lower for word in ["explain", "tell me", "how to"]):
            return "explanation"
        elif any(word in text_lower for word in ["find", "search", "look for"]):
            return "search"
        elif any(word in text_lower for word in ["recipe", "how to make", "cook"]):
            return "recipe"
        elif any(word in text_lower for word in ["close", "end", "stop", "exit"]):
            return "session_control"
        else:
            return "general"
    
    def _assess_complexity(self, text: str, tasks: List[Dict[str, Any]]) -> PromptComplexity:
        """Assess the overall complexity of the prompt"""
        if len(tasks) == 1:
            return PromptComplexity.SIMPLE
        elif len(tasks) == 2:
            # Check if tasks are related
            task_types = [task["type"] for task in tasks]
            if len(set(task_types)) == 1:  # Same type
                return PromptComplexity.COMPOUND
            else:
                return PromptComplexity.COMPLEX
        else:
            return PromptComplexity.COMPLEX
    
    def _needs_session_context(self, text: str) -> bool:
        """Check if the prompt needs session context"""
        context_indicators = [
            "continue", "also", "additionally", "furthermore",
            "my previous", "earlier", "before", "last time"
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in context_indicators)
    
    def _get_task_priority(self, task_text: str, index: int) -> int:
        """Determine task priority (1 = highest)"""
        # First task usually has highest priority
        base_priority = index + 1
        
        # Adjust based on urgency indicators
        urgent_words = ["urgent", "important", "first", "priority"]
        if any(word in task_text.lower() for word in urgent_words):
            base_priority = max(1, base_priority - 1)
        
        return base_priority
    
    def _estimate_task_complexity(self, task_text: str) -> str:
        """Estimate individual task complexity"""
        if len(task_text) < 50:
            return "low"
        elif len(task_text) < 150:
            return "medium"
        else:
            return "high"
    
    def is_session_command(self, text: str) -> bool:
        """Check if the text is a session control command"""
        session_commands = [
            "close session", "end session", "logout", "exit",
            "close chat", "end chat", "stop", "quit"
        ]
        
        text_lower = text.lower().strip()
        return any(cmd in text_lower for cmd in session_commands)