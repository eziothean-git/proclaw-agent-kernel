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

@Injectable()
export class PriorityRequestManagerService implements OnModuleInit, OnApplicationShutdown {
  private readonly logger = new Logger(PriorityRequestManagerService.name);
  private isRunning = false;
  private schedulerIntervalMs: number;

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
    const startTime = Date.now();

    try {
      const { success, result, error } = await this.workerPool.processTask(task);

      if (success && result) {
        // 任务成功完成
        await this.handleSuccess(task, result);
      } else if (error) {
        // 任务失败，尝试重试
        await this.handleFailure(task, error);
      }

    } catch (unexpectedError) {
      this.logger.error(`Unexpected error processing task ${task.requestId}: ${unexpectedError.message}`);
      await this.handleFailure(task, unexpectedError as Error);
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
    const startedAtMs = task.startedAt?.getTime();
    const createdAtMs = task.createdAt?.getTime();
    
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
    const requests = this.requestState.getAll().map(task => ({
      requestId: task.requestId,
      status: task.status,
      priority: task.priority,
      sessionId: task.sessionId,
      createdAt: task.createdAt.toISOString(),
      retryCount: task.retryCount,
    }));

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