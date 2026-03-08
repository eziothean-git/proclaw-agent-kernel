/**
 * MCP (Model Context Protocol) integration types and standards
 */

/**
 * Standard tool result format
 * All skills should return results in this format
 */
export interface ToolResult<T = unknown> {
  success: boolean;
  data?: T;
  error?: ToolError;
  metadata?: ToolResultMetadata;
}

/**
 * Tool error details
 */
export interface ToolError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

/**
 * Tool result metadata
 */
export interface ToolResultMetadata {
  execution_time_ms: number;
  timestamp: string;
  tool_name: string;
  skill_name: string;
}

/**
 * Skill manifest definition
 */
export interface SkillManifest {
  name: string;
  version: string;
  description: string;
  author?: string;
  tools: ToolDefinition[];
  required_permissions?: string[];
}

/**
 * Tool definition in skill manifest
 */
export interface ToolDefinition {
  name: string;
  description: string;
  parameters: JSONSchema;
  returns?: JSONSchema;
  examples?: ToolExample[];
}

/**
 * JSON Schema type for parameters/returns
 */
export interface JSONSchema {
  type: 'object' | 'array' | 'string' | 'number' | 'boolean';
  properties?: Record<string, JSONSchema>;
  required?: string[];
  items?: JSONSchema;
  enum?: unknown[];
  description?: string;
}

/**
 * Tool usage example
 */
export interface ToolExample {
  description: string;
  input: Record<string, unknown>;
  output: ToolResult;
}

/**
 * Standard tool categories
 */
export enum ToolCategory {
  FILE_SYSTEM = 'filesystem',
  SHELL = 'shell',
  NETWORK = 'network',
  DATABASE = 'database',
  AI_MODEL = 'ai_model',
  CUSTOM = 'custom',
}

/**
 * Tool call request format
 */
export interface ToolCallRequest {
  tool: string;
  parameters: Record<string, unknown>;
  request_id: string;
  timeout?: number;
}

/**
 * Capability descriptor
 */
export interface Capability {
  name: string;
  category: ToolCategory;
  description: string;
  dangerous: boolean;
  requires_confirmation: boolean;
}
