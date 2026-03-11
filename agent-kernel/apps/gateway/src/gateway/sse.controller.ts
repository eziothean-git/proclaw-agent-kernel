import { Controller, Sse, Query, MessageEvent, Logger, Res, Header } from '@nestjs/common';
import { Observable, Subject, merge } from 'rxjs';
import { GatewayService } from './gateway.service';
import { TelemetryAggregatorService } from '../telemetry/telemetry-aggregator.service';
import { TelemetryConfig } from '../telemetry/telemetry.types';
import { ApiOperation, ApiTags } from '@nestjs/swagger';
import { Response } from 'express';
import { map, takeUntil } from 'rxjs/operators';

interface ChatStreamQueryDto {
  message: string;
  user_id: string;
  platform?: string;
  device_id?: string;
  session_id?: string;
  metadata?: string; // JSON string
}

interface TelemetryStreamQueryDto {
  request_id: string;
  config?: string; // JSON string of Partial<TelemetryConfig>
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
@Controller('api/v1')
export class SseController {
  private readonly logger = new Logger(SseController.name);

  constructor(
    private readonly gatewayService: GatewayService,
    private readonly telemetryAggregator: TelemetryAggregatorService,
  ) {}

  /**
   * 原有的 Chat Stream - 业务流程事件
   * accepted → complete/error
   */
  @Sse('chat/stream')
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
          const response = await this.gatewayService.waitForResponse(requestId, 5 * 60 * 1000);

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

  /**
   * 新的 Telemetry Stream - 详细遥测数据流
   * 与 chat/stream 配合使用，提供 Agent 执行详情
   */
  @Sse('telemetry/stream')
  @ApiOperation({ summary: 'Stream detailed telemetry events for a request' })
  @Header('Content-Type', 'text/event-stream')
  @Header('Cache-Control', 'no-cache')
  @Header('Connection', 'keep-alive')
  @Header('X-Accel-Buffering', 'no')
  streamTelemetry(@Query() query: TelemetryStreamQueryDto): Observable<MessageEvent> {
    const { request_id, config: configStr } = query;
    
    if (!request_id) {
      throw new Error('request_id is required');
    }

    // Parse telemetry config
    let telemetryConfig: Partial<TelemetryConfig> = {};
    if (configStr) {
      try {
        telemetryConfig = JSON.parse(configStr);
      } catch {
        this.logger.warn('Failed to parse telemetry config JSON, using defaults');
      }
    }

    this.logger.log(`Client subscribing to telemetry stream: ${request_id}`);

    // Subscribe to telemetry events
    const telemetry$ = this.telemetryAggregator.subscribeToRequest(
      request_id,
      telemetryConfig
    );

    // Create completion trigger
    const completionSubject = new Subject<void>();

    // Watch for request completion to close stream
    this.gatewayService.waitForResponse(request_id, 5 * 60 * 1000)
      .then(() => {
        completionSubject.next();
        completionSubject.complete();
      })
      .catch(() => {
        completionSubject.next();
        completionSubject.complete();
      });

    // Convert telemetry events to SSE format
    return telemetry$.pipe(
      map((event) => ({
        data: JSON.stringify({
          type: 'telemetry',
          timestamp: new Date().toISOString(),
          requestId: request_id,
          data: event,
        }),
      })),
      takeUntil(completionSubject),
    );
  }

  /**
   * 统一流 - 同时返回业务流程和遥测数据
   * 适合 TUI/CLI 客户端使用
   */
  @Sse('chat/telemetry-stream')
  @ApiOperation({ summary: 'Unified stream with both chat events and telemetry' })
  async streamChatWithTelemetry(
    @Query() query: ChatStreamQueryDto & { telemetry_config?: string }
  ): Promise<Observable<MessageEvent>> {
    const chat$ = await this.streamChat(query);
    
    // Parse metadata to get request_id
    let metadata: Record<string, unknown> | undefined;
    if (query.metadata) {
      try {
        metadata = JSON.parse(query.metadata);
      } catch {
        this.logger.warn('Failed to parse metadata JSON');
      }
    }

    // We need to wait for the chat request to be accepted to get request_id
    // For now, return chat stream only, telemetry can be connected separately
    return chat$;
  }
}
