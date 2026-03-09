import { Injectable, Logger } from '@nestjs/common';
import * as readline from 'readline';
import { PlatformAdapter, ExternalMessage, CompiledOutput, RequestContext } from '../adapter.interface';

@Injectable()
export class CliAdapter implements PlatformAdapter {
  readonly platform = 'cli';
  private readonly logger = new Logger(CliAdapter.name);
  private messageHandler: ((msg: ExternalMessage) => Promise<void>) | null = null;
  private rl: readline.Interface | null = null;
  private isRunning = false;

  constructor() {}

  onMessage(handler: (msg: ExternalMessage) => Promise<void>): void {
    this.messageHandler = handler;
  }

  async start(): Promise<void> {
    if (this.isRunning) {
      this.logger.warn('CLI adapter already running');
      return;
    }

    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: false,
    });

    this.isRunning = true;
    this.logger.log('CLI adapter started - waiting for JSON input on stdin');

    // Process each line as JSON
    this.rl.on('line', async (line) => {
      try {
        const trimmed = line.trim();
        if (!trimmed) return;

        const msg = JSON.parse(trimmed);
        
        if (!this.messageHandler) {
          this.logger.error('No message handler registered');
          this.outputResponse({
            error: 'Internal error: No message handler registered',
          });
          return;
        }

        // Validate required fields
        if (!msg.message || !msg.user_id) {
          this.outputResponse({
            error: 'Missing required fields: message and user_id',
          });
          return;
        }

        const externalMsg: ExternalMessage = {
          message: msg.message,
          userId: msg.user_id,
          platform: 'cli',
          deviceId: msg.device_id || `cli-${process.pid}`,
          sessionId: msg.session_id,
          metadata: {
            clientVersion: msg.client_version,
            tags: msg.tags,
          },
        };

        await this.messageHandler(externalMsg);

      } catch (error) {
        this.logger.error(`Failed to process CLI input: ${error.message}`);
        this.outputResponse({
          error: `Invalid input: ${error.message}`,
        });
      }
    });

    this.rl.on('close', () => {
      this.logger.log('CLI adapter stopped');
      this.isRunning = false;
    });
  }

  stop(): void {
    if (this.rl) {
      this.rl.close();
      this.rl = null;
    }
    this.isRunning = false;
  }

  async sendResponse(context: RequestContext, output: CompiledOutput): Promise<void> {
    this.outputResponse({
      request_id: context.requestId,
      session_id: context.sessionId,
      status: 'completed',
      response: output.text,
      attachments: output.attachments?.map(att => ({
        path: att.path,
        mime_type: att.mimeType,
        description: att.description,
      })),
    });
  }

  compileForPlatform(ir: unknown): CompiledOutput {
    // For CLI, we just extract the text content
    if (typeof ir === 'string') {
      return { text: ir };
    }
    
    if (ir && typeof ir === 'object') {
      const obj = ir as Record<string, unknown>;
      
      // If it's an OutputMessage structure
      if (typeof obj.body === 'string') {
        return {
          text: obj.body,
          attachments: (obj.metadata as Record<string, unknown>)?.attachments as CompiledOutput['attachments'],
        };
      }
      
      // Fallback
      return { text: JSON.stringify(ir, null, 2) };
    }
    
    return { text: String(ir) };
  }

  healthCheck(): Promise<boolean> {
    return Promise.resolve(this.isRunning);
  }

  private outputResponse(data: Record<string, unknown>): void {
    // Output JSON to stdout
    console.log(JSON.stringify(data));
  }
}
