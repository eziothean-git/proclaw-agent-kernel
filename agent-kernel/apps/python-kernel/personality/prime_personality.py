"""
Prime Personality - Stateless orchestration layer.
Converts user requests into structured intermediate representations.
"""
import json
import os
from typing import Any

import structlog
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

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
- context_hints: Additional context for compilation""")


class PrimePersonality:
    def __init__(self, config: PrimePersonalityConfig | None = None):
        self.config = config or PrimePersonalityConfig()
        self._agent: Agent | None = None

    @property
    def agent(self) -> Agent:
        """Lazy initialization of the agent."""
        if self._agent is None:
            self._agent = self._create_agent()
        return self._agent

    def _create_agent(self) -> Agent:
        model = OpenAIModel(self.config.model_name)
        return Agent(
            model=model,
            system_prompt=self.config.system_prompt,
            result_type=IntermediateRepresentation,
        )

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

        # Check for explicit mock override in metadata
        metadata = request.metadata or {}
        if metadata.get("force_mock"):
            logger.warning("Force mock mode enabled via metadata", request_id=request.id)
            return self._build_mock_ir(request)

        context = self._build_enhanced_context(request, session_context)
        result = await self.agent.run(
            user_prompt=context,
            model_settings={
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            },
        )

        logger.info(
            "Generated intermediate representation",
            request_id=request.id,
            intent=result.data.intent,
            process_count=len(result.data.processes),
        )
        return result.data

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
                    context_parts.append("\n## Intent Analysis (from Master Compiler)")
                    if isinstance(analysis, dict):
                        if 'intent' in analysis:
                            intent = analysis['intent']
                            if isinstance(intent, dict):
                                if 'detected_intents' in intent:
                                    context_parts.append(f"- Detected Intents: {', '.join(intent['detected_intents'])}")
                                if 'confidence' in intent:
                                    context_parts.append(f"- Confidence: {intent['confidence']:.2f}")
                                if 'primary_intent' in intent:
                                    context_parts.append(f"- Primary Intent: {intent['primary_intent']}")
                        if 'complexity_score' in analysis:
                            context_parts.append(f"- Complexity Score: {analysis['complexity_score']:.2f}")

                # Add session information
                if 'session' in session_ctx:
                    session = session_ctx['session']
                    if isinstance(session, dict) and session.get('task_count', 0) > 0:
                        context_parts.append(f"\n## Session Context")
                        context_parts.append(f"- Task Count: {session.get('task_count', 0)}")
                        if 'history_summary' in session:
                            context_parts.append(f"- History: {json.dumps(session['history_summary'], ensure_ascii=False)}")

                # Add gathered artifacts from agent-assisted exploration
                if 'gathered_artifacts' in session_ctx:
                    artifacts = session_ctx['gathered_artifacts']
                    if artifacts:
                        context_parts.append("\n## Gathered Artifacts (from Agent Exploration)")
                        for i, artifact in enumerate(artifacts[:5], 1):  # Limit to 5 artifacts
                            if isinstance(artifact, dict):
                                slot_type = artifact.get('slot_type', 'unknown')
                                content = artifact.get('content', '')
                                priority = artifact.get('priority', 0)
                                context_parts.append(f"{i}. [{slot_type}] (priority: {priority}): {content[:200]}{'...' if len(content) > 200 else ''}")

                # Add files explored
                if 'files_explored' in session_ctx:
                    files = session_ctx['files_explored']
                    if files:
                        context_parts.append("\n## Files Explored")
                        for f in files[:10]:  # Limit to 10 files
                            context_parts.append(f"- {f}")

                # Add compilation metadata
                if 'metadata' in session_ctx:
                    metadata = session_ctx['metadata']
                    if isinstance(metadata, dict):
                        if metadata.get('agent_assisted'):
                            context_parts.append("\n## Compilation Method")
                            context_parts.append("- Agent-assisted compilation was used (complex or cross-session query)")
                            if 'patch_steps' in metadata:
                                context_parts.append(f"- Exploration Steps: {metadata['patch_steps']}")
                            if 'patch_confidence' in metadata:
                                context_parts.append(f"- Exploration Confidence: {metadata['patch_confidence']}")
                        elif metadata.get('rule_based'):
                            context_parts.append("\n## Compilation Method")
                            context_parts.append("- Rule-based compilation was used (standard query)")

        context_parts.append("""

## Instructions

Based on the pre-compiled context above, analyze the user request and generate a structured intermediate representation.

The pre-compiled context includes:
- Intent analysis (confidence scores, detected intents)
- Session history (if available)
- Gathered artifacts from agent exploration (for complex queries)
- Files explored (relevant context discovered)

Use this information to:
1. Refine your intent classification (trust high-confidence pre-analysis)
2. Consider gathered artifacts for task decomposition
3. Identify required capabilities based on files explored
4. Set appropriate security levels

Provide a structured JSON response matching the IntermediateRepresentation schema.
""")
        return "\n".join(context_parts)

    def _build_mock_ir(self, request: Request) -> IntermediateRepresentation:
        metadata = request.metadata or {}
        if isinstance(metadata.get("mock_ir"), dict):
            payload = dict(metadata["mock_ir"])
            payload.setdefault("request_id", request.id)
            payload.setdefault("context_hints", {})
            return IntermediateRepresentation(**payload)

        message = request.message.lower()
        capabilities = []
        if any(token in message for token in ["file", "文件", "目录", "read", "write", "list"]):
            capabilities.append("fs-skill")
        if any(token in message for token in ["shell", "命令", "command", "bash", "exec"]):
            capabilities.append("shell-skill")
        if not capabilities:
            capabilities = ["fs-skill", "shell-skill"]

        return IntermediateRepresentation(
            request_id=request.id,
            intent="mock_execute",
            goals=[request.message],
            processes=[
                {
                    "name": "mock-process",
                    "goal": request.message,
                    "capabilities": capabilities,
                    "constraints": ["Use only explicitly allowed capabilities"],
                    "security_level": "medium",
                }
            ],
            context_hints={
                "request_metadata": metadata,
                "mode": "mock",
            },
        )


_prime_personality: PrimePersonality | None = None


def get_prime_personality() -> PrimePersonality:
    global _prime_personality
    if _prime_personality is None:
        _prime_personality = PrimePersonality()
    return _prime_personality


def reset_prime_personality() -> None:
    global _prime_personality
    _prime_personality = None
