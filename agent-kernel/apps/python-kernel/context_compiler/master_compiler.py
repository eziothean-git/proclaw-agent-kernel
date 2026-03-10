"""
Master Context Compiler - Compiles context for Prime Personality.

Follows "rules-first, model-assisted when needed" principle:
1. First, compile context using deterministic rules
2. Only trigger PrimeContextCompilerAgent when:
   - Intent confidence is low (< 0.6)
   - Request involves cross-session queries
   - Complexity score is high (> 0.7)
3. Agent is read-only, step-limited (3-5 steps), returns Context Patch
4. Complete audit trail via PersistentEventLog

Key Design:
- Stateless across requests (Prime Personality is stateless)
- Stateful within single compile() call (Agent maintains exploration state)
- Caching to avoid repeated exploration for same request patterns
"""
import asyncio
import hashlib
import json
import time
from datetime import datetime
from typing import Any

import structlog

from context_compiler.compilation_auditor import PrimeCompilationAuditor
from context_compiler.models import PrimeCompilerConfig
from context_compiler.prime_compiler_agent import PrimeContextCompilerAgent
from schemas.models import CompiledContext, Request, Session

logger = structlog.get_logger()


class MasterContextCompiler:
    """
    Compiles context for Prime Personality using rules-first approach.
    
    Responsibilities:
    - Rule-based context compilation (fast path)
    - Trigger determination for agent assistance
    - Agent lifecycle management (create, run, destroy)
    - Context patch application
    - Audit record generation
    
    Thread Safety:
    - This class is stateless and thread-safe
    - All state is local to compile() calls
    - Cache uses simple dict (consider thread-safe cache for production)
    """
    
    def __init__(self, config: PrimeCompilerConfig | None = None):
        """
        Initialize Master Context Compiler.
        
        Args:
            config: Optional configuration (uses defaults if not provided)
        """
        self.config = config or PrimeCompilerConfig()
        self.logger = logger.bind(component="MasterContextCompiler")
        self.auditor = PrimeCompilationAuditor(self.config.storage_base_path)
        
        # Simple cache for exploration results
        # Format: {cache_key: (timestamp, patch)}
        self._exploration_cache: dict[str, tuple[float, Any]] = {}
        
        self.logger.info(
            "Master Context Compiler initialized",
            max_steps=self.config.max_steps,
            intent_threshold=self.config.intent_confidence_threshold,
            complexity_threshold=self.config.complexity_threshold,
        )
    
    async def compile(
        self,
        request: Request,
        session: Session,
        additional_context: dict[str, Any] | None = None,
    ) -> CompiledContext:
        """
        Compile context for Prime Personality.
        
        Two-phase compilation:
        1. Rule-based compilation (fast path)
        2. Agent-assisted compilation (if triggered)
        
        Args:
            request: The current user request
            session: Session state information
            additional_context: Any additional context to include
            
        Returns:
            CompiledContext for Prime Personality
        """
        start_time = time.time()
        self.logger.info(
            "Starting context compilation",
            request_id=request.id,
            session_id=session.id,
        )
        
        # Phase 1: Rule-based compilation
        base_context = self._rule_based_compile(request, session, additional_context)
        
        # Check cache first
        cache_key = self._compute_cache_key(request, session)
        if self.config.enable_caching:
            cached_patch = self._get_cached_patch(cache_key)
            if cached_patch:
                self.logger.info("Using cached exploration results", request_id=request.id)
                base_context = self._apply_context_patch(base_context, cached_patch)
                return base_context
        
        # Phase 2: Determine if agent assistance needed
        trigger_reason = self._determine_trigger_reason(request, base_context)
        
        if trigger_reason:
            self.logger.info(
                "Triggering agent-assisted compilation",
                request_id=request.id,
                reason=trigger_reason,
            )
            
            try:
                # Create and run agent
                agent = PrimeContextCompilerAgent(
                    request_id=request.id,
                    request=request,
                    session=session,
                    base_context=base_context,
                    max_steps=self.config.max_steps,
                )
                
                # Run agent asynchronously (non-blocking)
                patch = await agent.run()
                
                # Cache the patch if successful
                if patch.status == "complete" and self.config.enable_caching:
                    self._cache_patch(cache_key, patch)
                
                # Apply patch to base context
                base_context = self._apply_context_patch(base_context, patch)
                
                self.logger.info(
                    "Agent-assisted compilation complete",
                    request_id=request.id,
                    steps=patch.steps_used,
                    artifacts=len(patch.artifacts),
                    confidence=patch.confidence,
                )
            
            except Exception as e:
                self.logger.error(
                    "Agent-assisted compilation failed",
                    request_id=request.id,
                    error=str(e),
                )
                # Continue with base context on error
        else:
            self.logger.debug(
                "Skipping agent-assisted compilation",
                request_id=request.id,
                reason="No trigger conditions met",
            )
            
            # Generate summary for rule-only compilation
            self._save_rule_only_summary(request, session, start_time)
        
        duration_ms = int((time.time() - start_time) * 1000)
        self.logger.info(
            "Context compilation complete",
            request_id=request.id,
            duration_ms=duration_ms,
        )
        
        return base_context
    
    def _rule_based_compile(
        self,
        request: Request,
        session: Session,
        additional_context: dict[str, Any] | None,
    ) -> CompiledContext:
        """
        Compile context using deterministic rules.
        
        This is the fast path that doesn't require LLM calls.
        
        Args:
            request: User request
            session: Session state
            additional_context: Extra context
            
        Returns:
            Base CompiledContext
        """
        # Build request context
        request_context = {
            "id": request.id,
            "message": request.message,
            "user_id": request.user_id,
            "created_at": request.created_at.isoformat() if request.created_at else None,
        }
        
        # Build session context
        session_context = {
            "id": session.id,
            "task_count": session.task_count,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "last_activity": session.last_activity.isoformat() if session.last_activity else None,
        }
        
        # Add history if available
        if session.task_count > 0:
            session_context["history_summary"] = {
                "total_tasks": session.task_count,
                "recent_topics": [],  # Could be populated from memory
            }
        
        # Analyze intent and complexity for trigger determination
        intent_analysis = self._analyze_intent(request.message)
        complexity_score = self._calculate_complexity(request.message)
        
        # Build constraints
        constraints = [
            "Focus on user intent, not implementation details",
            "Decompose complex requests into discrete processes",
            "Identify required capabilities early",
            "Flag security-sensitive operations",
            "Maintain session continuity across processes",
        ]
        
        # Create compiled context
        compiled = CompiledContext(
            task_id=f"prime_compile_{request.id}",
            session_context={
                "request": request_context,
                "session": session_context,
                "additional": additional_context or {},
                "analysis": {
                    "intent": intent_analysis,
                    "complexity_score": complexity_score,
                },
            },
            task_goal="Compile context for Prime Personality",
            constraints=constraints,
            allowed_capabilities=["fs-skill", "prime-compiler-skill"],
            forbidden_capabilities=["write", "delete", "execute"],
            memory_references=[],
            metadata={
                "compilation_rules": self._get_compilation_rules(),
                "rule_based": True,
            },
        )
        
        self.logger.debug(
            "Rule-based compilation complete",
            request_id=request.id,
            complexity_score=complexity_score,
        )
        
        return compiled
    
    def _determine_trigger_reason(
        self,
        request: Request,
        base_context: CompiledContext,
    ) -> str | None:
        """
        Determine if agent assistance should be triggered.
        
        Args:
            request: User request
            base_context: Base compiled context with analysis
            
        Returns:
            Trigger reason string, or None if no trigger
        """
        analysis = base_context.session_context.get("analysis", {})
        
        # Rule 1: Low intent confidence
        intent_analysis = analysis.get("intent", {})
        confidence = intent_analysis.get("confidence", 1.0)
        if confidence < self.config.intent_confidence_threshold:
            return f"low_intent_confidence ({confidence:.2f} < {self.config.intent_confidence_threshold})"
        
        # Rule 2: Cross-session query keywords
        cross_session_keywords = [
            "previous", "last time", "before", "earlier",
            "之前的", "上次", "以前", "刚才", "之前",
        ]
        message_lower = request.message.lower()
        for keyword in cross_session_keywords:
            if keyword in message_lower:
                return f"cross_session_keyword ('{keyword}' detected)"
        
        # Rule 3: High complexity
        complexity_score = analysis.get("complexity_score", 0)
        if complexity_score > self.config.complexity_threshold:
            return f"high_complexity ({complexity_score:.2f} > {self.config.complexity_threshold})"
        
        # Rule 4: Multi-part requests (heuristic: length and structure)
        if len(request.message) > 200 and any(
            marker in message_lower 
            for marker in ["and then", "also", "next", "after that", "然后", "接着", "还有"]
        ):
            return "multi_part_request"
        
        return None
    
    def _apply_context_patch(
        self,
        base_context: CompiledContext,
        patch,
    ) -> CompiledContext:
        """
        Apply Context Patch to base CompiledContext.
        
        Args:
            base_context: Base compiled context
            patch: ContextPatch from agent
            
        Returns:
            Enhanced CompiledContext
        """
        # Add artifacts to session context
        if patch.artifacts:
            base_context.session_context["gathered_artifacts"] = [
                {
                    "slot_type": a.slot_type,
                    "content": a.content,
                    "priority": a.priority,
                }
                for a in patch.artifacts
            ]
        
        # Add files read
        if patch.files_read:
            base_context.session_context["files_explored"] = patch.files_read
        
        # Update metadata
        base_context.metadata.update({
            "rule_based": False,
            "agent_assisted": True,
            "patch_status": patch.status,
            "patch_confidence": patch.confidence,
            "patch_steps": patch.steps_used,
            "patch_reasoning": patch.reasoning,
        })
        
        return base_context
    
    def _analyze_intent(self, message: str) -> dict[str, Any]:
        """
        Analyze user intent using simple heuristics.
        
        Args:
            message: User message
            
        Returns:
            Intent analysis dict
        """
        message_lower = message.lower().strip()
        
        # Simple keyword-based intent detection
        intents = []
        confidence = 1.0
        
        # Greeting/Social intents - high confidence, no exploration needed
        greeting_keywords = [
            "hello", "hi", "hey", "greetings", 
            "你好", "您好", "嗨", "哈喽",
            "introduce", "介绍", "自己", "你是谁", "你是什么",
        ]
        if any(kw in message_lower for kw in greeting_keywords):
            intents.append("greeting")
            confidence = 0.9  # High confidence for greetings
        
        # Query intents
        if any(kw in message_lower for kw in ["what", "how", "why", "where", "when", "who", "什么", "怎么", "为什么", "哪里"]):
            intents.append("query")
        
        # Action intents
        if any(kw in message_lower for kw in ["do", "make", "create", "run", "execute", "做", "创建", "运行", "执行"]):
            intents.append("action")
        
        # File intents
        if any(kw in message_lower for kw in ["file", "document", "read", "write", "文件", "文档", "读取", "写入"]):
            intents.append("file_operation")
        
        # Ambiguous if no clear intent detected
        if not intents:
            intents.append("ambiguous")
            confidence = 0.5
        elif len(intents) > 2:
            confidence = 0.7  # Multiple intents reduce confidence
        
        return {
            "detected_intents": intents,
            "confidence": confidence,
            "primary_intent": intents[0] if intents else "unknown",
        }
    
    def _calculate_complexity(self, message: str) -> float:
        """
        Calculate request complexity score (0.0-1.0).
        
        Args:
            message: User message
            
        Returns:
            Complexity score
        """
        score = 0.0
        
        # Length factor
        if len(message) > 500:
            score += 0.3
        elif len(message) > 200:
            score += 0.15
        
        # Multi-part indicators
        multi_part_markers = ["and then", "also", "next", "after that", "additionally", " moreover",
                             "然后", "接着", "还有", "另外", "此外"]
        for marker in multi_part_markers:
            if marker in message.lower():
                score += 0.1
        
        # Conditional indicators
        conditional_markers = ["if", "when", "unless", "depending", "based on",
                              "如果", "当", "除非", "根据"]
        for marker in conditional_markers:
            if marker in message.lower():
                score += 0.1
        
        # Technical terms
        technical_terms = ["api", "database", "server", "config", "deploy", "script",
                          "api", "数据库", "服务器", "配置", "部署", "脚本"]
        for term in technical_terms:
            if term in message.lower():
                score += 0.05
        
        return min(score, 1.0)
    
    def _compute_cache_key(self, request: Request, session: Session) -> str:
        """Compute cache key for request pattern."""
        # Use message hash + session context
        content = f"{session.id}:{request.message}"
        return hashlib.md5(content.encode()).hexdigest()[:16]
    
    def _get_cached_patch(self, cache_key: str):
        """Get cached patch if still valid."""
        if cache_key not in self._exploration_cache:
            return None
        
        timestamp, patch = self._exploration_cache[cache_key]
        age = time.time() - timestamp
        
        if age > self.config.cache_ttl_seconds:
            # Expired
            del self._exploration_cache[cache_key]
            return None
        
        return patch
    
    def _cache_patch(self, cache_key: str, patch) -> None:
        """Cache exploration patch."""
        self._exploration_cache[cache_key] = (time.time(), patch)
        
        # Simple cache cleanup (remove oldest entries if too many)
        if len(self._exploration_cache) > 100:
            oldest_key = min(
                self._exploration_cache.keys(),
                key=lambda k: self._exploration_cache[k][0],
            )
            del self._exploration_cache[oldest_key]
    
    def _save_rule_only_summary(
        self,
        request: Request,
        session: Session,
        start_time: float,
    ) -> None:
        """Save summary for rule-only compilation."""
        try:
            from context_compiler.models import PrimeCompilationSummary
            from pathlib import Path
            
            storage_dir = Path(f"{self.config.storage_base_path}/{request.id}")
            storage_dir.mkdir(parents=True, exist_ok=True)
            
            summary = PrimeCompilationSummary(
                request_id=request.id,
                session_id=session.id,
                triggered_agent=False,
                steps_used=0,
                max_steps=self.config.max_steps,
                files_read=[],
                artifacts_gathered=0,
                duration_ms=int((time.time() - start_time) * 1000),
                status="success",
                trigger_reason="Rule-based compilation sufficient",
            )
            
            import json
            summary_path = storage_dir / "summary.json"
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary.model_dump(), f, indent=2, default=str)
        
        except Exception as e:
            self.logger.warning("Failed to save rule-only summary", error=str(e))
    
    def _get_compilation_rules(self) -> list[str]:
        """Get compilation rules for documentation."""
        return [
            "Focus on user intent, not implementation details",
            "Decompose complex requests into discrete processes",
            "Identify required capabilities early",
            "Flag security-sensitive operations",
            "Prioritize user safety and system integrity",
            "Maintain session continuity across processes",
        ]
    
    def get_audit_summary(self, request_id: str) -> dict | None:
        """
        Get audit summary for a request.
        
        Args:
            request_id: Request identifier
            
        Returns:
            Summary dict or None
        """
        summary = self.auditor.get_summary(request_id)
        if summary:
            return summary.model_dump()
        return None
    
    def clear_cache(self) -> None:
        """Clear exploration cache."""
        self._exploration_cache.clear()
        self.logger.info("Exploration cache cleared")


# Singleton instance
_master_compiler: MasterContextCompiler | None = None


def get_master_compiler(config: PrimeCompilerConfig | None = None) -> MasterContextCompiler:
    """Get or create singleton instance."""
    global _master_compiler
    if _master_compiler is None:
        _master_compiler = MasterContextCompiler(config)
    return _master_compiler


def reset_master_compiler() -> None:
    """Reset singleton instance (useful for testing)."""
    global _master_compiler
    _master_compiler = None