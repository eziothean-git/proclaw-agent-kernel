import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { RequestTask } from '../interfaces';
import { AuditLoggerService } from './audit-logger.service';
import { PriorityQueueService } from './priority-queue.service';
import { GrpcError, MaxRetriesExceededException } from '../exceptions';
import { RETRYABLE_GRPC_CODES, PRIORITY_NAMES } from '../constants';

@Injectable()
export class RetryHandlerService {
  private readonly logger = new Logger(RetryHandlerService.name);
  private readonly maxRetries: number;
  private readonly initialDelayMs: number;
  private readonly maxDelayMs: number;
  private readonly backoffMultiplier: number;

  // Metrics
  private totalRetried = 0;

  constructor(
    private readonly configService: ConfigService,
    private readonly auditLogger: AuditLoggerService,
    private readonly priorityQueue: PriorityQueueService,
  ) {
    this.maxRetries = this.configService.get<number>('MAX_RETRIES', 3);
    this.initialDelayMs = this.configService.get<number>('RETRY_DELAY_BASE_MS', 1000);
    this.maxDelayMs = this.configService.get<number>('RETRY_DELAY_MAX_MS', 30000);
    this.backoffMultiplier = this.configService.get<number>('BACKOFF_MULTIPLIER', 2);
  }

  async shouldRetry(task: RequestTask, error: Error): Promise<boolean> {
    // 检查是否超过最大重试次数
    if (task.retryCount >= this.maxRetries) {
      await this.auditLogger.logMaxRetriesExceeded(
        task.requestId,
        task.sessionId,
        task.retryCount
      );
      return false;
    }

    // 检查错误是否可恢复
    const isRecoverable = this.isRecoverableError(error);
    if (!isRecoverable) {
      this.logger.warn(
        `Request ${task.requestId} failed with non-recoverable error: ${error.message}`
      );
      return false;
    }

    // 计算下次重试延迟
    const delayMs = this.calculateRetryDelay(task.retryCount);

    await this.auditLogger.logRetryScheduled(
      task.requestId,
      task.sessionId,
      task.retryCount + 1,
      delayMs
    );

    this.logger.log(
      `Request ${task.requestId} (P${PRIORITY_NAMES[task.priority]}) scheduled for retry ${task.retryCount + 1}/${this.maxRetries} in ${delayMs}ms`
    );

    // 延迟后重新入队
    setTimeout(async () => {
      task.retryCount++;
      task.status = 6; // RETRYING
      task.createdAt = new Date(); // 重置创建时间
      task.timeoutAt = new Date(Date.now() + this.getTimeoutMs(task.priority));
      await this.priorityQueue.enqueue(task);
      this.totalRetried++;
    }, delayMs);

    return true;
  }

  async retryManually(
    task: RequestTask,
    resetRetryCount = false,
    newPriority?: number
  ): Promise<void> {
    if (resetRetryCount) {
      task.retryCount = 0;
    }

    if (newPriority !== undefined) {
      task.priority = newPriority as typeof task.priority;
      task.timeoutAt = new Date(Date.now() + this.getTimeoutMs(newPriority));
    }

    task.createdAt = new Date();
    task.status = 1; // QUEUED

    await this.auditLogger.logManualRetry(
      task.requestId,
      task.sessionId,
      resetRetryCount,
      newPriority
    );

    await this.priorityQueue.enqueue(task);
    
    this.logger.log(
      `Request ${task.requestId} manually retried (resetCount: ${resetRetryCount}, newPriority: ${newPriority})`
    );
  }

  private isRecoverableError(error: Error): boolean {
    if (error instanceof GrpcError) {
      return RETRYABLE_GRPC_CODES.includes(error.code);
    }

    // 网络错误通常可重试
    const networkErrors = [
      'ECONNREFUSED',
      'ETIMEDOUT',
      'ECONNRESET',
      'EPIPE',
      'NETWORK_ERROR',
    ];
    
    return networkErrors.some(code => error.message.includes(code));
  }

  private calculateRetryDelay(retryCount: number): number {
    const delay = this.initialDelayMs * Math.pow(this.backoffMultiplier, retryCount);
    return Math.min(delay, this.maxDelayMs);
  }

  private getTimeoutMs(priority: number): number {
    const timeouts: Record<number, number> = {
      100: this.configService.get<number>('TIMEOUT_P0_MS', 30000),
      50: this.configService.get<number>('TIMEOUT_P1_MS', 120000),
      10: this.configService.get<number>('TIMEOUT_P2_MS', 60000),
      0: this.configService.get<number>('TIMEOUT_P3_MS', 120000),
      [-10]: this.configService.get<number>('TIMEOUT_P4_MS', 300000),
    };
    return timeouts[priority] || 120000;
  }

  getTotalRetried(): number {
    return this.totalRetried;
  }
}