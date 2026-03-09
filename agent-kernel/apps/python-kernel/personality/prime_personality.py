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

Key responsibilities:
1. Classify user intent
2. Decompose complex requests into discrete processes
3. Identify required capabilities for each process
4. Flag potential security or permission concerns

Output a JSON structure with:
- intent: High-level classification
- goals: List of objectives
- processes: Array of process definitions with capabilities
- context_hints: Additional context for compilation""")


class PrimePersonality:
    def __init__(self, config: PrimePersonalityConfig | None = None):
        self.config = config or PrimePersonalityConfig()
        self.run_mode = os.environ.get("KERNEL_RUN_MODE", "real")
        self.agent = self._create_agent() if self.run_mode == "real" else None

    def _create_agent(self) -> Agent | None:
        try:
            model = OpenAIModel(self.config.model_name)
            return Agent(
                model=model,
                system_prompt=self.config.system_prompt,
                result_type=IntermediateRepresentation,
            )
        except Exception as exc:
            logger.warning(
                "Failed to initialize LLM agent, will use mock mode for this instance",
                error=str(exc),
            )
            return None

    async def process_request(
        self,
        request: Request,
        session_context: dict[str, Any] | None = None,
    ) -> IntermediateRepresentation:
        logger.info(
            "Processing request with Prime Personality",
            request_id=request.id,
            session_id=request.session_id,
            run_mode=self.run_mode,
        )

        if self.run_mode == "mock" or self.agent is None:
            return self._build_mock_ir(request)

        context = self._build_context(request, session_context)
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

    def _build_context(self, request: Request, session_context: dict[str, Any] | None) -> str:
        context_parts = [
            f"User Request: {request.message}",
            f"Request ID: {request.id}",
            f"Session ID: {request.session_id}",
            f"User ID: {request.user_id}",
        ]
        if session_context:
            context_parts.append(f"Session Context: {json.dumps(session_context, indent=2, ensure_ascii=False)}")
        context_parts.append("""
Analyze this request and decompose it into a structured intermediate representation.
Consider:
1. What is the user's primary intent?
2. What are the discrete steps/processes needed?
3. What capabilities (tools/skills) might be required?
4. Are there any security or permission considerations?

Provide a structured JSON response matching the IntermediateRepresentation schema.
""")
        return "\n\n".join(context_parts)

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
