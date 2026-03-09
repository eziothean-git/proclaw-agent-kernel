import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as fs from 'fs/promises';
import * as path from 'path';
import { createHash } from 'crypto';
import { v4 as uuidv4 } from 'uuid';
import { EventEmitter } from 'events';

export interface AttachmentMetadata {
  index: number;
  localPath: string;
  originalName: string;
  mimeType: string;
  sizeBytes: number;
  checksum: string;
}

export interface InputMessage {
  header: {
    timestamp: string;
    platform: string;
    deviceId: string;
    userId: string;
    sessionId?: string;
    requestId: string;
    sourceIp?: string;
    clientVersion?: string;
    priority?: number;
  };
  metadata?: {
    attachments?: AttachmentMetadata[];
    tags?: string[];
  };
  body: string;
}

export interface OutputMessage {
  header: {
    requestId: string;
    sessionId: string;
    timestamp: string;
    processingTimeMs?: number;
    modelVersion?: string;
    compilerVersion?: string;
  };
  status: 'completed' | 'failed' | 'partial';
  body: string;
  metadata?: {
    attachments?: Array<{
      localPath: string;
      mimeType: string;
      description?: string;
    }>;
    actions?: Array<{
      type: string;
      skill?: string;
      tool?: string;
      status: string;
      durationMs?: number;
    }>;
  };
  error?: {
    category: string;
    code?: string;
    message: string;
    stackTrace?: string;
    recoverable: boolean;
    auditLogRef?: string;
  };
  artifacts?: Record<string, unknown>;
}

export interface DetailedError {
  category: string;
  code?: string;
  message: string;
  stackTrace?: string;
  recoverable: boolean;
  context?: Record<string, unknown>;
}

export interface LogEntry {
  timestamp: string;
  type: 'request' | 'response' | 'error';
  requestId: string;
  sessionId?: string;
  path: string;
}

export interface RequestIndexEntry {
  timestamp: string;
  requestId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  userId: string;
  sessionId?: string;
  priority: number;
  path: string;
}

@Injectable()
export class StorageService implements OnModuleInit {
  private readonly logger = new Logger(StorageService.name);
  private readonly basePath: string;
  private readonly outboxEmitter = new EventEmitter();
  private watchedRequestIds = new Set<string>();
  private emittedRequestIds = new Set<string>();
  private isWatching = false;

  constructor(private readonly configService: ConfigService) {
    this.basePath = this.configService.get<string>('GATEWAY_STORAGE_PATH', '/var/gateway');
  }

  async onModuleInit(): Promise<void> {
    await this.initializeStorage();
    this.startOutboxWatcher();
  }

  private async initializeStorage(): Promise<void> {
    try {
      // Create all directories
      const dirs = [
        'inbox',
        'outbox',
        'pending',
        'attachments',
        'sessions',
        'errors',
        'archive',
        'logs',
      ];

      for (const dir of dirs) {
        await fs.mkdir(path.join(this.basePath, dir), { recursive: true });
      }

      this.logger.log(`Storage initialized at ${this.basePath}`);
    } catch (error) {
      this.logger.error(`Failed to initialize storage: ${error.message}`);
      throw error;
    }
  }

  private getDateString(): string {
    return new Date().toISOString().split('T')[0];
  }

  private async appendToIndex(indexPath: string, entry: Record<string, unknown>): Promise<void> {
    const line = JSON.stringify(entry) + '\n';
    try {
      await fs.appendFile(indexPath, line, 'utf-8');
    } catch (error) {
      this.logger.error(`Failed to append to index ${indexPath}: ${error.message}`);
      throw error;
    }
  }

