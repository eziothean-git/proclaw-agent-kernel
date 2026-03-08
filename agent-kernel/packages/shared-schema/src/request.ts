/**
 * User request type matching Python Request model
 */
export interface Request {
  id: string;
  session_id: string;
  user_id: string;
  message: string;
  status: RequestStatus;
  created_at: string;
  processed_at?: string;
  completed_at?: string;
  metadata?: Record<string, unknown>;
}

export enum RequestStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled',
}

/**
 * Session state type matching Python Session model
 */
export interface Session {
  id: string;
  user_id: string;
  status: string;
  created_at: string;
  last_activity: string;
  task_count: number;
  active_processes: string[];
  metadata?: Record<string, unknown>;
}

/**
 * Tool call request type
 */
export interface ToolCallRequest {
  request_id: string;
  session_id: string;
  skill_name: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  timeout: number;
}

/**
 * Tool call result type
 */
export interface ToolCallResult {
  request_id: string;
  success: boolean;
  result?: unknown;
  error?: string;
  execution_time_ms: number;
}

/**
 * Health check response
 */
export interface HealthCheck {
  status: string;
  version: string;
  timestamp: string;
  components: Record<string, string>;
}

/**
 * Chat request DTO
 */
export interface ChatRequestDto {
  sessionId?: string;
  message: string;
  userId: string;
  metadata?: Record<string, unknown>;
}

/**
 * Chat response DTO
 */
export interface ChatResponseDto {
  requestId: string;
  sessionId: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  timestamp: string;
}
