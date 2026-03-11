import { Injectable, Logger, OnModuleInit, OnApplicationShutdown } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { PriorityQueueService } from './priority-queue.service';
import { WorkerPoolService } from './worker-pool.service';
import { SessionAffinityService } from './session-affinity.service';
import { RetryHandlerService } from './retry-handler.service';
import { AuditLoggerService } from './audit-logger.service';
import { PersistenceService } from './persistence.service';
import { RequestStateService } from './request-state.service';
import { RequestTask, ProcessResult } from '../interfaces';
import { GrpcError, TimeoutException } from '../exceptions';
import { PRIORITY_NAMES } from '../constants';

// Callback type for task dispatch via gRPC stream
type TaskDispatchCallback = (task: RequestTask) => Promise<boolean>;

/**
 * Ensure value is a Date object.
 * Handles cases where Date was serialized to string (e.g., from storage).
 */
function ensureDate(value: Date | string | undefined): Date | undefined {
  if (!value) {
    return undefined;
  }
  if (value instanceof Date) {
    return value;
  }
  // Handle ISO string or other date string formats
  if (typeof value === 'string') {
    const parsed = new Date(value);
    return isNaN(parsed.getTime()) ? undefined : parsed;
  }
  return undefined;
}

@Injectable()
export class PriorityRequestManagerService implements OnModuleInit, OnApplicationShutdown {
  private readonly logger = new Logger(PriorityRequestManagerService.name);
  private isRunning = false;
  private schedulerIntervalMs: number;
  private taskDispatchCallback: TaskDispatchCallback | null = null;

  constructor(
    private readonly configService: ConfigService,
    private readonly priorityQueue: PriorityQueueService,
    private readonly workerPool: WorkerPoolService,
    private readonly sessionAffinity: SessionAffinityService,
    private readonly retryHandler: RetryHandlerService,
    private readonly auditLogger: AuditLoggerService,
    private readonly persistenceService: PersistenceService,
    private readonly requestState: RequestStateService,
  ) {
    this.schedulerIntervalMs = this.configService.get<number>('SCHEDULER_INTERVAL_MS', 100);
  }

  /**
   * Set the callback for dispatching tasks via gRPC stream.
   * This is called by RequestManagerGrpcServer to inject the gRPC dispatch function.
   */
  setTaskDispatchCallback(callback: TaskDispatchCallback): void {
    this.taskDispatchCallback = callback;
    this.logger.log('Task dispatch callback registered');
  }

  async onModuleInit(): Promise<void> {
    this.start();
  }

  async onApplicationShutdown(): Promise<void> {
    await this.stop();
  }

  start(): void {
    if (this.isRunning) {
      return;
    }

    this.isRunning = true;
    this.logger.log('Priority Request Manager scheduler started');
    this.schedulerLoop();
  }

  async stop(): Promise<void> {
    this.isRunning = false;
    await this.workerPool.gracefulShutdown();
    this.logger.log('Priority Request Manager scheduler stopped');
  }

  private async schedulerLoop(): Promise<void> {
    while (this.isRunning) {
      try {
        await this.schedule();
      } catch (error) {
        this.logger.error(`Scheduler error: ${error.message}`);
      }

      await new Promise(resolve => setTimeout(resolve, this.schedulerIntervalMs));
    }
  }

  private async schedule(): Promise<void> {
    // 检查是否有可用的 worker
    if (this.workerPool.getAvailableSlots() <= 0) {
      return;
    }

    // 从队列中获取任务
    const task = await this.priorityQueue.dequeue();
    if (!task) {
      return;
    }

    // 尝试获取 worker 槽位
    const acquired = await this.workerPool.acquireSlot(task);
    if (!acquired) {
      // 回退到队列
      await this.priorityQueue.enqueue(task);
      return;
    }

    // 异步处理任务
    this.processTask(task).catch(error => {
      this.logger.error(`Unhandled error in task processing: ${error.message}`);
    });
  }

  private async processTask(task: RequestTask): Promise<void> {
    try {
      // Check if gRPC dispatch callback is available
      if (!this.taskDispatchCallback) {
        this.logger.warn(`No gRPC dispatch callback registered for task ${task.requestId}`);
        // Release slot and requeue task
        await this.workerPool.releaseSlot(task.requestId);
        await this.priorityQueue.enqueue(task);
        return;
      }

      // Dispatch task via gRPC stream
      const dispatched = await this.taskDispatchCallback(task);
      
      if (!dispatched) {
        this.logger.warn(`Failed to dispatch task ${task.requestId} via gRPC stream`);
        // Release slot and requeue task
        await this.workerPool.releaseSlot(task.requestId);
        await this.priorityQueue.enqueue(task);
        return;
      }

      // Task successfully dispatched, update state
      this.logger.log(`Task ${task.requestId} dispatched via gRPC stream`);
      this.requestState.update(task.requestId, {
        status: 2, // PROCESSING
        progress: 10,
        startedAt: new Date(),
      });

      await this.auditLogger.logRequestStarted(
        task.requestId,
        task.sessionId,
        task.priority,
        task.retryCount
      );

    } catch (error) {
      this.logger.error(`Error dispatching task ${task.requestId}: ${error.message}`);
      // Release slot and handle failure
      await this.workerPool.releaseSlot(task.requestId);
      await this.handleFailure(task, error as Error);
    }
  }