  /**
   * Save request to inbox (Gateway → Request Manager)
   */
  async saveRequestToInbox(request: InputMessage): Promise<string> {
    const dateStr = this.getDateString();
    const requestId = request.header.requestId;
    const dateDir = path.join(this.basePath, 'inbox', dateStr);

    await fs.mkdir(dateDir, { recursive: true });

    const filePath = path.join(dateDir, `${requestId}.json`);

    try {
      // Write the request file
      await fs.writeFile(filePath, JSON.stringify(request, null, 2), 'utf-8');

      // Append to index
      const indexEntry: RequestIndexEntry = {
        timestamp: request.header.timestamp,
        requestId: requestId,
        status: 'pending',
        userId: request.header.userId,
        sessionId: request.header.sessionId,
        priority: request.header.priority || 0,
        path: filePath,
      };

      const indexPath = path.join(this.basePath, 'inbox', 'index.jsonl');
      await this.appendToIndex(indexPath, { ...indexEntry } as Record<string, unknown>);

      this.logger.log(`Request saved to inbox: ${filePath}`);
      return filePath;
    } catch (error) {
      this.logger.error(`Failed to save request ${requestId}: ${error.message}`);
      throw error;
    }
  }

  /**
   * Read response from outbox (Request Manager → Gateway)
   */
  async getResponseFromOutbox(requestId: string): Promise<OutputMessage | null> {
    try {
      // Try to find in outbox by scanning index
      const indexPath = path.join(this.basePath, 'outbox', 'index.jsonl');

      try {
        const indexContent = await fs.readFile(indexPath, 'utf-8');
        const lines = indexContent.split('\n').filter(line => line.trim());

        for (const line of lines) {
          const entry = JSON.parse(line);
          if (entry.requestId === requestId) {
            const content = await fs.readFile(entry.path, 'utf-8');
            return JSON.parse(content) as OutputMessage;
          }
        }
      } catch {
        // Index doesn't exist yet
        return null;
      }

      return null;
    } catch (error) {
      this.logger.error(`Failed to get response ${requestId}: ${error.message}`);
      return null;
    }
  }

  /**
   * Save response to outbox (Request Manager → Gateway)
   */
  async saveResponseToOutbox(response: OutputMessage): Promise<string> {
    const dateStr = this.getDateString();
    const requestId = response.header.requestId;
    const dateDir = path.join(this.basePath, 'outbox', dateStr);

    await fs.mkdir(dateDir, { recursive: true });

    const filePath = path.join(dateDir, `${requestId}.json`);

    try {
      // Write the response file
      await fs.writeFile(filePath, JSON.stringify(response, null, 2), 'utf-8');

      // Append to index
      const indexEntry = {
        timestamp: response.header.timestamp,
        requestId: requestId,
        sessionId: response.header.sessionId,
        status: response.status,
        path: filePath,
      };

      const indexPath = path.join(this.basePath, 'outbox', 'index.jsonl');
      await this.appendToIndex(indexPath, indexEntry as Record<string, unknown>);

      // Emit event for watchers and mark as emitted to prevent duplicate from pollOutbox
      this.emittedRequestIds.add(requestId);
      this.outboxEmitter.emit('response', response);

      this.logger.log(`Response saved to outbox: ${filePath}`);
      return filePath;
    } catch (error) {
      this.logger.error(`Failed to save response ${requestId}: ${error.message}`);
      throw error;
    }
  }

  /**
   * Watch outbox for new responses
   */
  watchOutbox(callback: (response: OutputMessage) => void): void {
    this.outboxEmitter.on('response', callback);
  }

  unwatchOutbox(callback: (response: OutputMessage) => void): void {
    this.outboxEmitter.off('response', callback);
  }

  /**
   * Start polling outbox for new files
   */
  private startOutboxWatcher(): void {
    if (this.isWatching) return;

    this.isWatching = true;
    this.logger.log('Started outbox watcher (polling)');

    const pollInterval = parseInt(
      this.configService.get<string>('OUTBOX_POLL_INTERVAL_MS', '500'),
      10,
    );

    const poll = async () => {
      try {
        await this.pollOutbox();
      } catch (error) {
        this.logger.error(`Outbox poll error: ${error.message}`);
      }

      if (this.isWatching) {
        setTimeout(poll, pollInterval);
      }
    };

    poll();
  }

