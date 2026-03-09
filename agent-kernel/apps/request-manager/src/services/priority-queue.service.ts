import { Injectable, Logger } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { RequestTask } from '../interfaces';
import { AuditLoggerService } from './audit-logger.service';
import { QueueFullException } from '../exceptions';
import { PRIORITY_LEVELS, PRIORITY_NAMES } from '../constants';

@Injectable()
export class PriorityQueueService {
  private readonly logger = new Logger(PriorityQueueService.name);
  private queues: Map<number, RequestTask[]> = new Map();
  private readonly maxQueueSize: number;
  private readonly priorityLevels: number[];

  constructor(
    private readonly configService: ConfigService,
    private readonly auditLogger: AuditLoggerService,
  ) {
    this.maxQueueSize = this.configService.get<number>('MAX_QUEUE_SIZE', 1000);
    this.priorityLevels = [
      PRIORITY_LEVELS.P0_EMERGENCY,
      PRIORITY_LEVELS.P1_SCHEDULED,
      PRIORITY_LEVELS.P2_HIGH,
      PRIORITY_LEVELS.P3_NORMAL,
      PRIORITY_LEVELS.P4_BACKGROUND,
    ];
    
    // 初始化队列
    this.priorityLevels.forEach(level => {
      this.queues.set(level, []);
    });
  }

  async enqueue(task: RequestTask): Promise<number> {
    const currentSize = this.getTotalSize();
    
    if (currentSize >= this.maxQueueSize) {
      await this.auditLogger.logQueueFullRejected(
        task.requestId,
        task.sessionId,
        task.priority
      );
      
      throw new QueueFullException(
        `Queue capacity exceeded (${currentSize}/${this.maxQueueSize})`
      );
    }

    const queue = this.queues.get(task.priority) || [];
    const queuePosition = queue.length;
    queue.push(task);
    this.queues.set(task.priority, queue);

    await this.auditLogger.logRequestQueued(
      task.requestId,
      task.sessionId,
      task.priority,
      queuePosition,
      task.retryCount
    );

    this.logger.log(
      `Request ${task.requestId} (P${PRIORITY_NAMES[task.priority]}) queued at position ${queuePosition}`
    );

    return queuePosition;
  }

  async dequeue(): Promise<RequestTask | null> {
    // 按优先级顺序查找（从高到低）
    for (const priority of this.priorityLevels) {
      const queue = this.queues.get(priority);
      if (queue && queue.length > 0) {
        const task = queue.shift();
        if (task) {
          this.logger.debug(`Request ${task.requestId} dequeued`);
          return task;
        }
      }
    }
    return null;
  }

  peek(priority?: number): RequestTask | null {
    if (priority !== undefined) {
      const queue = this.queues.get(priority);
      if (queue && queue.length > 0) {
        return queue[0] || null;
      }
      return null;
    }

    // 返回最高优先级的任务
    for (const p of this.priorityLevels) {
      const queue = this.queues.get(p);
      if (queue && queue.length > 0) {
        return queue[0];
      }
    }
    return null;
  }

  getTotalSize(): number {
    let total = 0;
    for (const queue of this.queues.values()) {
      total += queue.length;
    }
    return total;
  }

  getSizeByPriority(): Record<number, number> {
    const result: Record<number, number> = {};
    for (const [priority, queue] of this.queues.entries()) {
      result[priority] = queue.length;
    }
    return result;
  }

  remove(requestId: string): RequestTask | null {
    for (const [priority, queue] of this.queues.entries()) {
      const index = queue.findIndex(t => t.requestId === requestId);
      if (index !== -1) {
        const [task] = queue.splice(index, 1);
        this.logger.log(`Request ${requestId} removed from queue`);
        return task;
      }
    }
    return null;
  }
}