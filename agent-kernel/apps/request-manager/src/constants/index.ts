export const PRIORITY_LEVELS = {
  P0_EMERGENCY: 100,
  P1_SCHEDULED: 50,
  P2_HIGH: 10,
  P3_NORMAL: 0,
  P4_BACKGROUND: -10,
} as const;

export type PriorityLevel = typeof PRIORITY_LEVELS[keyof typeof PRIORITY_LEVELS];

export const PRIORITY_NAMES: Record<number, string> = {
  100: 'P0_EMERGENCY',
  50: 'P1_SCHEDULED',
  10: 'P2_HIGH',
  0: 'P3_NORMAL',
  [-10]: 'P4_BACKGROUND',
};

// gRPC Status Codes
export const GRPC_STATUS_CODES = {
  OK: 0,
  CANCELLED: 1,
  UNKNOWN: 2,
  INVALID_ARGUMENT: 3,
  DEADLINE_EXCEEDED: 4,
  NOT_FOUND: 5,
  ALREADY_EXISTS: 6,
  PERMISSION_DENIED: 7,
  RESOURCE_EXHAUSTED: 8,
  FAILED_PRECONDITION: 9,
  ABORTED: 10,
  OUT_OF_RANGE: 11,
  UNIMPLEMENTED: 12,
  INTERNAL: 13,
  UNAVAILABLE: 14,
  DATA_LOSS: 15,
  UNAUTHENTICATED: 16,
} as const;

// 可重试的 gRPC 错误码
export const RETRYABLE_GRPC_CODES: number[] = [
  GRPC_STATUS_CODES.DEADLINE_EXCEEDED,
  GRPC_STATUS_CODES.RESOURCE_EXHAUSTED,
  GRPC_STATUS_CODES.ABORTED,
  GRPC_STATUS_CODES.UNAVAILABLE,
];

export const DEFAULT_CONFIG = {
  // 并发配置
  MAX_CONCURRENT_REQUESTS: 5,
  MAX_QUEUE_SIZE: 1000,

  // 超时配置（按优先级）
  TIMEOUT_P0_MS: 30000,
  TIMEOUT_P1_MS: 120000,
  TIMEOUT_P2_MS: 60000,
  TIMEOUT_P3_MS: 120000,
  TIMEOUT_P4_MS: 300000,

  // 重试配置
  MAX_RETRIES: 3,
  RETRY_DELAY_BASE_MS: 1000,
  RETRY_DELAY_MAX_MS: 30000,
  BACKOFF_MULTIPLIER: 2,

  // 存储路径
  STORAGE_BASE_PATH: '/var/gateway/request-manager',
  INBOX_PATH: '/var/gateway/request-manager/inbox',
  AUDIT_PATH: '/var/gateway/request-manager/audit',
  STATE_PATH: '/var/gateway/request-manager/state',

  // gRPC 配置
  REQUEST_MANAGER_GRPC_PORT: 50052,
  PRIME_PERSONALITY_GRPC_URL: 'localhost:50051',

  // 轮询间隔
  SCHEDULER_INTERVAL_MS: 100,
} as const;

export const EVENT_TYPES = {
  REQUEST_RECEIVED: 'request_received',
  REQUEST_QUEUED: 'request_queued',
  REQUEST_STARTED: 'request_started',
  PRIME_PERSONALITY_CALLED: 'prime_personality_called',
  PRIME_PERSONALITY_COMPLETED: 'prime_personality_completed',
  PRIME_PERSONALITY_FAILED: 'prime_personality_failed',
  REQUEST_COMPLETED: 'request_completed',
  REQUEST_FAILED: 'request_failed',
  REQUEST_CANCELLED: 'request_cancelled',
  RETRY_SCHEDULED: 'retry_scheduled',
  MAX_RETRIES_EXCEEDED: 'max_retries_exceeded',
  TIMEOUT_TRIGGERED: 'timeout_triggered',
  QUEUE_FULL_REJECTED: 'queue_full_rejected',
  SESSION_QUEUED: 'session_queued',
  MANUAL_RETRY: 'manual_retry',
  STATUS_QUERIED: 'status_queried',
  CANCEL_REQUESTED: 'cancel_requested',
} as const;

export type EventType = typeof EVENT_TYPES[keyof typeof EVENT_TYPES];

export const REQUEST_STATUS = {
  UNKNOWN: 0,
  QUEUED: 1,
  PROCESSING: 2,
  COMPLETED: 3,
  FAILED: 4,
  CANCELLED: 5,
  RETRYING: 6,
} as const;

export type RequestStatus = typeof REQUEST_STATUS[keyof typeof REQUEST_STATUS];