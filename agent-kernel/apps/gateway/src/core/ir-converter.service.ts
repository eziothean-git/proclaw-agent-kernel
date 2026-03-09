import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import Ajv from 'ajv';
import * as fs from 'fs/promises';
import * as path from 'path';
import { InputMessage, OutputMessage, AttachmentMetadata, StorageService } from './storage.service';

export interface ExternalMessage {
  message: string;
  userId: string;
  platform: string;
  deviceId: string;
  sessionId?: string;
  priority?: number;
  attachments?: Array<{
    buffer: Buffer;
    originalName: string;
    mimeType: string;
  }>;
  metadata?: {
    sourceIp?: string;
    clientVersion?: string;
    tags?: string[];
  };
}

export interface CompiledOutput {
  text: string;
  attachments?: Array<{
    path: string;
    mimeType: string;
    description?: string;
  }>;
  metadata?: Record<string, unknown>;
}

export interface ValidationResult {
  valid: boolean;
  errors?: string[];
}

@Injectable()
export class IRConverterService implements OnModuleInit {
  private readonly logger = new Logger(IRConverterService.name);
  private ajv: Ajv;
  private inputSchema: object | null = null;
  private outputSchema: object | null = null;

  constructor(private readonly storageService: StorageService) {
    this.ajv = new Ajv({ allErrors: true });
  }

  async onModuleInit(): Promise<void> {
    await this.loadSchemas();
  }

  private async loadSchemas(): Promise<void> {
    try {
      const inputSchemaPath = path.join(__dirname, '../schemas/input-message.json');
      const outputSchemaPath = path.join(__dirname, '../schemas/output-message.json');
      
      const inputContent = await fs.readFile(inputSchemaPath, 'utf-8');
      this.inputSchema = JSON.parse(inputContent);
      
      const outputContent = await fs.readFile(outputSchemaPath, 'utf-8');
      this.outputSchema = JSON.parse(outputContent);
      
      this.logger.log('JSON schemas loaded successfully');
    } catch (error) {
      this.logger.error(`Failed to load schemas: ${error.message}`);
    }
  }

  async convertToInputIR(
    externalMsg: ExternalMessage,
    requestId: string,
  ): Promise<InputMessage> {
    // Process attachments if any
    const attachments: AttachmentMetadata[] = [];
    
    if (externalMsg.attachments && externalMsg.attachments.length > 0) {
      for (let i = 0; i < externalMsg.attachments.length; i++) {
        const attachment = externalMsg.attachments[i];
        const metadata = await this.storageService.saveAttachment(attachment.buffer, {
          index: i,
          originalName: attachment.originalName,
          mimeType: attachment.mimeType,
        });
        attachments.push(metadata);
      }
    }

    // Build body with attachment placeholders
    let body = externalMsg.message;
    if (attachments.length > 0) {
      // If message doesn't have placeholders, append them
      const hasPlaceholders = /\[attachment:\d+\]/.test(body);
      if (!hasPlaceholders) {
        const placeholders = attachments.map(a => `[attachment:${a.index}]`).join(' ');
        body = body + ' ' + placeholders;
      }
    }

    const inputIR: InputMessage = {
      header: {
        timestamp: new Date().toISOString(),
        platform: externalMsg.platform,
        deviceId: externalMsg.deviceId,
        userId: externalMsg.userId,
        sessionId: externalMsg.sessionId,
        requestId: requestId,
        sourceIp: externalMsg.metadata?.sourceIp,
        clientVersion: externalMsg.metadata?.clientVersion,
        priority: externalMsg.priority || 0,
      },
      metadata: {
        attachments: attachments.length > 0 ? attachments : undefined,
        tags: externalMsg.metadata?.tags,
      },
      body,
    };

    // Validate
    const validation = this.validateIR(inputIR, 'input');
    if (!validation.valid) {
      this.logger.error(`Input IR validation failed: ${validation.errors?.join(', ')}`);
    }

    return inputIR;
  }

  compileOutputIR(ir: OutputMessage, platform: string): CompiledOutput {
    // Base compilation - mostly just passing through for now
    const compiled: CompiledOutput = {
      text: ir.body,
    };

    // Handle attachments
    if (ir.metadata?.attachments && ir.metadata.attachments.length > 0) {
      compiled.attachments = ir.metadata.attachments.map(att => ({
        path: att.localPath,
        mimeType: att.mimeType,
        description: att.description,
      }));
    }

    // Platform-specific compilation can be extended here
    switch (platform) {
      case 'cli':
        // CLI doesn't need special formatting
        break;
      case 'http':
      case 'websocket':
        // Web can handle HTML/markdown
        break;
      case 'qq':
        // QQ has specific formatting requirements
        compiled.text = this.compileForQQ(compiled.text);
        break;
      default:
        this.logger.warn(`Unknown platform: ${platform}`);
    }

    return compiled;
  }

  private compileForQQ(text: string): string {
    // Basic QQ formatting rules
    // Remove or escape unsupported markdown
    return text
      .replace(/#{1,6}\s/g, '') // Remove headers
      .replace(/\*\*/g, '') // Remove bold markers
      .replace(/\*/g, ''); // Remove italic markers
  }

  validateIR(ir: unknown, schema: 'input' | 'output'): ValidationResult {
    const schemaObj = schema === 'input' ? this.inputSchema : this.outputSchema;
    
    if (!schemaObj) {
      this.logger.warn(`Schema ${schema} not loaded, skipping validation`);
      return { valid: true };
    }

    const validate = this.ajv.compile(schemaObj);
    const valid = validate(ir);

    if (!valid) {
      return {
        valid: false,
        errors: validate.errors?.map(e => `${e.instancePath}: ${e.message}`),
      };
    }

    return { valid: true };
  }
}
