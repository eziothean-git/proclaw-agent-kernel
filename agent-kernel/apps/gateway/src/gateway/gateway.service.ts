import { Injectable, Logger } from '@nestjs/common';
import { v4 as uuidv4 } from 'uuid';
import { RequestQueueService } from '../request-queue/request-queue.service';
import { RouterService } from '../router/router.service';
import { KernelService } from '../kernel/kernel.service';

interface ChatRequestDto {
  sessionId?: string;
  message: string;
  userId: string;
  metadata?: Record<string, unknown>;
}

interface ChatResponseDto {
  requestId: string;
  sessionId: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  timestamp: string;
}

@Injectable()
export class GatewayService {
  private readonly logger = new Logger(GatewayService.name);

  constructor(
    private readonly requestQueueService: RequestQueueService,
    private readonly routerService: RouterService,
    private readonly kernelService: KernelService,
  ) {}

  async handleChatRequest(dto: ChatRequestDto): Promise<ChatResponseDto> {
    const requestId = uuidv4();

    this.logger.log(`Received chat request ${requestId} from user ${dto.userId}`);

    let sessionId = dto.sessionId;

    if (!sessionId) {
      const routeDecision = await this.routerService.determineRoute({
        userId: dto.userId,
        message: dto.message,
        metadata: dto.metadata,
      });

      sessionId = routeDecision.sessionId;
      this.logger.log(`Route decision: ${routeDecision.action} for session ${routeDecision.sessionId}`);

      if (routeDecision.action === 'create') {
        await this.routerService.registerSession(
          routeDecision.sessionId,
          dto.userId
        );
      }
    } else {
      const existingSessions = await this.routerService.getActiveSessions(dto.userId);
      const sessionExists = existingSessions.sessions.some((session) => session.sessionId === sessionId);

      if (!sessionExists) {
        await this.routerService.registerSession(sessionId, dto.userId);
      }
    }

    await this.requestQueueService.enqueue({
      id: requestId,
      sessionId,
      userId: dto.userId,
      message: dto.message,
      priority: 0,
      metadata: dto.metadata,
    });

    this.logger.log(`Request ${requestId} enqueued for session ${sessionId}`);

    return {
      requestId,
      sessionId,
      status: 'queued',
      timestamp: new Date().toISOString(),
    };
  }

  async getSessionStatus(sessionId: string): Promise<{
    sessionId: string;
    status: string;
    activeTasks: number;
    activeTaskCount: number;
    queueStatus: {
      pending: number;
      processing: number;
      scheduled: number;
    };
  }> {
    const kernelStatus = await this.kernelService.getSessionStatus(sessionId);
    const queueStatus = await this.requestQueueService.getQueueStatus(sessionId);

    const activeTaskCount = kernelStatus?.active_task_count || 0;

    return {
      sessionId,
      status: kernelStatus?.status || 'unknown',
      activeTasks: activeTaskCount,
      activeTaskCount,
      queueStatus,
    };
  }
}
