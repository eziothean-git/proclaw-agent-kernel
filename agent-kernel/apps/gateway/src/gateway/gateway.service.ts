import { Injectable, Logger } from '@nestjs/common';
import { v4 as uuidv4 } from 'uuid';
import { IRConverterService } from '../core/ir-converter.service';
import { StorageService, OutputMessage } from '../core/storage.service';
import { RouterService } from '../router/router.service';
import { RequestManagerClient } from '../grpc/request-manager.client';
import { RawRequestStorageService, RawChatRequest, RawRequestEntry } from '../raw-request/raw-request-storage.service';

interface ChatRequestDto {
  sessionId?: string;
  message: string;
  userId: string;
  platform?: string;
  deviceId?: string;
  priority?: number;
  metadata?: Record<string, unknown>;
  sourceIp?: string;
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
    private readonly requestManagerClient: RequestManagerClient,
    private readonly rawRequestStorage: RawRequestStorageService,
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

    // Step 1: Save raw request (before IR conversion)
    const rawRequest: RawChatRequest = {
      sessionId,
      message: dto.message,
      userId: dto.userId,
      platform: dto.platform,
      deviceId: dto.deviceId,
      metadata: dto.metadata,
    };
    
    await this.rawRequestStorage.saveRawRequest(
      requestId,
      sessionId,
      rawRequest,
      dto.sourceIp
    );
    
    this.logger.debug(`Raw request saved for ${requestId}`);

    // Step 2: Convert to Input IR
    const inputIR = await this.irConverterService.convertToInputIR(
      {
        message: dto.message,
        userId: dto.userId,
        platform: dto.platform || 'http',
        deviceId: dto.deviceId || `http-${process.pid}`,
        sessionId,
        priority: dto.priority,
        metadata: dto.metadata,
      },
      requestId,
    );

    // Step 3: Submit to Request Manager via gRPC
    try {
      const submitResponse = await this.requestManagerClient.submitRequest(
        inputIR,
        dto.priority || 3
      );

      this.logger.log(
        `Request ${requestId} submitted to Request Manager: ${submitResponse.message} ` +
        `(queue position: ${submitResponse.queuePosition})`
      );
    } catch (error) {
      this.logger.error(`Failed to submit request ${requestId} to Request Manager: ${error.message}`);
      throw error;
    }

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
    // First check Request Manager via gRPC
    try {
      const rmStatus = await this.requestManagerClient.getRequestStatus(requestId);
      
      // Map Request Manager status to Gateway status
      const statusMap: { [key: number]: 'pending' | 'processing' | 'completed' | 'failed' } = {
        1: 'pending',     // QUEUED
        2: 'processing',  // PROCESSING
        3: 'completed',   // COMPLETED
        4: 'failed',      // FAILED
        5: 'failed',      // CANCELLED
        6: 'pending',     // RETRYING
      };

      const status = statusMap[rmStatus.status] || 'not_found';

      if (status === 'completed' || status === 'failed') {
        const response = await this.storageService.getResponseFromOutbox(requestId);
        return {
          requestId,
          status,
          response: response || undefined,
        };
      }

      return {
        requestId,
        status,
      };
    } catch (error) {
      this.logger.error(`Failed to get status from Request Manager: ${error.message}`);
      
      // Fallback to local storage
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
      // Read raw requests index to count session requests
      const rawRequests = await this.rawRequestStorage.getRawRequestsBySession(sessionId);
      
      for (const req of rawRequests) {
        const status = await this.getRequestStatus(req.requestId);
        if (status.status === 'pending') pending++;
        else if (status.status === 'processing') processing++;
        else if (status.status === 'completed') completed++;
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

  /**
   * Get raw request by ID (for debugging/audit)
   */
  async getRawRequest(requestId: string) {
    return this.rawRequestStorage.getRawRequest(requestId);
  }

  /**
   * Get raw requests by session (for debugging/audit)
   */
  async getRawRequestsBySession(sessionId: string) {
    return this.rawRequestStorage.getRawRequestsBySession(sessionId);
  }
}