  private async pollOutbox(): Promise<void> {
    // Read outbox index
    const indexPath = path.join(this.basePath, 'outbox', 'index.jsonl');

    try {
      const indexContent = await fs.readFile(indexPath, 'utf-8');
      const lines = indexContent.split('\n').filter(line => line.trim());

      for (const line of lines) {
        try {
          const entry = JSON.parse(line);

          // Check if this is a response we're watching for and haven't yet emitted
          if (
            this.watchedRequestIds.has(entry.requestId) &&
            !this.emittedRequestIds.has(entry.requestId)
          ) {
            this.watchedRequestIds.delete(entry.requestId);
            this.emittedRequestIds.add(entry.requestId);

            // Read the response file
            const content = await fs.readFile(entry.path, 'utf-8');
            const response = JSON.parse(content) as OutputMessage;

            // Emit event
            this.outboxEmitter.emit('response', response);
          }
        } catch {
          // Skip malformed lines
          continue;
        }
      }
    } catch {
      // Index doesn't exist yet, that's fine
    }
  }

  /**
   * Register a request to watch for response
   */
  watchRequest(requestId: string): void {
    this.watchedRequestIds.add(requestId);
  }

  stopWatching(requestId: string): void {
    this.watchedRequestIds.delete(requestId);
  }

  /**
   * Save attachment
   */
  async saveAttachment(
    file: Buffer,
    metadata: Omit<AttachmentMetadata, 'localPath' | 'sizeBytes' | 'checksum'>,
  ): Promise<AttachmentMetadata> {
    const dateStr = this.getDateString();
    const attachmentId = uuidv4();
    const dateDir = path.join(this.basePath, 'attachments', dateStr);
    const attachmentDir = path.join(dateDir, attachmentId);

    await fs.mkdir(attachmentDir, { recursive: true });

    // Use only the basename (strips any path traversal sequences like ../) then
    // further sanitize: keep alphanumerics, dots, hyphens, underscores only.
    const baseName = path.basename(metadata.originalName);
    const safeFileName = baseName.replace(/[^a-zA-Z0-9._-]/g, '_') || 'attachment';
    const filePath = path.join(attachmentDir, safeFileName);

    try {
      await fs.writeFile(filePath, file);

      const checksum = createHash('sha256').update(file).digest('hex');
      const stats = await fs.stat(filePath);

      const fullMetadata: AttachmentMetadata = {
        ...metadata,
        localPath: filePath,
        sizeBytes: stats.size,
        checksum,
      };

      const metaPath = path.join(attachmentDir, 'metadata.json');
      await fs.writeFile(metaPath, JSON.stringify(fullMetadata, null, 2), 'utf-8');

      const indexEntry = {
        timestamp: new Date().toISOString(),
        attachmentId,
        ...fullMetadata,
      };

      const indexPath = path.join(this.basePath, 'attachments', 'index.jsonl');
      await this.appendToIndex(indexPath, indexEntry);

      this.logger.debug(`Attachment saved: ${filePath}`);
      return fullMetadata;
    } catch (error) {
      this.logger.error(`Failed to save attachment: ${error.message}`);
      throw error;
    }
  }

  /**
   * Get request from inbox (for debugging/inspection)
   */
  async getRequest(requestId: string): Promise<InputMessage | null> {
    try {
      const indexPath = path.join(this.basePath, 'inbox', 'index.jsonl');
      const indexContent = await fs.readFile(indexPath, 'utf-8');
      const lines = indexContent.split('\n').filter(line => line.trim());

      for (const line of lines) {
        const entry = JSON.parse(line);
        if (entry.requestId === requestId) {
          const content = await fs.readFile(entry.path, 'utf-8');
          return JSON.parse(content) as InputMessage;
        }
      }

      return null;
    } catch (error) {
      this.logger.error(`Failed to get request ${requestId}: ${error.message}`);
      return null;
    }
  }

  /**
   * Save error details
   */
  async saveError(requestId: string, error: DetailedError): Promise<string> {
    const dateStr = this.getDateString();
    const dateDir = path.join(this.basePath, 'errors', dateStr);

    await fs.mkdir(dateDir, { recursive: true });

    const filePath = path.join(dateDir, `${requestId}.json`);
    const errorRecord = {
      requestId,
      timestamp: new Date().toISOString(),
      ...error,
    };

    try {
      await fs.writeFile(filePath, JSON.stringify(errorRecord, null, 2), 'utf-8');

      const indexEntry = {
        timestamp: errorRecord.timestamp,
        type: 'error',
        requestId: requestId,
        category: error.category,
        recoverable: error.recoverable,
        path: filePath,
      };

      const indexPath = path.join(this.basePath, 'errors', 'index.jsonl');
      await this.appendToIndex(indexPath, indexEntry);

      this.logger.debug(`Error saved: ${filePath}`);
      return filePath;
    } catch (err) {
      this.logger.error(`Failed to save error ${requestId}: ${err.message}`);
      throw err;
    }
  }

