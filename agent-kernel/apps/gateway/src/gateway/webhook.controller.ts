import { Controller, Post, Body, Logger } from '@nestjs/common';
import { ApiTags, ApiOperation } from '@nestjs/swagger';
import { StorageService, OutputMessage } from '../core/storage.service';
import { IRConverterService } from '../core/ir-converter.service';

interface KernelCallbackDto {
  request_id: string;
  session_id: string;
  status: 'completed' | 'failed' | 'partial';
  header?: {
    timestamp?: string;
    processing_time_ms?: number;
    model_version?: string;
    compiler_version?: string;
  };
  body?: string;
  metadata?: {
    attachments?: Array<{
      local_path: string;
      mime_type: string;
      description?: string;
    }>;
    actions?: unknown[];
  };
  error?: {
    category: string;
    code?: string;
    message: string;
    stack_trace?: string;
    recoverable: boolean;
  };
  artifacts?: Record<string, unknown>;
}

@ApiTags('webhook')
@Controller('gateway/webhook')
export class WebhookController {
  private readonly logger = new Logger(WebhookController.name);

  constructor(
    private readonly storageService: StorageService,
    private readonly irConverterService: IRConverterService,
  ) {}

  @Post('kernel-response')
  @ApiOperation({ summary: 'Receive callback from Python Kernel' })
  async handleKernelResponse(@Body() dto: KernelCallbackDto) {
    this.logger.log(`Received kernel callback for request ${dto.request_id}, status: ${dto.status}`);

    try {
      // Build OutputMessage with safe header access
      const now = new Date().toISOString();
      const outputMessage: OutputMessage = {
        header: {
          requestId: dto.request_id,
          sessionId: dto.session_id,
          timestamp: dto.header?.timestamp || now,
          processingTimeMs: dto.header?.processing_time_ms,
          modelVersion: dto.header?.model_version,
          compilerVersion: dto.header?.compiler_version,
        },
        status: dto.status,
        body: dto.body || '',
        metadata: dto.metadata ? {
          attachments: dto.metadata.attachments?.map(att => ({
            localPath: att.local_path,
            mimeType: att.mime_type,
            description: att.description,
          })),
          actions: dto.metadata.actions as any,
        } : undefined,
      };

      if (dto.error) {
        outputMessage.error = {
          category: dto.error.category,
          code: dto.error.code,
          message: dto.error.message,
          stackTrace: dto.error.stack_trace,
          recoverable: dto.error.recoverable,
        };
      }

      if (dto.artifacts) {
        outputMessage.artifacts = dto.artifacts;
      }

      // Save response to outbox
      await this.storageService.saveResponseToOutbox(outputMessage);

      // TODO: Push to user via appropriate platform adapter
      // This will be implemented when we integrate the adapters
      this.logger.log(`Response saved for request ${dto.request_id}`);

      return { received: true, request_id: dto.request_id };
    } catch (error) {
      this.logger.error(`Failed to handle kernel callback: ${error.message}`);
      throw error;
    }
  }
}
