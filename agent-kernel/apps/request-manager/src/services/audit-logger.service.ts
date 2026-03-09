import { Injectable } from '@nestjs/common';
import { PersistenceService } from './persistence.service';
import { AuditLogEntry } from '../interfaces';

@Injectable()
export class AuditLoggerService {
  constructor(private readonly persistenceService: PersistenceService) {}

  async log(entry: Partial<AuditLogEntry>): Promise<void> {
    const fullEntry: AuditLogEntry = {
      version: '1.0',
      timestamp: new Date().toISOString(),
      requestId: entry.requestId || 'unknown',
      sessionId: entry.sessionId || 'unknown',
      eventType: entry.eventType || 'unknown',
      context: entry.context || {
        priority: 0,
        retryCount: 0,
      },
      ...(entry.metadata && { metadata: entry.metadata }),
    };

    await this.persistenceService.writeAuditLog(fullEntry);
  }

  async logRequestReceived(
    requestId: string,
    sessionId: string,
    priority: number,
    metadata?: Record<string, unknown>
  ): Promise<void> {
    await this.log({
      eventType: 'request_received',
      requestId,
      sessionId,
      context: {
        priority,
        retryCount: 0,
      },
      metadata,
    });
  }

  async logRequestQueued(
    requestId: string,
    sessionId: string,
    priority: number,
    queuePosition: number,
    retryCount: number
  ): Promise<void> {
    await this.log({
      eventType: 'request_queued',
      requestId,
      sessionId,
      context: {
        priority,
        retryCount,
        queuePosition,
      },
    });
  }

  async logRequestStarted(
    requestId: string,
    sessionId: string,
    priority: number,
    retryCount: number
  ): Promise<void> {
    await this.log({
      eventType: 'request_started',
      requestId,
      sessionId,
      context: {
        priority,
        retryCount,
      },
    });
  }

  async logPrimePersonalityCalled(
    requestId: string,
    sessionId: string,
    timeoutMs: number
  ): Promise<void> {
    await this.log({
      eventType: 'prime_personality_called',
      requestId,
      sessionId,
      context: {
        priority: 0,
        retryCount: 0,
        timeoutMs,
      },
    });
  }

  async logPrimePersonalityCompleted(
    requestId: string,
    sessionId: string,
    durationMs: number
  ): Promise<void> {
    await this.log({
      eventType: 'prime_personality_completed',
      requestId,
      sessionId,
      context: {
        priority: 0,
        retryCount: 0,
      },
      metadata: {
        durationMs,
      },
    });
  }

  async logPrimePersonalityFailed(
    requestId: string,
    sessionId: string,
    errorCategory: string,
    errorMessage: string,
    recoverable: boolean
  ): Promise<void> {
    await this.log({
      eventType: 'prime_personality_failed',
      requestId,
      sessionId,
      context: {
        priority: 0,
        retryCount: 0,
        errorCategory,
      },
      metadata: {
        errorMessage,
        recoverable,
      },
    });
  }

  async logRequestCompleted(
    requestId: string,
    sessionId: string,
    durationMs: number,
    totalDurationMs: number
  ): Promise<void> {
    await this.log({
      eventType: 'request_completed',
      requestId,
      sessionId,
      context: {
        priority: 0,
        retryCount: 0,
      },
      metadata: {
        processingTimeMs: durationMs,
        totalTimeMs: totalDurationMs,
      },
    });
  }

  async logRequestFailed(
    requestId: string,
    sessionId: string,
    errorMessage: string
  ): Promise<void> {
    await this.log({
      eventType: 'request_failed',
      requestId,
      sessionId,
      context: {
        priority: 0,
        retryCount: 0,
      },
      metadata: {
        errorMessage,
      },
    });
  }

  async logRetryScheduled(
    requestId: string,
    sessionId: string,
    retryCount: number,
    nextRetryDelayMs: number
  ): Promise<void> {
    await this.log({
      eventType: 'retry_scheduled',
      requestId,
      sessionId,
      context: {
        priority: 0,
        retryCount,
        nextRetryDelayMs,
      },
    });
  }

  async logMaxRetriesExceeded(
    requestId: string,
    sessionId: string,
    totalRetries: number
  ): Promise<void> {
    await this.log({
      eventType: 'max_retries_exceeded',
      requestId,
      sessionId,
      context: {
        priority: 0,
        retryCount: totalRetries,
      },
    });
  }

  async logTimeoutTriggered(
    requestId: string,
    sessionId: string
  ): Promise<void> {
    await this.log({
      eventType: 'timeout_triggered',
      requestId,
      sessionId,
      context: {
        priority: 0,
        retryCount: 0,
      },
    });
  }

  async logQueueFullRejected(
    requestId: string,
    sessionId: string,
    priority: number
  ): Promise<void> {
    await this.log({
      eventType: 'queue_full_rejected',
      requestId,
      sessionId,
      context: {
        priority,
        retryCount: 0,
      },
    });
  }

  async logSessionQueued(
    requestId: string,
    sessionId: string,
    priority: number,
    sessionQueuePosition: number
  ): Promise<void> {
    await this.log({
      eventType: 'session_queued',
      requestId,
      sessionId,
      context: {
        priority,
        retryCount: 0,
        sessionQueuePosition,
      },
    });
  }

  async logManualRetry(
    requestId: string,
    sessionId: string,
    resetRetryCount: boolean,
    newPriority?: number
  ): Promise<void> {
    await this.log({
      eventType: 'manual_retry',
      requestId,
      sessionId,
      context: {
        priority: newPriority || 0,
        retryCount: 0,
      },
      metadata: {
        resetRetryCount,
        newPriority,
      },
    });
  }
}