import { Injectable, Logger } from '@nestjs/common';
import { KernelService } from '../kernel/kernel.service';
import { RouterService } from '../router/router.service';

interface QueuedRequest {
  id: string;
  sessionId: string;
  userId: string;
  message: string;
  priority: number;
  scheduledAt?: Date;
  createdAt: Date;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  metadata?: Record<string, unknown>;
}

interface RequestQueue {
  [sessionId: string]: QueuedRequest[];
}

@Injectable()
export class RequestQueueService {
  private readonly logger = new Logger(RequestQueueService.name);
  private queues: RequestQueue = {};
  private processingSessions = new Set<string>();

  constructor(
    private readonly kernelService: KernelService,
    private readonly routerService: RouterService,
  ) {}

  /**
   * Enqueue a request, maintaining per-session serialization
   */
  async enqueue(request: Omit<QueuedRequest, 'createdAt' | 'status'>): Promise<QueuedRequest> {
    const { sessionId } = request;
    
    if (!this.queues[sessionId]) {
      this.queues[sessionId] = [];
    }

    const queuedRequest: QueuedRequest = {
      ...request,
      createdAt: new Date(),
      status: 'pending',
    };

    this.queues[sessionId].push(queuedRequest);
    this.logger.log(`Enqueued request ${request.id} for session ${sessionId}`);
    
    // Trigger processing
    this.processQueue(sessionId);
    
    return queuedRequest;
  }

  /**
   * Schedule a future request
   */
  async schedule(
    request: Omit<QueuedRequest, 'createdAt' | 'status' | 'scheduledAt'>,
    executeAt: Date
  ): Promise<QueuedRequest> {
    const queuedRequest: QueuedRequest = {
      ...request,
      scheduledAt: executeAt,
      createdAt: new Date(),
      status: 'pending',
    };

    if (!this.queues[request.sessionId]) {
      this.queues[request.sessionId] = [];
    }

    this.queues[request.sessionId].push(queuedRequest);
    this.logger.log(`Scheduled request ${request.id} for ${executeAt.toISOString()}`);
    
    return queuedRequest;
  }

  /**
   * Process the queue for a specific session
   */
  private async processQueue(sessionId: string): Promise<void> {
    if (this.processingSessions.has(sessionId)) {
      return; // Already processing
    }

    const queue = this.queues[sessionId];
    if (!queue || queue.length === 0) {
      return;
    }

    // Find next eligible request (non-scheduled or scheduled time passed)
    const now = new Date();
    const nextRequestIndex = queue.findIndex(
      r => r.status === 'pending' && (!r.scheduledAt || r.scheduledAt <= now)
    );

    if (nextRequestIndex === -1) {
      return; // No eligible requests
    }

    this.processingSessions.add(sessionId);
    const request = queue[nextRequestIndex];
    request.status = 'processing';

    try {
      this.logger.log(`Processing request ${request.id} for session ${sessionId}`);
      
      // @deprecated: Gateway now uses filesystem mailbox pattern
      // Requests are written to inbox/ directory and processed by Request Manager
      // This in-memory queue is kept for backward compatibility but not actively used
      await this.routerService.setSessionProcessing(sessionId, true);

      // Simulate processing - in real implementation this would be done by Request Manager
      await new Promise(resolve => setTimeout(resolve, 100));
      
      request.status = 'completed';
      await this.routerService.updateSessionActivity(sessionId);
      this.logger.log(`Completed request ${request.id} with status: ${request.status}`);
    } catch (error) {
      request.status = 'failed';
      this.logger.error(`Failed request ${request.id}: ${error.message}`);
    } finally {
      await this.routerService.setSessionProcessing(sessionId, false);

      // Remove completed/failed request from queue
      queue.splice(nextRequestIndex, 1);
      this.processingSessions.delete(sessionId);

      // Process next request in queue
      if (queue.length > 0) {
        void this.processQueue(sessionId);
      }
    }
  }

  /**
   * Get queue status for a session
   */
  async getQueueStatus(sessionId: string): Promise<{
    pending: number;
    processing: number;
    scheduled: number;
  }> {
    const queue = this.queues[sessionId] || [];
    const now = new Date();
    
    return {
      pending: queue.filter(r => r.status === 'pending' && (!r.scheduledAt || r.scheduledAt <= now)).length,
      processing: queue.filter(r => r.status === 'processing').length,
      scheduled: queue.filter(r => r.scheduledAt && r.scheduledAt > now).length,
    };
  }

  /**
   * Cancel a pending request
   */
  async cancelRequest(sessionId: string, requestId: string): Promise<boolean> {
    const queue = this.queues[sessionId];
    if (!queue) return false;

    const index = queue.findIndex(r => r.id === requestId && r.status === 'pending');
    if (index === -1) return false;

    queue.splice(index, 1);
    this.logger.log(`Cancelled request ${requestId}`);
    return true;
  }
}
