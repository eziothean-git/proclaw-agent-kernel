import { PriorityLevel, RequestStatus } from '../constants';

export interface RequestTask {
  requestId: string;
  sessionId: string;
  userId: string;
  priority: PriorityLevel;
  body: string;
  metadata: Record<string, string>;
  retryCount: number;
  status: RequestStatus;
  createdAt: Date;
  startedAt?: Date;
  completedAt?: Date;
  timeoutAt: Date;
  progress: number;
  errorMessage?: string;
}

export interface WorkerState {
  taskId: string;
  sessionId: string;
  startTime: Date;
  timeoutAt: Date;
  retryCount: number;
}

export interface AuditLogEntry {
  version: string;
  timestamp: string;
  requestId: string;
  sessionId: string;
  eventType: string;
  context: {
    priority: number;
    retryCount: number;
    queuePosition?: number;
    workerId?: string;
    sessionQueuePosition?: number;
    errorCategory?: string;
    nextRetryDelayMs?: number;
    timeoutMs?: number;
  };
  metadata?: Record<string, unknown>;
}

export interface ProcessResult {
  content: string;
  actions: Array<{
    type: string;
    skill?: string;
    tool?: string;
    status: string;
    durationMs?: number;
    result?: string;
  }>;
  metrics?: {
    totalDurationMs?: number;
    tokenCountInput?: number;
    tokenCountOutput?: number;
    modelVersion?: string;
    llmCallsCount?: number;
  };
}

export interface QueueMetrics {
  totalSize: number;
  byPriority: Record<number, number>;
  waitingSessions: number;
}

export interface WorkerPoolMetrics {
  maxWorkers: number;
  activeWorkers: number;
  availableSlots: number;
  activeTasks: WorkerState[];
}

export interface RequestManagerMetrics {
  queue: QueueMetrics;
  workers: WorkerPoolMetrics;
  totalProcessed: number;
  totalFailed: number;
  totalRetried: number;
  totalTimedOut: number;
  totalRejected: number;
  totalCancelled: number;
}

export interface InboxEntry {
  requestId: string;
  sessionId: string;
  userId: string;
  priority: number;
  body: string;
  metadata: Record<string, string>;
  receivedAt: string;
  filePath: string;
}

export interface StateSnapshot {
  timestamp: string;
  requests: Array<{
    requestId: string;
    status: RequestStatus;
    priority: number;
    sessionId: string;
    createdAt: string;
    retryCount: number;
  }>;
}