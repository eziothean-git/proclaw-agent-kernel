import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import * as path from 'path';
import { RequestTask } from '../interfaces';
import { PriorityQueueService } from '../services/priority-queue.service';
import { SessionAffinityService } from '../services/session-affinity.service';
import { PersistenceService } from '../services/persistence.service';
import { AuditLoggerService } from '../services/audit-logger.service';
import { WorkerPoolService } from '../services/worker-pool.service';
import { RequestStateService } from '../services/request-state.service';
import { QueueFullException } from '../exceptions';
import { PRIORITY_LEVELS } from '../constants';

/**
 * Ensure value is a Date object.
 */
function ensureDate(value: Date | string | undefined): Date | undefined {
  if (!value) {
    return undefined;
  }
  if (value instanceof Date) {
    return value;
  }
  if (typeof value === 'string') {
    const parsed = new Date(value);
    return isNaN(parsed.getTime()) ? undefined : parsed;
  }
  return undefined;
}

@Injectable()
export class RequestManagerGrpcServer implements OnModuleInit {
  private readonly logger = new Logger(RequestManagerGrpcServer.name);
  private server: grpc.Server;
  private readonly port: number;
  private readonly protoPath: string;

  // Kernel Worker连接管理
  private kernelWorkers: Map<string, grpc.ServerWritableStream<any, any>> = new Map();
  private pendingTasks: RequestTask[] = [];
  
  // 活跃任务跟踪（用于统计）
  private activeTasks: Map<string, RequestTask> = new Map();

  constructor(
    private readonly configService: ConfigService,
    private readonly priorityQueue: PriorityQueueService,
    private readonly sessionAffinity: SessionAffinityService,
    private readonly persistenceService: PersistenceService,
    private readonly auditLogger: AuditLoggerService,
    private readonly workerPool: WorkerPoolService,
    private readonly requestState: RequestStateService,
  ) {
    this.port = this.configService.get<number>('REQUEST_MANAGER_GRPC_PORT', 50052);
    const possiblePaths = [
      path.join(__dirname, '../../src/proto/request-manager.proto'),
      path.join(__dirname, '../../proto/request-manager.proto'),
      path.join(process.cwd(), 'src/proto/request-manager.proto'),
      path.join(process.cwd(), 'proto/request-manager.proto'),
    ];
    
    this.protoPath = possiblePaths.find(p => {
      try {
        require('fs').accessSync(p);
        return true;
      } catch {
        return false;
      }
    }) || possiblePaths[0];
  }

  async onModuleInit(): Promise<void> {
    await this.startServer();
    // Start task dispatcher loop
    this.startTaskDispatcher();
  }

  private async startServer(): Promise<void> {
    const packageDefinition = protoLoader.loadSync(this.protoPath, {
      keepCase: false,
      longs: String,
      enums: String,
      defaults: true,
      oneofs: true,
    });

    const proto = grpc.loadPackageDefinition(packageDefinition) as any;
    
    this.server = new grpc.Server();
    
    // RequestManager service
    this.server.addService(proto.requestmanager.RequestManager.service, {
      submitRequest: this.handleSubmitRequest.bind(this),
      getRequestStatus: this.handleGetRequestStatus.bind(this),
      cancelRequest: this.handleCancelRequest.bind(this),
      streamRequestStatus: this.handleStreamRequestStatus.bind(this),
      getQueueStatus: this.handleGetQueueStatus.bind(this),
      getWorkerStatus: this.handleGetWorkerStatus.bind(this),
      retryRequest: this.handleRetryRequest.bind(this),
      shutdown: this.handleShutdown.bind(this),
      healthCheck: this.handleHealthCheck.bind(this),
    });

    // KernelWorker service (Server streaming tasks)
    this.server.addService(proto.requestmanager.KernelWorker.service, {
      streamTasks: this.handleKernelWorkerStreamTasks.bind(this),
      heartbeat: this.handleKernelWorkerHeartbeat.bind(this),
      taskComplete: this.handleTaskComplete.bind(this),
    });

    this.server.bindAsync(
      `0.0.0.0:${this.port}`,
      grpc.ServerCredentials.createInsecure(),
      (err, port) => {
        if (err) {
          this.logger.error(`Failed to start gRPC server: ${err.message}`);
          return;
        }
        this.logger.log(`Request Manager gRPC server started on port ${port}`);
        this.logger.log('Services: RequestManager, KernelWorker (task streaming + heartbeat)');
      }
    );
  }

  // ============ RequestManager Handlers ============

