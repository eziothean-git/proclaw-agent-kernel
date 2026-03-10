"""
Agent Output Parser - Parse LLM output into structured intents.

Converts raw LLM text output into ParsedIntent objects that can be
used to drive the Agent Thread's SEE-ACT-UPDATE loop.

Supports multiple formats:
- Structured JSON/YAML output
- Heuristic parsing for unstructured text
- Phase-specific parsing rules
"""
import json
import re
from typing import Any

import structlog
import yaml

from thread_runtime.models import (
    IntentType,
    ParsedIntent,
    Phase,
    PhaseTransitionIntent,
    ToolCallIntent,
)

logger = structlog.get_logger()


class AgentOutputParser:
    """
    Parser for Agent Thread LLM output.
    
    Uses phase-specific parsing strategies to extract:
    - Tool call intents
    - Phase transition requests
    - Final answers
    - Error conditions
    """
    
    def __init__(self):
        self.logger = logger.bind(component="AgentOutputParser")
        
        # Compile regex patterns for heuristic parsing
        self._patterns = {
            "json_code_block": re.compile(r"```json\s*(.*?)\s*```", re.DOTALL),
            "yaml_code_block": re.compile(r"```yaml\s*(.*?)\s*```", re.DOTALL),
            "any_code_block": re.compile(r"```\s*(.*?)\s*```", re.DOTALL),
            "tool_call": re.compile(
                r"(?:tool_call|call_tool|execute)\s*[:\-]?\s*(.+)",
                re.IGNORECASE,
            ),
            "final_answer": re.compile(
                r"(?:final_answer|answer|result)\s*[:\-]?\s*(.+)",
                re.IGNORECASE | re.DOTALL,
            ),
        }
    
    def parse(
        self,
        raw_output: str,
        current_phase: Phase,
    ) -> ParsedIntent:
        """
        Parse raw LLM output into structured intent.
        
        Args:
            raw_output: Raw text output from LLM
            current_phase: Current execution phase
            
        Returns:
            ParsedIntent with structured data
        """
        self.logger.debug(
            "Parsing agent output",
            phase=current_phase.value,
            output_length=len(raw_output),
        )
        
        # Try structured parsing first (JSON/YAML)
        structured = self._try_structured_parse(raw_output)
        if structured:
            return self._parse_structured(structured, raw_output, current_phase)
        
        # Fall back to heuristic parsing
        return self._heuristic_parse(raw_output, current_phase)
    
    def _try_structured_parse(self, raw_output: str) -> dict[str, Any] | None:
        """
        Try to extract structured data from output.
        
        Looks for:
        1. JSON code blocks
        2. YAML code blocks
        3. Raw JSON objects
        4. Raw YAML documents
        """
        # Try JSON code block
        match = self._patterns["json_code_block"].search(raw_output)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try YAML code block
        match = self._patterns["yaml_code_block"].search(raw_output)
        if match:
            try:
                return yaml.safe_load(match.group(1))
            except yaml.YAMLError:
                pass
        
        # Try any code block (might be JSON/YAML without language tag)
        match = self._patterns["any_code_block"].search(raw_output)
        if match:
            content = match.group(1)
            # Try JSON first
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                pass
            # Try YAML
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError:
                pass
        
        # Try raw JSON (output starts with {)
        stripped = raw_output.strip()
        if stripped.startswith("{"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        
        # Try raw YAML
        if stripped.startswith("intent:") or stripped.startswith("---"):
            try:
                return yaml.safe_load(stripped)
            except yaml.YAMLError:
                pass
        
        return None
    
    def _parse_structured(
        self,
        data: dict[str, Any],
        raw_output: str,
        current_phase: Phase,
    ) -> ParsedIntent:
        """Parse structured data based on intent type."""
        intent_str = data.get("intent", "").lower()
        
        if intent_str == "tool_call" or "tool_calls" in data:
            return self._parse_tool_call_intent(data, raw_output)
        
        elif intent_str == "phase_transition" or "to_phase" in data:
            return self._parse_phase_transition_intent(data, raw_output, current_phase)
        
        elif intent_str == "final_answer" or "answer" in data:
            return self._parse_final_answer_intent(data, raw_output)
        
        elif intent_str == "clarification" or "question" in data:
            return self._parse_clarification_intent(data, raw_output)
        
        elif intent_str == "error":
            return self._parse_error_intent(data, raw_output)
        
        # Unknown structured format, treat as heuristic
        return self._heuristic_parse(raw_output, current_phase)
    
    def _parse_tool_call_intent(
        self,
        data: dict[str, Any],
        raw_output: str,
    ) -> ParsedIntent:
        """Parse tool call intent from structured data."""
        tool_calls_data = data.get("tool_calls", [])
        
        # Handle single tool call (not in list)
        if not tool_calls_data and "skill" in data:
            tool_calls_data = [data]
        
        tool_calls = []
        for tc in tool_calls_data:
            tool_calls.append(ToolCallIntent(
                skill_name=tc.get("skill", tc.get("skill_name", "")),
                tool_name=tc.get("tool", tc.get("tool_name", "")),
                parameters=tc.get("parameters", tc.get("params", {})),
                reasoning=tc.get("reasoning", data.get("reasoning", "")),
            ))
        
        return ParsedIntent(
            intent_type=IntentType.TOOL_CALL,
            confidence=0.9 if tool_calls else 0.5,
            raw_content=raw_output,
            structured_data=data,
            tool_calls=tool_calls,
        )
    
    def _parse_phase_transition_intent(
        self,
        data: dict[str, Any],
        raw_output: str,
        current_phase: Phase,
    ) -> ParsedIntent:
        """Parse phase transition intent from structured data."""
        from_phase_str = data.get("from_phase", current_phase.value)
        to_phase_str = data.get("to_phase", data.get("to", ""))
        
        try:
            from_phase = Phase(from_phase_str)
        except ValueError:
            from_phase = current_phase
        
        try:
            to_phase = Phase(to_phase_str)
        except ValueError:
            # Invalid phase, treat as unknown intent
            return self._heuristic_parse(raw_output, current_phase)
        
        phase_transition = PhaseTransitionIntent(
            from_phase=from_phase,
            to_phase=to_phase,
            reason=data.get("reason", ""),
            artifacts_to_finalize=data.get("artifacts_to_finalize", []),
        )
        
        return ParsedIntent(
            intent_type=IntentType.PHASE_TRANSITION,
            confidence=0.9,
            raw_content=raw_output,
            structured_data=data,
            phase_transition=phase_transition,
        )
    
    def _parse_final_answer_intent(
        self,
        data: dict[str, Any],
        raw_output: str,
    ) -> ParsedIntent:
        """Parse final answer intent from structured data."""
        answer = data.get("answer", data.get("content", data.get("result", raw_output)))
        
        return ParsedIntent(
            intent_type=IntentType.FINAL_ANSWER,
            confidence=0.9,
            raw_content=raw_output,
            structured_data=data,
            final_answer=str(answer),
        )
    
    def _parse_clarification_intent(
        self,
        data: dict[str, Any],
        raw_output: str,
    ) -> ParsedIntent:
        """Parse clarification request intent from structured data."""
        question = data.get("question", data.get("clarification", ""))
        
        return ParsedIntent(
            intent_type=IntentType.CLARIFICATION,
            confidence=0.8,
            raw_content=raw_output,
            structured_data=data,
            clarification_request=str(question),
        )
    
    def _parse_error_intent(
        self,
        data: dict[str, Any],
        raw_output: str,
    ) -> ParsedIntent:
        """Parse error intent from structured data."""
        error_msg = data.get("error", data.get("message", "Unknown error"))
        
        return ParsedIntent(
            intent_type=IntentType.ERROR,
            confidence=0.9,
            raw_content=raw_output,
            structured_data=data,
            error_message=str(error_msg),
        )
    
    def _heuristic_parse(
        self,
        raw_output: str,
        current_phase: Phase,
    ) -> ParsedIntent:
        """
        Heuristic parsing for unstructured text.
        
        Uses phase-specific heuristics to guess intent.
        """
        stripped = raw_output.strip().lower()
        
        # Check for completion indicators
        completion_indicators = [
            "task complete",
            "completed successfully",
            "done.",
            "finished.",
            "i have completed",
        ]
        if any(ind in stripped for ind in completion_indicators):
            return ParsedIntent(
                intent_type=IntentType.FINAL_ANSWER,
                confidence=0.7,
                raw_content=raw_output,
                structured_data={},
                final_answer=raw_output,
            )
        
        # Check for tool call indicators
        tool_indicators = [
            "i will call",
            "let me use",
            "i need to execute",
            "calling tool",
        ]
        if any(ind in stripped for ind in tool_indicators):
            # Try to extract tool info
            tool_calls = self._extract_tool_from_text(raw_output)
            return ParsedIntent(
                intent_type=IntentType.TOOL_CALL,
                confidence=0.6 if tool_calls else 0.4,
                raw_content=raw_output,
                structured_data={},
                tool_calls=tool_calls,
            )
        
        # Check for phase transition indicators
        if current_phase == Phase.EXPLORE:
            transition_indicators = [
                "i have gathered enough",
                "ready to execute",
                "let me proceed to execute",
            ]
            if any(ind in stripped for ind in transition_indicators):
                return ParsedIntent(
                    intent_type=IntentType.PHASE_TRANSITION,
                    confidence=0.6,
                    raw_content=raw_output,
                    structured_data={},
                    phase_transition=PhaseTransitionIntent(
                        from_phase=Phase.EXPLORE,
                        to_phase=Phase.EXECUTE,
                        reason="Heuristic: gathered enough information",
                    ),
                )
        
        # Check for clarification indicators
        question_indicators = [
            "i need clarification",
            "could you clarify",
            "i don't understand",
            "what do you mean by",
        ]
        if any(ind in stripped for ind in question_indicators):
            return ParsedIntent(
                intent_type=IntentType.CLARIFICATION,
                confidence=0.6,
                raw_content=raw_output,
                structured_data={},
                clarification_request=raw_output,
            )
        
        # Default: unknown intent
        return ParsedIntent(
            intent_type=IntentType.UNKNOWN,
            confidence=0.3,
            raw_content=raw_output,
            structured_data={},
        )
    
    def _extract_tool_from_text(self, text: str) -> list[ToolCallIntent]:
        """Try to extract tool call info from unstructured text."""
        tool_calls = []
        
        # Look for patterns like: skill.tool or skill: tool
        patterns = [
            r"(\w+)[\.:\s]+(\w+)\s*\(([^)]*)\)",  # skill.tool(params)
            r"(\w+)[\.:\s]+(\w+)",  # skill.tool
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) >= 2:
                    skill = match[0]
                    tool = match[1]
                    params_str = match[2] if len(match) > 2 else ""
                    
                    # Try to parse parameters
                    params = {}
                    if params_str:
                        # Simple param parsing: key=value, key2=value2
                        param_pairs = re.findall(r"(\w+)\s*=\s*([^,]+)", params_str)
                        for key, value in param_pairs:
                            params[key.strip()] = value.strip().strip('"\'')
                    
                    tool_calls.append(ToolCallIntent(
                        skill_name=skill,
                        tool_name=tool,
                        parameters=params,
                        reasoning="Extracted from unstructured text",
                    ))
        
        return tool_calls


# Singleton instance
_output_parser: AgentOutputParser | None = None


def get_output_parser() -> AgentOutputParser:
    """Get or create singleton instance."""
    global _output_parser
    if _output_parser is None:
        _output_parser = AgentOutputParser()
    return _output_parser
