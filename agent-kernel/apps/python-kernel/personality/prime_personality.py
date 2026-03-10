"""
Prime Personality - Stateless orchestration layer.
Converts user requests into structured intermediate representations.
"""
import json
from typing import Any

import structlog
from pydantic import BaseModel, Field

from llm_client import get_llm_client, LLMClient
from schemas.models import IntermediateRepresentation, Request

logger = structlog.get_logger()


class PrimePersonalityConfig(BaseModel):
    model_name: str = Field(default="gpt-4")
    temperature: float = Field(default=0.3, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, ge=1)
    system_prompt: str = Field(default="""You are the Prime Personality of an AI Agent Kernel.
Your role is to analyze user requests and decompose them into structured processes.

You are stateless - you do not maintain memory between invocations.
Your output is an intermediate representation (IR) that will be compiled into executable contexts.

You are provided with pre-compiled context from the Master Context Compiler, which includes:
- Intent analysis and confidence scores
- Session history and recent activities
- Gathered artifacts from agent-assisted exploration (if triggered)
- Files explored and relevant context discovered

Use this pre-compiled context to make better decisions about:
1. User intent classification (leverage intent analysis if confidence is high)
2. Task decomposition (consider gathered artifacts for context)
3. Required capabilities (based on files explored and operations needed)
4. Security considerations

Key responsibilities:
1. Classify user intent using pre-compiled analysis
2. Decompose complex requests into discrete processes
3. Identify required capabilities for each process
4. Flag potential security or permission concerns
5. Leverage gathered context for cross-session queries

Output a JSON structure with:
- intent: High-level classification
- goals: List of objectives
- processes: Array of process definitions with capabilities and constraints
- context_hints: Additional context for compilation

IMPORTANT: Return ONLY the JSON object without any markdown formatting (no ```json or ``` blocks).
Example format:
{
  "intent": "file_operation",
  "goals": ["List directory contents"],
  "processes": [
    {
      "name": "list_files",
      "goal": "List files in current directory",
      "capabilities": ["fs-skill"],
      "constraints": [],
      "security_level": "low"
    }
  ],
  "context_hints": {}
}""")