  private async handleSubmitRequest(call: any, callback: any): Promise<void> {
    const request = call.request;
    
    try {
      const priorityMap: Record<number, number> = {
        0: PRIORITY_LEVELS.P0_EMERGENCY,
        1: PRIORITY_LEVELS.P1_SCHEDULED,
        2: PRIORITY_LEVELS.P2_HIGH,
        3: PRIORITY_LEVELS.P3_NORMAL,
        4: PRIORITY_LEVELS.P4_BACKGROUND,
      };
      const priority = priorityMap[request.priority] ?? PRIORITY_LEVELS.P3_NORMAL;

      const task: RequestTask = {
        requestId: request.requestId,
        sessionId: request.sessionId,
        userId: request.userId,
        priority: priority as typeof PRIORITY_LEVELS[keyof typeof PRIORITY_LEVELS],
        body: request.body,
        metadata: request.metadata || {},
        retryCount: 0,
        status: 1, // QUEUED
        createdAt: new Date(),
        timeoutAt: new Date(Date.now() + this.getTimeoutMs(priority)),
        progress: 0,
      };

      // 持久化（不再写入inbox文件，只保留审计日志）
      await this.auditLogger.logRequestReceived(
        task.requestId,
        task.sessionId,
        priority,
        { body: task.body.substring(0, 100) }
      );

      // 检查会话亲和性
      const canProcess = await this.sessionAffinity.canProcess(task.sessionId);
      
      if (!canProcess) {
        await this.sessionAffinity.enqueueForSession(task);
      } else {
        await this.priorityQueue.enqueue(task);
      }

      this.requestState.set(task.requestId, task);

      const estimatedWaitMs = this.calculateEstimatedWaitTime(task);

      callback(null, {
        requestId: task.requestId,
        status: 1, // QUEUED
        queuePosition: this.priorityQueue.getTotalSize(),
        estimatedWaitMs,
        message: 'Request queued successfully',
      });

    } catch (error) {
      if (error instanceof QueueFullException) {
        callback({
          code: grpc.status.RESOURCE_EXHAUSTED,
          message: error.message,
        });
      } else {
        this.logger.error(`Failed to submit request: ${error.message}`);
        callback({
          code: grpc.status.INTERNAL,
          message: error.message,
        });
      }
    }
  }

  private async handleGetRequestStatus(call: any, callback: any): Promise<void> {
    const requestId = call.request.requestId;
    const task = this.requestState.get(requestId);

    if (!task) {
      callback({
        code: grpc.status.NOT_FOUND,
        message: `Request ${requestId} not found`,
      });
      return;
    }

    const now = Date.now();
    const startedAt = ensureDate(task.startedAt);
    const createdAt = ensureDate(task.createdAt);
    const completedAt = ensureDate(task.completedAt);
    
    const waitTimeMs = startedAt && createdAt
      ? startedAt.getTime() - createdAt.getTime()
      : now - (createdAt?.getTime() || now);
    const processingTimeMs = startedAt 
      ? (completedAt?.getTime() || now) - startedAt.getTime()
      : 0;

    const startedAtProto = startedAt
      ? { seconds: Math.floor(startedAt.getTime() / 1000).toString(), nanos: (startedAt.getTime() % 1000) * 1000000 }
      : undefined;
    const completedAtProto = completedAt
      ? { seconds: Math.floor(completedAt.getTime() / 1000).toString(), nanos: (completedAt.getTime() % 1000) * 1000000 }
      : undefined;

    callback(null, {
      requestId: task.requestId,
      sessionId: task.sessionId,
      status: task.status,
      progressPercent: task.progress,
      waitTimeMs,
      processingTimeMs,
      retryCount: task.retryCount,
      errorMessage: task.errorMessage || '',
      startedAt: startedAtProto,
      completedAt: completedAtProto,
    });
  }

  private async handleStreamRequestStatus(call: any): Promise<void> {
    const requestId = call.request.requestId;
    const interval = setInterval(() => {
      const task = this.requestState.get(requestId);
      if (!task) {
        call.end();
        clearInterval(interval);
        return;
      }

      call.write({
        requestId: task.requestId,
        status: task.status,
        progressPercent: task.progress,
        message: task.errorMessage || '',
        timestamp: new Date().toISOString(),
      });

      if (task.status === 3 || task.status === 4 || task.status === 5) {
        call.end();
        clearInterval(interval);
      }
    }, 1000);

    call.on('cancelled', () => {
      clearInterval(interval);
    });
  }

