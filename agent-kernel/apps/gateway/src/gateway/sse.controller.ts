import { Controller, Sse, Query, MessageEvent, Logger } from '@nestjs/common';
import { Observable, Subject, interval } from 'rxjs';
import { takeUntil, map, filter } from 'rxjs/operators';
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
  private readonly HEARTBEAT_INTERVAL = 15000; // 15 seconds

  constructor(private readonly gatewayService: GatewayService) {}

  @Sse('stream')
  @ApiOperation({ summary: 'Stream chat request with real-time updates via SSE' })
  async streamChat(@Query() query: ChatStreamQueryDto): Promise<Observable<MessageEvent>> {
    const subject = new Subject<ChatStreamEvent>();
    const destroy$ = new Subject<void>();

    // Parse metadata if provided
    let metadata: Record<string, unknown> | undefined;
    if (query.metadata) {
      try {
        metadata = JSON.parse(query.metadata);
      } catch {
        this.logger.warn('Failed to parse metadata JSON');
      }
    }

    // Start the chat request
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

        // Start polling for status updates
        const pollInterval = setInterval(async () => {
          try {
            const status = await this.gatewayService.getRequestStatus(requestId);

            // Skip 'not_found' status - will retry on next poll
            if (status.status === 'not_found') {
              return;
            }

            // Emit status update
            subject.next({
              type: 'status',
              timestamp: new Date().toISOString(),
              requestId,
              sessionId,
              status: status.status,
            });

            // If completed or failed, emit final event and complete
            if (status.status === 'completed' || status.status === 'failed') {
              clearInterval(pollInterval);

              if (status.status === 'completed' && status.response) {
                subject.next({
                  type: 'complete',
                  timestamp: new Date().toISOString(),
                  requestId,
                  sessionId,
                  response: status.response,
                });
              } else if (status.status === 'failed') {
                subject.next({
                  type: 'error',
                  timestamp: new Date().toISOString(),
                  requestId,
                  sessionId,
                  error: 'Request processing failed',
                });
              }

              subject.complete();
              destroy$.next();
              destroy$.complete();
            }
          } catch (error) {
            this.logger.error(`Error polling request ${requestId}: ${error.message}`);
            clearInterval(pollInterval);
            subject.next({
              type: 'error',
              timestamp: new Date().toISOString(),
              requestId,
              sessionId,
              error: `Polling error: ${error.message}`,
            });
            subject.complete();
            destroy$.next();
            destroy$.complete();
          }
        }, 500); // Poll every 500ms

        // Set a maximum timeout (5 minutes)
        setTimeout(() => {
          clearInterval(pollInterval);
          subject.next({
            type: 'error',
            timestamp: new Date().toISOString(),
            requestId,
            sessionId,
            error: 'Request timeout after 5 minutes',
          });
          subject.complete();
          destroy$.next();
          destroy$.complete();
        }, 5 * 60 * 1000);
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
        destroy$.next();
        destroy$.complete();
      });

    // Create heartbeat stream
    const heartbeat$ = interval(this.HEARTBEAT_INTERVAL).pipe(
      map(() => ({
        type: 'heartbeat',
        timestamp: new Date().toISOString(),
        requestId: 'heartbeat',
      } as ChatStreamEvent)),
      takeUntil(destroy$),
    );

    // Combine main events with heartbeats
    return new Observable<MessageEvent>((observer) => {
      const subscription = subject.subscribe({
        next: (event) => observer.next({ data: event } as MessageEvent),
        error: (err) => observer.error(err),
        complete: () => observer.complete(),
      });

      const heartbeatSubscription = heartbeat$.subscribe({
        next: (event) => observer.next({ data: event } as MessageEvent),
      });

      // Cleanup on unsubscribe
      return () => {
        subscription.unsubscribe();
        heartbeatSubscription.unsubscribe();
        destroy$.next();
        destroy$.complete();
      };
    });
  }
}
