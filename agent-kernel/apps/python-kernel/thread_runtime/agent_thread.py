"""
Agent Thread - Execution-level Agent that operates in local context.
"""
import os
from datetime import datetime
from typing import Any

import structlog
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.openai import OpenAIModel

from schemas.models import AgentOutput, CompiledContext, TaskSnapshot, ToolCallRequest
from storage.runtime_store import get_memory_manager

logger = structlog.get_logger()


class AgentThread:
    def __init__(
        self,
        task: TaskSnapshot,
        compiled_context: CompiledContext,
        executor_client: Any,
    ):
        self.task = task
        self.context = compiled_context
        self.executor_client = executor_client
        self.logger = logger.bind(component="AgentThread", task_id=task.id)
        self.run_mode = os.environ.get("KERNEL_RUN_MODE", "real")
        self.agent = self._create_agent() if self.run_mode == "real" else None
        self.conversation_history: list[ModelMessage] = []
        self.max_iterations = 10
        self.current_iteration = 0
        self.observations: list[dict[str, Any]] = []

    def _create_agent(self) -> Agent | None:
        try:
            model = OpenAIModel("gpt-4")
            return Agent(
                model=model,
                system_prompt=self._build_system_prompt(),
                result_type=AgentOutput,
                tools=[],
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to initialize LLM agent, will use mock execution for this instance",
                error=str(exc),
            )
            return None

    def _build_system_prompt(self) -> str:
        lines = [
            "You are an Agent Thread executing a specific task.",
            "",
            f"Task Goal: {self.context.task_goal}",
            "",
            "Constraints:",
        ]
        lines.extend([f"  - {constraint}" for constraint in self.context.constraints])
        lines.extend(["", "Allowed Capabilities:"])
        lines.extend([f"  - {cap}" for cap in self.context.allowed_capabilities])
        if self.context.forbidden_capabilities:
            lines.extend(["", "Forbidden Capabilities (DO NOT USE):"])
            lines.extend([f"  - {cap}" for cap in self.context.forbidden_capabilities])
        lines.extend([
            "",
            "Instructions:",
            "1. Work within your allowed capabilities only",
            "2. If you need a tool, request it explicitly",
            "3. If you encounter errors, attempt to correct them",
            "4. Report success or failure clearly",
            "5. Prefer recent context and use fs-skill to inspect logs only when needed",
        ])
        return "\n".join(lines)

    async def run(self) -> AgentOutput:
        self.logger.info("Starting agent thread execution", goal=self.context.task_goal, run_mode=self.run_mode)
        if self.run_mode == "mock" or self.agent is None:
            return await self._run_mock()

        try:
            while self.current_iteration < self.max_iterations:
                self.current_iteration += 1
                result = await self._run_step()
                if result.success and not result.tool_calls:
                    result.observations = self.observations
                    return result
                if result.tool_calls:
                    observations = await self._execute_tool_calls(result.tool_calls)
                    self.observations.extend(observations)
                    for obs in observations:
                        self.conversation_history.append(ModelMessage.user(str(obs)))
                    if all(obs.get("success", False) for obs in observations):
                        continue
            return AgentOutput(
                task_id=self.task.id,
                content="Maximum iterations reached without completion",
                success=False,
                error="Max iterations exceeded",
                observations=self.observations,
            )
        except Exception as e:
            self.logger.error("Agent thread failed", error=str(e))
            return AgentOutput(
                task_id=self.task.id,
                content=f"Execution failed: {str(e)}",
                success=False,
                error=str(e),
                observations=self.observations,
            )

    async def _run_step(self) -> AgentOutput:
        prompt = self._build_prompt()
        result = await self.agent.run(user_prompt=prompt, message_history=self.conversation_history)
        self.conversation_history.extend(result.new_messages())
        return result.data

    def _build_prompt(self) -> str:
        if self.current_iteration <= 1:
            return f"Execute the following task: {self.context.task_goal}"
        return "Continue with the task based on previous observations."

    async def _run_mock(self) -> AgentOutput:
        metadata = self.context.session_context.get("request_metadata", {})
        mock_tool_call = metadata.get("mock_tool_call") if isinstance(metadata, dict) else None

        if isinstance(mock_tool_call, dict):
            observations = await self._execute_tool_calls([
                {
                    "skill": mock_tool_call.get("skill_name", "fs-skill"),
                    "tool": mock_tool_call.get("tool_name", "list_directory"),
                    "parameters": mock_tool_call.get("parameters", {}),
                }
            ])
            self.observations.extend(observations)
            success = all(obs.get("success", False) for obs in observations)
            content = "Mock execution completed"
            if observations:
                content = f"Mock execution completed with {len(observations)} observation(s)"
            return AgentOutput(
                task_id=self.task.id,
                content=content,
                success=success,
                error=None if success else observations[0].get("error", "Mock tool failure"),
                observations=self.observations,
            )

        return AgentOutput(
            task_id=self.task.id,
            content=f"Mock execution completed for task: {self.context.task_goal}",
            success=True,
            observations=self.observations,
        )

    async def _execute_tool_calls(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        memory_manager = get_memory_manager()
        observations = []
        for call in tool_calls:
            tool_request = ToolCallRequest(
                request_id=f"{self.task.id}_{datetime.utcnow().timestamp()}",
                session_id=self.task.session_id,
                skill_name=call.get("skill", ""),
                tool_name=call.get("tool", ""),
                parameters=call.get("parameters", {}),
            )

            await memory_manager.save_event(
                self.task.session_id,
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "session_id": self.task.session_id,
                    "request_id": self.context.session_context.get("request_id"),
                    "task_id": self.task.id,
                    "phase": "tool_request",
                    "actor": "agent_thread",
                    "summary": f"{tool_request.skill_name}.{tool_request.tool_name}",
                    "status": "started",
                },
            )

            result = await self.executor_client.execute_tool(tool_request)
            observation = {
                "tool": tool_request.tool_name,
                "skill": tool_request.skill_name,
                "success": result.success,
                "result": result.result,
                "error": result.error,
            }
            observations.append(observation)

            await memory_manager.save_event(
                self.task.session_id,
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "session_id": self.task.session_id,
                    "request_id": self.context.session_context.get("request_id"),
                    "task_id": self.task.id,
                    "phase": "tool_result",
                    "actor": "executor",
                    "summary": f"{tool_request.skill_name}.{tool_request.tool_name}",
                    "status": "completed" if result.success else "failed",
                },
            )
        return observations