  private async handleCancelRequest(call: any, callback: any): Promise<void> {
    const requestId = call.request.requestId;
    const task = this.requestState.get(requestId);

    if (!task) {
      callback(null, {
        requestId,
        success: false,
        message: `Request ${requestId} not found`,
      });
      return;
    }

    if (task.status !== 1) {
      callback(null, {
        requestId,
        success: false,
        message: `Cannot cancel request in status ${task.status}`,
      });
      return;
    }

    const removed = this.priorityQueue.remove(requestId);
    if (removed) {
      task.status = 5; // CANCELLED
      await this.auditLogger.log({
        eventType: 'request_cancelled',
        requestId,
        sessionId: task.sessionId,
        context: { priority: task.priority, retryCount: task.retryCount },
      });

      callback(null, {
        requestId,
        success: true,
        message: 'Request cancelled successfully',
      });
    } else {
      callback(null, {
        requestId,
        success: false,
        message: 'Request not found in queue',
      });
    }
  }

  private async handleGetQueueStatus(call: any, callback: any): Promise<void> {
    const sizeByPriority = this.priorityQueue.getSizeByPriority();
    const byPriority: Record<number, number> = {};
    for (const [key, value] of Object.entries(sizeByPriority)) {
      byPriority[parseInt(key)] = value;
    }

    callback(null, {
      totalSize: this.priorityQueue.getTotalSize(),
      byPriority,
      waitingSessions: this.sessionAffinity.getWaitingSessionCount(),
    });
  }

  private async handleGetWorkerStatus(call: any, callback: any): Promise<void> {
    const activeTasks = this.workerPool.getActiveTasks();
    
    const workerTasks = activeTasks.map(task => ({
      taskId: task.taskId,
      sessionId: task.sessionId,
      startTime: {
        seconds: Math.floor(task.startTime.getTime() / 1000).toString(),
        nanos: (task.startTime.getTime() % 1000) * 1000000,
      },
      timeoutAt: {
        seconds: Math.floor(task.timeoutAt.getTime() / 1000).toString(),
        nanos: (task.timeoutAt.getTime() % 1000) * 1000000,
      },
      retryCount: task.retryCount,
    }));
    
    callback(null, {
      maxWorkers: this.workerPool.getMaxWorkers(),
      activeWorkers: this.workerPool.getActiveWorkers(),
      availableSlots: this.workerPool.getAvailableSlots(),
      activeTasks: workerTasks,
    });
  }

  private async handleRetryRequest(call: any, callback: any): Promise<void> {
    const { requestId, resetRetryCount, newPriority } = call.request;
    const task = this.requestState.get(requestId);

    if (!task) {
      callback(null, {
        requestId,
        success: false,
        newStatus: 0,
        message: `Request ${requestId} not found`,
      });
      return;
    }

    if (task.status !== 4 && task.status !== 5) {
      callback(null, {
        requestId,
        success: false,
        newStatus: task.status,
        message: `Cannot retry request in status ${task.status}`,
      });
      return;
    }

    let priority: typeof task.priority = task.priority;
    if (newPriority !== undefined && newPriority >= 0 && newPriority <= 4) {
      const priorityMap: Record<number, typeof PRIORITY_LEVELS[keyof typeof PRIORITY_LEVELS]> = {
        0: PRIORITY_LEVELS.P0_EMERGENCY,
        1: PRIORITY_LEVELS.P1_SCHEDULED,
        2: PRIORITY_LEVELS.P2_HIGH,
        3: PRIORITY_LEVELS.P3_NORMAL,
        4: PRIORITY_LEVELS.P4_BACKGROUND,
      };
      priority = priorityMap[newPriority];
    }

    if (resetRetryCount) {
      task.retryCount = 0;
    }
    task.priority = priority;
    task.status = 1;
    task.progress = 0;
    task.errorMessage = undefined;
    task.createdAt = new Date();
    task.timeoutAt = new Date(Date.now() + this.getTimeoutMs(priority));

    await this.priorityQueue.enqueue(task);

    await this.auditLogger.logManualRetry(
      requestId,
      task.sessionId,
      resetRetryCount,
      priority
    );

    callback(null, {
      requestId,
      success: true,
      newStatus: 1,
      message: 'Request queued for retry',
    });
  }

  private async handleShutdown(call: any, callback: any): Promise<void> {
    const { timeoutSeconds, reason } = call.request;
    this.logger.log(`Shutdown requested: ${reason}, timeout: ${timeoutSeconds}s`);
    
    // Get active request count
    const activeRequests = this.workerPool.getActiveWorkers();
    
    callback(null, {
      success: true,
      message: 'Shutdown initiated',
      activeRequests,
      shutdownAt: new Date(Date.now() + timeoutSeconds * 1000).toISOString(),
    });

    // Schedule actual shutdown
    setTimeout(() => {
      this.logger.log('Executing shutdown');
      process.exit(0);
    }, timeoutSeconds * 1000);
  }

