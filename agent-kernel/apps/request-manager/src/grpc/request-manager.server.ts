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
import { QueueFullException, RequestNotFoundException } from '../exceptions';
import { PRIORITY_LEVELS } from '../constants';

@Injectable()
export class RequestManagerGrpcServer implements OnModuleInit {
  private readonly logger = new Logger(RequestManagerGrpcServer.name);
  private server: grpc.Server;
  private readonly port: number;
  private readonly protoPath: string;

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
    // 尝试多个路径来找到 proto 文件
    const possiblePaths = [
      path.join(__dirname, '../../src/proto/request-manager.proto'), // 开发模式 (ts-node)
      path.join(__dirname, '../../proto/request-manager.proto'),     // 生产模式 (dist)
      path.join(process.cwd(), 'src/proto/request-manager.proto'),   // 当前工作目录
      path.join(process.cwd(), 'proto/request-manager.proto'),       // 备选
    ];
    
    this.protoPath = possiblePaths.find(p => {
      try {
        require('fs').accessSync(p);
        return true;
      } catch {
        return false;
      }
    }) || possiblePaths[0]; // 默认使用第一个路径
  }

  async onModuleInit(): Promise<void> {
    await this.startServer();
  }

  private async startServer(): Promise<void> {
    const packageDefinition = protoLoader.loadSync(this.protoPath, {
      keepCase: false,  // 自动将 snake_case 转换为 camelCase
      longs: String,
      enums: String,
      defaults: true,
      oneofs: true,
    });

    const proto = grpc.loadPackageDefinition(packageDefinition) as any;
    const RequestManagerService = proto.requestmanager.RequestManager;

    this.server = new grpc.Server();
    
    this.server.addService(RequestManagerService.service, {
      submitRequest: this.handleSubmitRequest.bind(this),
      getRequestStatus: this.handleGetRequestStatus.bind(this),
      cancelRequest: this.handleCancelRequest.bind(this),
      streamRequestStatus: this.handleStreamRequestStatus.bind(this),
      getQueueStatus: this.handleGetQueueStatus.bind(this),
      getWorkerStatus: this.handleGetWorkerStatus.bind(this),
      retryRequest: this.handleRetryRequest.bind(this),
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
      }
    );
  }

  // ============ Handlers ============

  private async handleSubmitRequest(call: any, callback: any): Promise<void> {
    const request = call.request;
    
    try {
      // 映射优先级
      const priorityMap: Record<number, number> = {
        0: PRIORITY_LEVELS.P0_EMERGENCY,
        1: PRIORITY_LEVELS.P1_SCHEDULED,
        2: PRIORITY_LEVELS.P2_HIGH,
        3: PRIORITY_LEVELS.P3_NORMAL,
        4: PRIORITY_LEVELS.P4_BACKGROUND,
      };
      const priority = priorityMap[request.priority] ?? PRIORITY_LEVELS.P3_NORMAL;

      // 创建任务
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

      // 持久化到 inbox
      await this.persistenceService.saveToInbox({
        requestId: task.requestId,
        sessionId: task.sessionId,
        userId: task.userId,
        priority,
        body: task.body,
        metadata: task.metadata,
        receivedAt: new Date().toISOString(),
        filePath: '',
      });

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
        // 入队
        const queuePosition = await this.priorityQueue.enqueue(task);
      }

      // 存储请求状态
      this.requestState.set(task.requestId, task);

      // 计算预估等待时间
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
    const waitTimeMs = task.startedAt 
      ? task.startedAt.getTime() - task.createdAt.getTime()
      : now - task.createdAt.getTime();
    const processingTimeMs = task.startedAt 
      ? (task.completedAt?.getTime() || now) - task.startedAt.getTime()
      : 0;

    // Convert Date objects to protobuf Timestamp format
    const startedAtProto = task.startedAt
      ? { seconds: Math.floor(task.startedAt.getTime() / 1000).toString(), nanos: (task.startedAt.getTime() % 1000) * 1000000 }
      : undefined;
    const completedAtProto = task.completedAt
      ? { seconds: Math.floor(task.completedAt.getTime() / 1000).toString(), nanos: (task.completedAt.getTime() % 1000) * 1000000 }
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

      // 如果任务完成或失败，结束流
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

    // 只能取消排队中的请求
    if (task.status !== 1) { // QUEUED
      callback(null, {
        requestId,
        success: false,
        message: `Cannot cancel request in status ${task.status}`,
      });
      return;
    }

    // 从队列中移除
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
    
    // 转换优先级键
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
    
    // Convert WorkerState dates to protobuf Timestamp format
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
        newStatus: 0, // UNKNOWN
        message: `Request ${requestId} not found`,
      });
      return;
    }

    // 只能重试失败或取消的请求
    if (task.status !== 4 && task.status !== 5) { // FAILED or CANCELLED
      callback(null, {
        requestId,
        success: false,
        newStatus: task.status,
        message: `Cannot retry request in status ${task.status}`,
      });
      return;
    }

    // 映射新优先级
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

    // 重置状态
    if (resetRetryCount) {
      task.retryCount = 0;
    }
    task.priority = priority;
    task.status = 1; // QUEUED
    task.progress = 0;
    task.errorMessage = undefined;
    task.createdAt = new Date();
    task.timeoutAt = new Date(Date.now() + this.getTimeoutMs(priority));

    // 入队
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
      newStatus: 1, // QUEUED
      message: 'Request queued for retry',
    });
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
    const avgProcessingTime = 30000; // 假设平均30秒
    return queueSize * avgProcessingTime;
  }

  // 供其他服务更新请求状态
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