  /**
   * Get session history
   */
  async *getRequestHistory(sessionId: string): AsyncIterable<InputMessage | OutputMessage> {
    // Get requests from inbox
    try {
      const requestIndexPath = path.join(this.basePath, 'inbox', 'index.jsonl');
      const requestContent = await fs.readFile(requestIndexPath, 'utf-8');
      const requestLines = requestContent.split('\n').filter(line => line.trim());

      for (const line of requestLines) {
        const entry = JSON.parse(line);
        if (entry.sessionId === sessionId) {
          const content = await fs.readFile(entry.path, 'utf-8');
          yield JSON.parse(content);
        }
      }
    } catch {
      // Ignore errors
    }

    // Get responses from outbox
    try {
      const responseIndexPath = path.join(this.basePath, 'outbox', 'index.jsonl');
      const responseContent = await fs.readFile(responseIndexPath, 'utf-8');
      const responseLines = responseContent.split('\n').filter(line => line.trim());

      for (const line of responseLines) {
        const entry = JSON.parse(line);
        if (entry.sessionId === sessionId) {
          const content = await fs.readFile(entry.path, 'utf-8');
          yield JSON.parse(content);
        }
      }
    } catch {
      // Ignore errors
    }
  }

  /**
   * Query by date range
   */
  async *queryByDateRange(start: Date, end: Date): AsyncIterable<LogEntry> {
    const types: Array<'inbox' | 'outbox' | 'errors'> = ['inbox', 'outbox', 'errors'];

    for (const type of types) {
      const indexPath = path.join(this.basePath, type, 'index.jsonl');

      try {
        const content = await fs.readFile(indexPath, 'utf-8');
        const lines = content.split('\n').filter(line => line.trim());

        for (const line of lines) {
          const entry = JSON.parse(line);
          const entryDate = new Date(entry.timestamp);

          if (entryDate >= start && entryDate <= end) {
            yield {
              timestamp: entry.timestamp,
              type: type === 'inbox' ? 'request' : type === 'outbox' ? 'response' : 'error',
              requestId: entry.requestId,
              sessionId: entry.sessionId,
              path: entry.path,
            };
          }
        }
      } catch {
        // Index file may not exist yet
        continue;
      }
    }
  }

  /**
   * Get request status
   * Priority: outbox (completed/failed) > inbox (pending/processing) > not_found
   */
  async getRequestStatus(requestId: string): Promise<{
    status: 'pending' | 'processing' | 'completed' | 'failed' | 'not_found';
    path?: string;
  }> {
    // First check outbox (completed/failed takes priority)
    try {
      const outboxIndexPath = path.join(this.basePath, 'outbox', 'index.jsonl');
      const outboxContent = await fs.readFile(outboxIndexPath, 'utf-8');
      const outboxLines = outboxContent.split('\n').filter(line => line.trim());

      for (const line of outboxLines) {
        const entry = JSON.parse(line);
        if (entry.requestId === requestId) {
          return {
            status: entry.status,
            path: entry.path,
          };
        }
      }
    } catch {
      // Not in outbox
    }

    // Then check inbox (pending/processing)
    try {
      const inboxIndexPath = path.join(this.basePath, 'inbox', 'index.jsonl');
      const inboxContent = await fs.readFile(inboxIndexPath, 'utf-8');
      const inboxLines = inboxContent.split('\n').filter(line => line.trim());

      for (const line of inboxLines) {
        const entry = JSON.parse(line);
        if (entry.requestId === requestId) {
          return {
            status: entry.status,
            path: entry.path,
          };
        }
      }
    } catch {
      // Not in inbox
    }

    return { status: 'not_found' };
  }
}