  private async handleHealthCheck(call: any, callback: any): Promise<void> {
    callback(null, {
      healthy: true,
      version: '0.1.0',
      timestamp: new Date().toISOString(),
      details: {
        connectedWorkers: this.kernelWorkers.size.toString(),
        activeTasks: this.activeTasks.size.toString(),
        queueSize: this.priorityQueue.getTotalSize().toString(),
      },
    });
  }

  // ============ KernelWorker Handlers (Server Streaming) ============

  private async handleKernelWorkerStreamTasks(call: grpc.ServerWritableStream<any, any>): Promise<void> {
    const workerId = call.request.workerId || `worker-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const capacity = call.request.capacity || 1;
    
    this.logger.log(`Kernel worker connected: ${workerId} (capacity: ${capacity})`);
    
    this.kernelWorkers.set(workerId, call);

    call.on('cancelled', () => {
      this.logger.log(`Kernel worker disconnected: ${workerId}`);
      this.kernelWorkers.delete(workerId);
    });

    call.on('error', (err: any) => {
      this.logger.error(`Kernel worker error: ${err.message}`);
      this.kernelWorkers.delete(workerId);
    });

    // Send any pending tasks immediately
    this.dispatchPendingTasks();
    
    // Keep the stream open
    return new Promise((resolve) => {
      call.on('end', () => {
        this.logger.log(`Kernel worker stream ended: ${workerId}`);
        this.kernelWorkers.delete(workerId);
        resolve();
      });
    });
  }

  private async handleKernelWorkerHeartbeat(call: any, callback: any): Promise<void> {
    const { workerId, activeTasks, availableSlots } = call.request;
    
    this.logger.debug(`Heartbeat from worker ${workerId}: ${activeTasks} active, ${availableSlots} available`);
    
    callback(null, {
      acknowledged: true,
      serverTime: new Date().toISOString(),
    });
  }

  private async handleTaskComplete(call: any, callback: any): Promise<void> {
    const { requestId, success, errorMessage } = call.request;
    
    this.logger.log(`Task ${requestId} completed (success: ${success})`);
    
    // Update request state (for scheduling/tracking purposes only)
    this.updateRequestStatus(requestId, {
      status: success ? 3 : 4, // COMPLETED or FAILED
      progress: 100,
      completedAt: new Date(),
      errorMessage: errorMessage || undefined,
    });
    
    // Remove from active tasks
    this.activeTasks.delete(requestId);
    
    callback(null, {
      acknowledged: true,
    });
  }

  // ============ Task Dispatching ============

  private startTaskDispatcher(): void {
    // Periodically check queue and dispatch to available workers
    setInterval(() => {
      this.dispatchPendingTasks();
    }, 100);
  }

  private async dispatchPendingTasks(): Promise<void> {
    // Get tasks from queue
    while (this.kernelWorkers.size > 0) {
      const task = await this.priorityQueue.dequeue();
      if (!task) break;

      // Find an available worker
      const availableWorker = Array.from(this.kernelWorkers.values())[0];
      if (!availableWorker) {
        // No workers available, put back in queue
        await this.priorityQueue.enqueue(task);
        break;
      }

      // Send task to worker
      // Convert Date to protobuf Timestamp format
      const receivedAtProto = {
        seconds: Math.floor(task.createdAt.getTime() / 1000).toString(),
        nanos: (task.createdAt.getTime() % 1000) * 1000000,
      };
      
      availableWorker.write({
        requestId: task.requestId,
        sessionId: task.sessionId,
        userId: task.userId,
        body: task.body,
        metadata: task.metadata,
        receivedAt: receivedAtProto,
        timeoutSeconds: Math.floor((task.timeoutAt.getTime() - Date.now()) / 1000),
      });

      // Update task status
      task.status = 2; // PROCESSING
      task.startedAt = new Date();
      this.activeTasks.set(task.requestId, task);
      
      this.logger.log(`Dispatched task ${task.requestId} to worker`);
    }
  }

  // ============ Helpers ============

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

  private calculateEstimatedWaitTime(task: RequestTask): number {
    const queueSize = this.priorityQueue.getTotalSize();
    const avgProcessingTime = 30000;
    return queueSize * avgProcessingTime;
  }

  updateRequestStatus(requestId: string, updates: Partial<RequestTask>): void {
    const task = this.requestState.get(requestId);
    if (task) {
      Object.assign(task, updates);
    }
  }

  getRequest(requestId: string): RequestTask | undefined {
    return this.requestState.get(requestId);
  }
}
