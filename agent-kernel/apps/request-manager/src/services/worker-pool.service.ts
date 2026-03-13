import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { RequestTask, ProcessResult } from '../interfaces';
import { AuditLoggerService } from './audit-logger.service';
import { SessionAffinityService } from './session-affinity.service';
import { PrimePersonalityClient } from '../grpc/prime-personality.client';
import { GrpcError, TimeoutException, CancelledException } from '../exceptions';
import { PRIORITY_NAMES } from '../constants';

@Injectable()
export class WorkerPoolService {
  private readonly logger = new Logger(WorkerPoolService.name);
  private maxWorkers: number;
  private activeWorkers = 0;
  private activeTasks: Map<string, WorkerState> = new Map();
  private shutdownPromise: Promise<void> | null = null;
  private pythonKernelUrl: string;

  // Metrics
  private totalProcessed = 0;
  private totalFailed = 0;
  private totalTimedOut = 0;
  private totalCancelled = 0;

  constructor(
    private readonly configService: ConfigService,
    private readonly auditLogger: AuditLoggerService,
    private readonly sessionAffinity: SessionAffinityService,
    private readonly primePersonalityClient: PrimePersonalityClient,
  ) {
    this.maxWorkers = this.configService.get<number>('MAX_CONCURRENT_REQUESTS', 5);
    this.pythonKernelUrl = this.configService.get<string>('PYTHON_KERNEL_URL', 'http://localhost:8000');
  }

  async acquireSlot(task: RequestTask): Promise<boolean> {
    if (this.shutdownPromise) {
      this.logger.warn(`Cannot acquire slot: shutdown in progress`);
      return false;
    }

    if (this.activeWorkers >= this.maxWorkers) {
      return false;
    }

    this.activeWorkers++;
    const timeoutMs = this.getTimeoutMs(task.priority);
    
    this.activeTasks.set(task.requestId, {
      taskId: task.requestId,
      sessionId: task.sessionId,
      startTime: new Date(),
      timeoutAt: new Date(Date.now() + timeoutMs),
      retryCount: task.retryCount,
    });

    return true;
  }

  async releaseSlot(taskId: string): Promise<void> {
    this.activeWorkers--;
    const task = this.activeTasks.get(taskId);
    this.activeTasks.delete(taskId);
    
    if (task) {
      await this.sessionAffinity.finishProcessing(task.sessionId);
    }
  }

  async processTask(task: RequestTask): Promise<{ success: boolean; result?: ProcessResult; error?: Error }> {
    const startTime = Date.now();

    try {
      await this.auditLogger.logRequestStarted(
        task.requestId,
        task.sessionId,
        task.priority,
        task.retryCount
      );

      await this.sessionAffinity.startProcessing(task.sessionId);

      // 更新任务状态
      task.status = 2; // PROCESSING
      task.startedAt = new Date();
      task.progress = 10;

      // 调用 Python Kernel 的 HTTP API
      const timeoutMs = this.getTimeoutMs(task.priority);
      await this.auditLogger.logPrimePersonalityCalled(
        task.requestId,
        task.sessionId,
        timeoutMs
      );

      const ppStartTime = Date.now();
      const result = await this.callPrimePersonalityGrpc(task, timeoutMs);
      const ppDuration = Date.now() - ppStartTime;

      await this.auditLogger.logPrimePersonalityCompleted(
        task.requestId,
        task.sessionId,
        ppDuration
      );

      task.progress = 100;
      task.status = 3; // COMPLETED
      task.completedAt = new Date();

      const totalDuration = Date.now() - startTime;
      await this.auditLogger.logRequestCompleted(
        task.requestId,
        task.sessionId,
        ppDuration,
        totalDuration
      );

      this.totalProcessed++;
      this.logger.log(
        `Request ${task.requestId} completed in ${totalDuration}ms`
      );

      return { success: true, result };

    } catch (error) {
      // 更新任务状态为失败
      task.status = 4; // FAILED
      task.errorMessage = (error as Error).message;
      task.completedAt = new Date();
      this.totalFailed++;
      
      this.logger.error(
        `Request ${task.requestId} failed: ${(error as Error).message}`
      );
      
      return { success: false, error: error as Error };
    } finally {
      await this.releaseSlot(task.requestId);
    }
  }

  private async callPrimePersonalityGrpc(task: RequestTask, timeoutMs: number): Promise<ProcessResult> {
    try {
      const result = await this.primePersonalityClient.processRequest(task, timeoutMs);
      return result;
    } catch (error) {
      this.logger.error(`Failed to call Prime Personality gRPC: ${(error as Error).message}`);
      throw error;
    }
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

  getActiveWorkers(): number {
    return this.activeWorkers;
  }

  getMaxWorkers(): number {
    return this.maxWorkers;
  }

  getAvailableSlots(): number {
    return this.maxWorkers - this.activeWorkers;
  }

  getActiveTasks(): WorkerState[] {
    return Array.from(this.activeTasks.values());
  }

  getMetrics() {
    return {
      totalProcessed: this.totalProcessed,
      totalFailed: this.totalFailed,
      totalTimedOut: this.totalTimedOut,
      totalCancelled: this.totalCancelled,
    };
  }

  async gracefulShutdown(): Promise<void> {
    if (this.shutdownPromise) {
      return this.shutdownPromise;
    }

    this.shutdownPromise = new Promise(async (resolve) => {
      this.logger.log('Starting graceful shutdown...');
      
      while (this.activeWorkers > 0) {
        this.logger.log(`Waiting for ${this.activeWorkers} active tasks to complete...`);
        await new Promise(r => setTimeout(r, 1000));
      }
      
      this.logger.log('All tasks completed. Graceful shutdown finished.');
      resolve();
    });

    return this.shutdownPromise;
  }
}

interface WorkerState {
  taskId: string;
  sessionId: string;
  startTime: Date;
  timeoutAt: Date;
  retryCount: number;
}
