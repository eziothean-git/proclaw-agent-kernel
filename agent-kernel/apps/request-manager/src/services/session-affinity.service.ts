import { Injectable, Logger } from '@nestjs/common';
import { RequestTask } from '../interfaces';
import { AuditLoggerService } from './audit-logger.service';
import { PriorityQueueService } from './priority-queue.service';

@Injectable()
export class SessionAffinityService {
  private readonly logger = new Logger(SessionAffinityService.name);
  private processingSessions: Set<string> = new Set();
  private sessionQueues: Map<string, RequestTask[]> = new Map();

  constructor(
    private readonly auditLogger: AuditLoggerService,
    private readonly priorityQueue: PriorityQueueService,
  ) {}

  async canProcess(sessionId: string): Promise<boolean> {
    return !this.processingSessions.has(sessionId);
  }

  async isProcessing(sessionId: string): Promise<boolean> {
    return this.processingSessions.has(sessionId);
  }

  async enqueueForSession(task: RequestTask): Promise<void> {
    const queue = this.sessionQueues.get(task.sessionId) || [];
    const position = queue.length;
    queue.push(task);
    this.sessionQueues.set(task.sessionId, queue);

    await this.auditLogger.logSessionQueued(
      task.requestId,
      task.sessionId,
      task.priority,
      position
    );

    this.logger.log(
      `Request ${task.requestId} queued for session ${task.sessionId} at position ${position}`
    );
  }

  async startProcessing(sessionId: string): Promise<void> {
    this.processingSessions.add(sessionId);
    this.logger.debug(`Session ${sessionId} marked as processing`);
  }

  async finishProcessing(sessionId: string): Promise<void> {
    this.processingSessions.delete(sessionId);
    this.logger.debug(`Session ${sessionId} finished processing`);
    
    // 自动触发同会话的下一个任务
    await this.triggerNext(sessionId);
  }

  private async triggerNext(sessionId: string): Promise<void> {
    const queue = this.sessionQueues.get(sessionId);
    if (!queue || queue.length === 0) {
      // 清理空队列
      this.sessionQueues.delete(sessionId);
      return;
    }

    const nextTask = queue.shift();
    
    if (!nextTask) {
      this.sessionQueues.delete(sessionId);
      return;
    }
    
    if (queue.length === 0) {
      this.sessionQueues.delete(sessionId);
    }

    // 将任务重新提交到主队列（保持优先级）
    this.logger.log(
      `Triggering next task ${nextTask.requestId} for session ${sessionId}`
    );
    
    await this.priorityQueue.enqueue(nextTask);
  }

  getWaitingSessionCount(): number {
    return this.sessionQueues.size;
  }

  getSessionQueueLength(sessionId: string): number {
    return this.sessionQueues.get(sessionId)?.length || 0;
  }

  getAllWaitingSessions(): Array<{ sessionId: string; queueLength: number }> {
    const result: Array<{ sessionId: string; queueLength: number }> = [];
    for (const [sessionId, queue] of this.sessionQueues.entries()) {
      result.push({ sessionId, queueLength: queue.length });
    }
    return result;
  }
}