/**
 * Observability standards and telemetry conventions
 */

/**
 * Standard attribute names for OpenTelemetry spans
 */
export const SpanAttributes = {
  // System attributes
  SYSTEM_COMPONENT: 'system.component',
  SYSTEM_LAYER: 'system.layer',
  
  // Request attributes
  REQUEST_ID: 'request.id',
  SESSION_ID: 'session.id',
  USER_ID: 'user.id',
  REQUEST_MESSAGE: 'request.message',
  
  // Task attributes
  TASK_ID: 'task.id',
  TASK_STATUS: 'task.status',
  TASK_GOAL: 'task.goal',
  
  // Process attributes
  PROCESS_ID: 'process.id',
  PROCESS_NAME: 'process.name',
  
  // Tool attributes
  SKILL_NAME: 'skill.name',
  TOOL_NAME: 'tool.name',
  TOOL_SUCCESS: 'tool.success',
  TOOL_EXECUTION_TIME: 'tool.execution_time_ms',
  
  // Error attributes
  ERROR_TYPE: 'error.type',
  ERROR_MESSAGE: 'error.message',
  ERROR_STACK: 'error.stack',
} as const;

/**
 * System layers for tracing
 */
export enum SystemLayer {
  GATEWAY = 'gateway',
  PYTHON_KERNEL = 'python_kernel',
  SKILL = 'skill',
}

/**
 * Standard log levels
 */
export enum LogLevel {
  DEBUG = 'debug',
  INFO = 'info',
  WARN = 'warn',
  ERROR = 'error',
}

/**
 * Standard event names
 */
export const EventNames = {
  // Request lifecycle
  REQUEST_RECEIVED: 'request.received',
  REQUEST_QUEUED: 'request.queued',
  REQUEST_PROCESSING: 'request.processing',
  REQUEST_COMPLETED: 'request.completed',
  REQUEST_FAILED: 'request.failed',
  
  // Task lifecycle
  TASK_CREATED: 'task.created',
  TASK_STARTED: 'task.started',
  TASK_COMPLETED: 'task.completed',
  TASK_FAILED: 'task.failed',
  
  // Tool execution
  TOOL_CALLED: 'tool.called',
  TOOL_SUCCEEDED: 'tool.succeeded',
  TOOL_FAILED: 'tool.failed',
  
  // Context compilation
  CONTEXT_COMPILING: 'context.compiling',
  CONTEXT_COMPILED: 'context.compiled',
} as const;

/**
 * Metrics names
 */
export const Metrics = {
  // Request metrics
  REQUESTS_TOTAL: 'requests.total',
  REQUESTS_ACTIVE: 'requests.active',
  REQUEST_DURATION: 'request.duration_ms',
  
  // Task metrics
  TASKS_TOTAL: 'tasks.total',
  TASKS_ACTIVE: 'tasks.active',
  TASK_DURATION: 'task.duration_ms',
  
  // Queue metrics
  QUEUE_SIZE: 'queue.size',
  QUEUE_WAIT_TIME: 'queue.wait_time_ms',
  
  // Tool metrics
  TOOL_CALLS_TOTAL: 'tool_calls.total',
  TOOL_CALL_DURATION: 'tool_call.duration_ms',
  
  // Resource metrics
  MEMORY_USAGE: 'memory.usage_bytes',
  CPU_USAGE: 'cpu.usage_percent',
} as const;

/**
 * Context propagation keys
 */
export const ContextKeys = {
  REQUEST_ID: 'x-request-id',
  SESSION_ID: 'x-session-id',
  TRACE_ID: 'x-trace-id',
} as const;

/**
 * Health check statuses
 */
export enum HealthStatus {
  HEALTHY = 'healthy',
  DEGRADED = 'degraded',
  UNHEALTHY = 'unhealthy',
}
