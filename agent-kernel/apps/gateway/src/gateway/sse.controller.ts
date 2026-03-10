import { Controller, Sse, Query, MessageEvent, Logger } from '@nestjs/common';
import { Observable, Subject } from 'rxjs';
import { GatewayService } from './gateway.service';
import { ApiOperation, ApiTags } from '@nestjs/swagger';

interface ChatStreamQueryDto {
  message: string;
  user_id: string;
  platform?: string;
  device_id?: string;
  session_id?: string;
  metadata?: string; // JSON string
}

interface ChatStreamEvent {
  type: 'accepted' | 'status' | 'complete' | 'error' | 'heartbeat';
  timestamp: string;
  requestId: string;
  sessionId?: string;
  message?: string;
  status?: 'pending' | 'processing' | 'completed' | 'failed';
  response?: unknown;
  error?: string;
}

@ApiTags('gateway')
@Controller('api/v1/chat')
export class SseController {
  private readonly logger = new Logger(SseController.name);

  constructor(private readonly gatewayService: GatewayService) {}

  @Sse('stream')
  @ApiOperation({ summary: 'Stream chat request with real-time updates via SSE' })
  async streamChat(@Query() query: ChatStreamQueryDto): Promise<Observable<MessageEvent>> {
    const subject = new Subject<ChatStreamEvent>();

    // Parse metadata if provided
    let metadata: Record<string, unknown> | undefined;
    if (query.metadata) {
      try {
        metadata = JSON.parse(query.metadata);
      } catch {
        this.logger.warn('Failed to parse metadata JSON');
      }
    }

    // Start the chat request and wait for response
    this.gatewayService
      .handleChatRequest({
        message: query.message,
        userId: query.user_id,
        platform: query.platform || 'tui',
        deviceId: query.device_id,
        sessionId: query.session_id,
        metadata,
      })
      .then(async (result) => {
        const { requestId, sessionId } = result;

        // Emit accepted event
        subject.next({
          type: 'accepted',
          timestamp: new Date().toISOString(),
          requestId,
          sessionId,
          message: 'Request accepted and queued for processing',
        });

        try {
          // Wait for response (event-driven, not polling!)
          // This will resolve immediately when webhook callback is received
          const response = await this.gatewayService.waitForResponse(requestId, 5 * 60 * 1000); // 5 min timeout

          // Emit completion
          subject.next({
            type: 'complete',
            timestamp: new Date().toISOString(),
            requestId,
            sessionId,
            response: response,
          });

          subject.complete();
        } catch (error) {
          // Timeout or error
          this.logger.error(`Request ${requestId} failed or timeout: ${error.message}`);
          subject.next({
            type: 'error',
            timestamp: new Date().toISOString(),
            requestId,
            sessionId,
            error: error.message || 'Request processing failed',
          });
          subject.complete();
        }
      })
      .catch((error) => {
        this.logger.error(`Failed to start chat stream: ${error.message}`);
        subject.next({
          type: 'error',
          timestamp: new Date().toISOString(),
          requestId: 'unknown',
          error: `Failed to start request: ${error.message}`,
        });
        subject.complete();
      });

    // Convert to MessageEvent stream
    return subject.asObservable().pipe(
      map((event): MessageEvent => ({
        data: JSON.stringify(event),
      })),
    );
  }
}

// Need to import map
import { map } from 'rxjs/operators';
