import { Injectable, Logger } from '@nestjs/common';
import * as path from 'path';
import * as fsModule from 'fs';
import { v4 as uuidv4 } from 'uuid';
import { IRConverterService } from '../core/ir-converter.service';
import { StorageService, OutputMessage } from '../core/storage.service';
import { RouterService } from '../router/router.service';

interface ChatRequestDto {
  sessionId?: string;
  message: string;
  userId: string;
  platform?: string;
  deviceId?: string;
  metadata?: Record<string, unknown>;
}

interface ChatResponseDto {
  requestId: string;
  sessionId: string;
  status: 'accepted';
  timestamp: string;
  message: string;
}

@Injectable()
export class GatewayService {
  private readonly logger = new Logger(GatewayService.name);
  private responseHandlers = new Map<
    string,
    {
      resolve: (output: OutputMessage) => void;
      reject: (error: Error) => void;
      timeout: NodeJS.Timeout;
    }
  >();

  constructor(
    private readonly storageService: StorageService,
    private readonly irConverterService: IRConverterService,
    private readonly routerService: RouterService,
  ) {
    // Listen for responses from outbox
    this.storageService.watchOutbox((response) => {
      this.handleResponse(response);
    });
  }

  async handleChatRequest(dto: ChatRequestDto): Promise<ChatResponseDto> {
    const requestId = uuidv4();

    this.logger.log(
      `Received chat request ${requestId} from user ${dto.userId} via ${dto.platform || 'unknown'}`,
    );

    // Determine session
    let sessionId = dto.sessionId;
    if (!sessionId) {
      const routeDecision = await this.routerService.determineRoute({
        userId: dto.userId,
        message: dto.message,
        metadata: dto.metadata,
      });

      sessionId = routeDecision.sessionId;
      this.logger.log(
        `Route decision: ${routeDecision.action} for session ${routeDecision.sessionId}`,
      );

      if (routeDecision.action === 'create') {
        await this.routerService.registerSession(routeDecision.sessionId, dto.userId);
      }
    } else {
      const existingSessions = await this.routerService.getActiveSessions(dto.userId);
      const sessionExists = existingSessions.sessions.some(
        (session) => session.sessionId === sessionId,
      );

      if (!sessionExists) {
        await this.routerService.registerSession(sessionId, dto.userId);
      }
    }

    // Convert to Input IR
    const inputIR = await this.irConverterService.convertToInputIR(
      {
        message: dto.message,
        userId: dto.userId,
        platform: dto.platform || 'http',
        deviceId: dto.deviceId || `http-${process.pid}`,
        sessionId,
        metadata: dto.metadata,
      },
      requestId,
    );

    // Save to inbox (file system mailbox)
    await this.storageService.saveRequestToInbox(inputIR);

    this.logger.log(`Request ${requestId} written to inbox for session ${sessionId}`);

    // Return immediately (asynchronous processing)
    return {
      requestId,
      sessionId,
      status: 'accepted',
      timestamp: new Date().toISOString(),
      message: 'Request accepted and queued for processing',
    };
  }

  async waitForResponse(
    requestId: string,
    timeoutMs: number = 60000,
  ): Promise<OutputMessage> {
    return new Promise((resolve, reject) => {
      // Set timeout
      const timeout = setTimeout(() => {
        this.responseHandlers.delete(requestId);
        reject(new Error(`Timeout waiting for response for request ${requestId}`));
      }, timeoutMs);

      // Register handler
      this.responseHandlers.set(requestId, {
        resolve,
        reject,
        timeout,
      });

      // Also watch via storage service
      this.storageService.watchRequest(requestId);
    });
  }

  private handleResponse(response: OutputMessage): void {
    const requestId = response.header.requestId;
    const handler = this.responseHandlers.get(requestId);

    if (handler) {
      clearTimeout(handler.timeout);
      this.responseHandlers.delete(requestId);
      handler.resolve(response);
      this.logger.log(`Response delivered for request ${requestId}`);
    } else {
      this.logger.debug(`Received response for ${requestId} but no handler registered`);
    }
  }

  async getRequestStatus(requestId: string): Promise<{
    requestId: string;
    status: 'pending' | 'processing' | 'completed' | 'failed' | 'not_found';
    response?: OutputMessage;
  }> {
    const status = await this.storageService.getRequestStatus(requestId);

    if (status.status === 'completed' || status.status === 'failed') {
      const response = await this.storageService.getResponseFromOutbox(requestId);
      return {
        requestId,
        status: status.status,
        response: response || undefined,
      };
    }

    return {
      requestId,
      status: status.status,
    };
  }

  async getSessionStatus(sessionId: string): Promise<{
    sessionId: string;
    status: string;
    activeTasks: number;
    queueStatus: {
      pending: number;
      processing: number;
      completed: number;
    };
  }> {
    const routerStatus = await this.routerService.getSessionContext(sessionId);

    // Count requests for this session
    let pending = 0;
    let processing = 0;
    let completed = 0;

    try {
      // Read inbox index
      const inboxPath = path.join(
        process.env.GATEWAY_STORAGE_PATH || '/var/gateway',
        'inbox',
        'index.jsonl',
      );
      const fsPromises = fsModule.promises;
      const inboxContent = await fsPromises.readFile(inboxPath, 'utf-8');
      const inboxLines = inboxContent.split('\n').filter((line: string) => line.trim());

      for (const line of inboxLines) {
        const entry = JSON.parse(line);
        if (entry.sessionId === sessionId) {
          if (entry.status === 'pending') pending++;
          else if (entry.status === 'processing') processing++;
        }
      }

      // Read outbox index
      const outboxPath = path.join(
        process.env.GATEWAY_STORAGE_PATH || '/var/gateway',
        'outbox',
        'index.jsonl',
      );
      const outboxContent = await fsPromises.readFile(outboxPath, 'utf-8');
      const outboxLines = outboxContent.split('\n').filter((line: string) => line.trim());

      for (const line of outboxLines) {
        const entry = JSON.parse(line);
        if (entry.sessionId === sessionId) {
          completed++;
        }
      }
    } catch {
      // Ignore errors, return zeros
    }

    return {
      sessionId,
      status: routerStatus?.context?.['isProcessing'] ? 'processing' : 'idle',
      activeTasks: processing,
      queueStatus: {
        pending,
        processing,
        completed,
      },
    };
  }
}
