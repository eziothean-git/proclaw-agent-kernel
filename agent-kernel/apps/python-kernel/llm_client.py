"""
LLM Client Configuration - Support multiple LLM providers

Supports:
- Volcengine Ark (火山方舟) - 默认
- OpenAI
- Custom OpenAI-compatible APIs
"""
import os
from dataclasses import dataclass
from typing import Any

import structlog
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

logger = structlog.get_logger()


@dataclass
class LLMConfig:
    """LLM Configuration"""
    provider: str = "ark"  # ark (default), openai, custom
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4000
    timeout: int = 60
    
    @classmethod
    def from_env(cls) -> "LLMConfig":
        """Create config from environment variables"""
        provider = os.environ.get("LLM_PROVIDER", "ark").lower()
        
        if provider == "ark":
            # Volcengine Ark (火山方舟) - 默认
            return cls(
                provider="ark",
                api_key=os.environ.get("ARK_API_KEY", ""),
                base_url=os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
                model=os.environ.get("ARK_MODEL", "glm-4-7-251222"),
                temperature=float(os.environ.get("LLM_TEMPERATURE", "0.7")),
                max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4000")),
            )
        elif provider == "openai":
            return cls(
                provider="openai",
                api_key=os.environ.get("OPENAI_API_KEY", ""),
                base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                model=os.environ.get("OPENAI_MODEL", "gpt-4"),
                temperature=float(os.environ.get("LLM_TEMPERATURE", "0.7")),
                max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4000")),
            )
        elif provider == "custom":
            return cls(
                provider="custom",
                api_key=os.environ.get("CUSTOM_API_KEY", ""),
                base_url=os.environ.get("CUSTOM_BASE_URL", ""),
                model=os.environ.get("CUSTOM_MODEL", ""),
                temperature=float(os.environ.get("LLM_TEMPERATURE", "0.7")),
                max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4000")),
            )
        else:
            # Default to Ark
            return cls(
                provider="ark",
                api_key=os.environ.get("ARK_API_KEY", ""),
                base_url=os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
                model=os.environ.get("ARK_MODEL", "doubao-pro-32k"),
                temperature=float(os.environ.get("LLM_TEMPERATURE", "0.7")),
                max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "4000")),
            )
    
    def validate(self) -> bool:
        """Validate configuration"""
        if not self.api_key:
            logger.error(f"No API key configured for provider: {self.provider}")
            return False
        if not self.base_url:
            logger.error(f"No BASE_URL configured for provider: {self.provider}")
            return False
        if not self.model:
            logger.error(f"No MODEL configured for provider: {self.provider}")
            return False
        return True


class LLMClient:
    """Unified LLM Client supporting multiple providers"""
    
    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig.from_env()
        self.logger = logger.bind(component="LLMClient", provider=self.config.provider)
        self._agent: Any = None
    
    def initialize(self, system_prompt: str = "") -> bool:
        """Initialize the LLM client"""
        if not self.config.validate():
            return False
        
        try:
            # Create OpenAI-compatible provider
            from pydantic_ai.providers.openai import OpenAIProvider
            
            provider = OpenAIProvider(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
            )
            
            model = OpenAIModel(
                self.config.model,
                provider=provider,
            )
            
            self._agent = Agent(
                model=model,
                system_prompt=system_prompt or "You are a helpful assistant.",
            )
            
            self.logger.info(
                "LLM client initialized",
                model=self.config.model,
                base_url=self.config.base_url,
                provider=self.config.provider,
            )
            return True
            
        except Exception as e:
            self.logger.error("Failed to initialize LLM client", error=str(e))
            return False
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt"""
        if not self._agent:
            raise RuntimeError("LLM client not initialized. Call initialize() first.")
        
        try:
            result = await self._agent.run(user_prompt=prompt)
            # Handle different result types from pydantic-ai
            if hasattr(result, 'output'):
                # AgentRunResult has .output attribute
                return str(result.output)
            elif hasattr(result, 'data'):
                # Some results have .data
                return str(result.data)
            else:
                return str(result)
        except Exception as e:
            self.logger.error("Generation failed", error=str(e))
            raise
    
    def get_model_info(self) -> dict[str, Any]:
        """Get current model information"""
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "base_url": self.config.base_url,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }


# Singleton instance
_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """Get or create singleton LLM client"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def configure_llm(
    provider: str = "ark",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> LLMClient:
    """Configure LLM with explicit parameters"""
    global _llm_client
    
    config = LLMConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url or ("https://ark.cn-beijing.volces.com/api/v3" if provider == "ark" else ""),
        model=model or ("glm-4-7-251222" if provider == "ark" else "gpt-4"),
        temperature=temperature,
        max_tokens=max_tokens,
    )
    
    _llm_client = LLMClient(config)
    return _llm_client