class PrimePersonality:
    def __init__(self, config: PrimePersonalityConfig | None = None):
        self.config = config or PrimePersonalityConfig()
        self._client: LLMClient | None = None

    @property
    def client(self) -> LLMClient:
        """Lazy initialization of the LLM client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> LLMClient:
        """Create and initialize LLM client."""
        client = get_llm_client()
        success = client.initialize(system_prompt=self.config.system_prompt)
        if not success:
            raise RuntimeError("Failed to initialize LLM client. Check your API configuration.")
        return client

    async def process_request(
        self,
        request: Request,
        session_context: dict[str, Any] | None = None,
    ) -> IntermediateRepresentation:
        logger.info(
            "Processing request with Prime Personality",
            request_id=request.id,
            session_id=request.session_id,
            has_compiled_context=session_context is not None,
        )

        context = self._build_enhanced_context(request, session_context)
        
        try:
            # Use unified LLM client
            result_text = await self.client.generate(context)
            
            # Clean markdown code blocks if present
            result_text = self._extract_json_from_markdown(result_text)
            
            # Parse JSON result
            result_data = json.loads(result_text)
            
            # Create IntermediateRepresentation
            ir = IntermediateRepresentation(
                request_id=request.id,
                intent=result_data.get("intent", "execute"),
                goals=result_data.get("goals", []),
                processes=result_data.get("processes", []),
                context_hints=result_data.get("context_hints", {}),
            )
            
            logger.info(
                "Generated intermediate representation",
                request_id=request.id,
                intent=ir.intent,
                process_count=len(ir.processes),
            )
            return ir
            
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse LLM response as JSON",
                request_id=request.id,
                error=str(e),
                response=result_text[:500] if 'result_text' in locals() else "N/A",
            )
            raise RuntimeError(f"LLM returned invalid JSON: {e}")
        except Exception as e:
            logger.error(
                "Failed to process request",
                request_id=request.id,
                error=str(e),
            )
            raise

    def _extract_json_from_markdown(self, text: str) -> str:
        """Extract JSON content from markdown code blocks."""
        import re

        # Try to find JSON in markdown code blocks
        patterns = [
            r"```json\s*\n(.*?)\n```",  # ```json ... ```
            r"```yaml\s*\n(.*?)\n```",  # ```yaml ... ```
            r"```\s*\n(.*?)\n```",      # ``` ... ```
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()

        # If no code blocks found, return original text stripped
        return text.strip()

    def _build_enhanced_context(self, request: Request, compiled_context: Any | None) -> str:
        """Build enhanced context using pre-compiled information from Master Compiler."""
        context_parts = [
            f"User Request: {request.message}",
            f"Request ID: {request.id}",
            f"Session ID: {request.session_id}",
            f"User ID: {request.user_id}",
        ]

        if compiled_context:
            # Extract structured information from CompiledContext
            session_ctx = compiled_context.session_context if hasattr(compiled_context, 'session_context') else compiled_context

            if isinstance(session_ctx, dict):
                # Add intent analysis if available
                if 'analysis' in session_ctx:
                    analysis = session_ctx['analysis']
                    context_parts.append(f"\nPre-compiled Intent Analysis:")
                    if isinstance(analysis, dict):
                        if 'primary_intent' in analysis:
                            context_parts.append(f"- Primary Intent: {analysis['primary_intent']}")
                        if 'confidence' in analysis:
                            context_parts.append(f"- Confidence: {analysis['confidence']}")
                        if 'keywords' in analysis:
                            context_parts.append(f"- Keywords: {', '.join(analysis['keywords'])}")
                        if 'complexity_score' in analysis:
                            context_parts.append(f"- Complexity Score: {analysis['complexity_score']}")

                # Add session history summary if available
                if 'recent_messages' in session_ctx and session_ctx['recent_messages']:
                    context_parts.append(f"\nSession History:")
                    recent = session_ctx['recent_messages']
                    if isinstance(recent, list) and len(recent) > 0:
                        # Only include last 3 messages to avoid context overflow
                        for msg in recent[-3:]:
                            if isinstance(msg, dict):
                                role = msg.get('role', 'unknown')
                                content = msg.get('content', '')
                                context_parts.append(f"- [{role}]: {content[:100]}...")

                # Add gathered artifacts if available (from agent-assisted exploration)
                if 'artifacts' in session_ctx and session_ctx['artifacts']:
                    context_parts.append(f"\nGathered Artifacts:")
                    artifacts = session_ctx['artifacts']
                    if isinstance(artifacts, list):
                        for artifact in artifacts[:5]:  # Limit to 5 artifacts
                            if isinstance(artifact, dict):
                                name = artifact.get('name', 'unnamed')
                                content_preview = str(artifact.get('content', ''))[:50]
                                context_parts.append(f"- {name}: {content_preview}...")

                # Add explored files if available
                if 'explored_files' in session_ctx and session_ctx['explored_files']:
                    context_parts.append(f"\nExplored Files:")
                    files = session_ctx['explored_files']
                    if isinstance(files, list):
                        for file_info in files[:10]:  # Limit to 10 files
                            if isinstance(file_info, dict):
                                path = file_info.get('path', 'unknown')
                                file_type = file_info.get('type', 'file')
                                context_parts.append(f"- {path} ({file_type})")

        context_parts.extend([
            "\nAnalyze the user request and output a JSON structure with:",
            "- intent: High-level classification (e.g., 'file_operation', 'code_generation', 'analysis')",
            "- goals: List of objectives to accomplish",
            "- processes: Array of process definitions, each with:",
            "  * name: Process name",
            "  * goal: Specific goal for this process",
            "  * capabilities: List of required skills (e.g., ['fs-skill', 'shell-skill'])",
            "  * constraints: List of constraints (e.g., ['max_steps: 10'])",
            "  * security_level: 'low', 'medium', or 'high'",
            "- context_hints: Additional context for compilation",
            "",
            "Use the pre-compiled context above to make better decisions about intent classification and task decomposition.",
        ])

        return "\n".join(context_parts)


_prime_personality: PrimePersonality | None = None


def get_prime_personality() -> PrimePersonality:
    global _prime_personality
    if _prime_personality is None:
        _prime_personality = PrimePersonality()
    return _prime_personality


def reset_prime_personality() -> None:
    global _prime_personality
    _prime_personality = None