  /**
   * Called by RequestManagerGrpcServer when a task completes (via taskComplete gRPC call).
   * This handles the completion of a task dispatched via gRPC stream.
   */
  async handleTaskCompleted(
    requestId: string, 
    success: boolean, 
    errorMessage?: string
  ): Promise<void> {
    const task = this.requestState.get(requestId);
    if (!task) {
      this.logger.warn(`Task ${requestId} not found for completion handling`);
      return;
    }

    // Release the worker slot
    await this.workerPool.releaseSlot(requestId);

    if (success) {
      // Create a minimal ProcessResult for handleSuccess
      const result: ProcessResult = {
        content: 'Task completed via gRPC stream',
        actions: [],
        metrics: {
          totalDurationMs: task.startedAt 
            ? Date.now() - task.startedAt.getTime() 
            : 0,
        },
      };
      await this.handleSuccess(task, result);
    } else {
      const error = new Error(errorMessage || 'Task failed');
      await this.handleFailure(task, error);
    }
  }

  private async handleSuccess(task: RequestTask, result: ProcessResult): Promise<void> {
    // 更新状态
    this.requestState.update(task.requestId, {
      status: 3, // COMPLETED
      progress: 100,
      completedAt: new Date(),
    });

    // 记录成功 - 防御性日期检查
    // Ensure dates are Date objects (they may be strings when loaded from storage)
    const startedAt = ensureDate(task.startedAt);
    const createdAt = ensureDate(task.createdAt);
    
    const startedAtMs = startedAt?.getTime();
    const createdAtMs = createdAt?.getTime();
    
    // Validate dates are valid numbers
    const processingDurationMs = (startedAtMs && !isNaN(startedAtMs))
      ? Date.now() - startedAtMs
      : 0;
    const totalDurationMs = (createdAtMs && !isNaN(createdAtMs))
      ? Date.now() - createdAtMs
      : 0;

    await this.auditLogger.logRequestCompleted(
      task.requestId,
      task.sessionId,
      processingDurationMs,
      totalDurationMs
    );

    // 保存状态快照
    await this.saveStateSnapshot();

    this.logger.log(
      `Request ${task.requestId} (P${PRIORITY_NAMES[task.priority]}) completed successfully`
    );
  }

  private async handleFailure(task: RequestTask, error: Error): Promise<void> {
    // 判断是否应该重试
    const shouldRetry = await this.retryHandler.shouldRetry(task, error);

    if (shouldRetry) {
      // 重试已调度，更新状态
      this.requestState.update(task.requestId, {
        status: 6, // RETRYING
        retryCount: task.retryCount,
      });
    } else {
      // 最终失败
      await this.markAsFailed(task, error);
    }
  }

  private async markAsFailed(task: RequestTask, error: Error): Promise<void> {
    // 更新状态
    this.requestState.update(task.requestId, {
      status: 4, // FAILED
      errorMessage: error.message,
      completedAt: new Date(),
    });

    // 记录失败
    await this.auditLogger.logRequestFailed(
      task.requestId,
      task.sessionId,
      error.message
    );

    // 保存状态快照
    await this.saveStateSnapshot();

    this.logger.error(
      `Request ${task.requestId} (P${PRIORITY_NAMES[task.priority]}) failed: ${error.message}`
    );
  }

  private async saveStateSnapshot(): Promise<void> {
    // 获取所有请求的快照
    // Ensure createdAt is a Date before calling toISOString()
    const requests = this.requestState.getAll().map(task => {
      const createdAt = ensureDate(task.createdAt);
      return {
        requestId: task.requestId,
        status: task.status,
        priority: task.priority,
        sessionId: task.sessionId,
        createdAt: createdAt ? createdAt.toISOString() : new Date().toISOString(),
        retryCount: task.retryCount,
      };
    });

    await this.persistenceService.saveStateSnapshot({
      timestamp: new Date().toISOString(),
      requests,
    });
  }

  async retryRequest(
    requestId: string,
    resetRetryCount = false,
    newPriority?: number
  ): Promise<boolean> {
    const task = this.requestState.get(requestId);
    
    if (!task) {
      return false;
    }

    // 只能重试失败或取消的请求
    if (task.status !== 4 && task.status !== 5) {
      return false;
    }

    await this.retryHandler.retryManually(task, resetRetryCount, newPriority);
    return true;
  }
}