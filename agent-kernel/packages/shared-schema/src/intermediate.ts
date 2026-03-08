/**
 * Intermediate Representation from Prime Personality
 */
export interface IntermediateRepresentation {
  request_id: string;
  intent: string;
  goals: string[];
  processes: ProcessDefinition[];
  context_hints: Record<string, unknown>;
}

/**
 * Process definition within IR
 */
export interface ProcessDefinition {
  name: string;
  goal: string;
  capabilities: string[];
  forbidden_capabilities?: string[];
  constraints?: string[];
  security_level?: 'low' | 'medium' | 'high';
  dependencies?: string[];
}

/**
 * Compiled context for Agent execution
 */
export interface CompiledContext {
  task_id: string;
  session_context: Record<string, unknown>;
  task_goal: string;
  constraints: string[];
  allowed_capabilities: string[];
  forbidden_capabilities: string[];
  memory_references: string[];
  compiled_at: string;
}

/**
 * Agent output type
 */
export interface AgentOutput {
  task_id: string;
  content: string;
  tool_calls: ToolCall[];
  observations: Observation[];
  success: boolean;
  error?: string;
  created_at: string;
}

/**
 * Tool call within Agent output
 */
export interface ToolCall {
  skill: string;
  tool: string;
  parameters: Record<string, unknown>;
  request_id?: string;
}

/**
 * Observation from tool execution
 */
export interface Observation {
  tool: string;
  success: boolean;
  result?: unknown;
  error?: string;
}
