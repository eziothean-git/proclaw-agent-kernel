import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as fs from 'fs/promises';
import * as path from 'path';

/**
 * Interface for raw chat request (before IR conversion)
 */
export interface RawChatRequest {
  sessionId?: string;
  message: string;
  userId: string;
  platform?: string;
  deviceId?: string;
  metadata?: Record<string, unknown>;
}

/**
 * Interface for raw request storage entry
 */
export interface RawRequestEntry {
  timestamp: string;
  requestId: string;
  sessionId: string;
  userId: string;
  rawRequest: RawChatRequest;
  sourceIp?: string;
}

/**
 * Interface for index entry
 */
interface RawRequestIndexEntry {
  timestamp: string;
  requestId: string;
  sessionId: string;
  userId: string;
  path: string;
}

@Injectable()
export class RawRequestStorageService implements OnModuleInit {
  private readonly logger = new Logger(RawRequestStorageService.name);
  private readonly basePath: string;
  private readonly rawRequestsPath: string;

  constructor(private readonly configService: ConfigService) {
    this.basePath = this.configService.get<string>('GATEWAY_STORAGE_PATH', '/var/gateway');
    this.rawRequestsPath = path.join(this.basePath, 'raw_requests');
  }

  async onModuleInit(): Promise<void> {
    await this.initializeStorage();
  }

  private async initializeStorage(): Promise<void> {
    try {
      await fs.mkdir(this.rawRequestsPath, { recursive: true });
      this.logger.log(`Raw request storage initialized at ${this.rawRequestsPath}`);
    } catch (error) {
      this.logger.error(`Failed to initialize raw request storage: ${error.message}`);
      throw error;
    }
  }

  private getDateString(): string {
    return new Date().toISOString().split('T')[0];
  }

  /**
   * Save a raw request (before IR conversion)
   * @param requestId - The unique request ID
   * @param sessionId - The session ID
   * @param rawRequest - The original chat request DTO
   * @param sourceIp - Optional source IP address
   * @returns Path to the saved file
   */
  async saveRawRequest(
    requestId: string,
    sessionId: string,
    rawRequest: RawChatRequest,
    sourceIp?: string
  ): Promise<string> {
    const dateStr = this.getDateString();
    const dateDir = path.join(this.rawRequestsPath, dateStr);

    await fs.mkdir(dateDir, { recursive: true });

    const filePath = path.join(dateDir, `${requestId}.json`);

    const entry: RawRequestEntry = {
      timestamp: new Date().toISOString(),
      requestId,
      sessionId,
      userId: rawRequest.userId,
      rawRequest,
      sourceIp,
    };

    try {
      // Write the raw request file
      await fs.writeFile(filePath, JSON.stringify(entry, null, 2), 'utf-8');

      // Append to index
      const indexEntry: RawRequestIndexEntry = {
        timestamp: entry.timestamp,
        requestId,
        sessionId,
        userId: rawRequest.userId,
        path: filePath,
      };

      const indexPath = path.join(this.rawRequestsPath, 'index.jsonl');
      await fs.appendFile(indexPath, JSON.stringify(indexEntry) + '\n', 'utf-8');

      this.logger.debug(`Raw request saved: ${filePath}`);
      return filePath;
    } catch (error) {
      this.logger.error(`Failed to save raw request ${requestId}: ${error.message}`);
      throw error;
    }
  }

  /**
   * Get a raw request by ID
   * @param requestId - The request ID to lookup
   * @returns The raw request entry or null if not found
   */
  async getRawRequest(requestId: string): Promise<RawRequestEntry | null> {
    try {
      const indexPath = path.join(this.rawRequestsPath, 'index.jsonl');
      const content = await fs.readFile(indexPath, 'utf-8');
      const lines = content.split('\n').filter(line => line.trim());

      for (const line of lines) {
        const entry: RawRequestIndexEntry = JSON.parse(line);
        if (entry.requestId === requestId) {
          const fileContent = await fs.readFile(entry.path, 'utf-8');
          return JSON.parse(fileContent) as RawRequestEntry;
        }
      }

      return null;
    } catch (error) {
      this.logger.error(`Failed to get raw request ${requestId}: ${error.message}`);
      return null;
    }
  }

  /**
   * Get raw requests by session ID
   * @param sessionId - The session ID to query
   * @returns Array of raw request entries
   */
  async getRawRequestsBySession(sessionId: string): Promise<RawRequestEntry[]> {
    const results: RawRequestEntry[] = [];

    try {
      const indexPath = path.join(this.rawRequestsPath, 'index.jsonl');
      const content = await fs.readFile(indexPath, 'utf-8');
      const lines = content.split('\n').filter(line => line.trim());

      for (const line of lines) {
        const indexEntry: RawRequestIndexEntry = JSON.parse(line);
        if (indexEntry.sessionId === sessionId) {
          try {
            const fileContent = await fs.readFile(indexEntry.path, 'utf-8');
            results.push(JSON.parse(fileContent) as RawRequestEntry);
          } catch {
            // Skip files that can't be read
            continue;
          }
        }
      }
    } catch (error) {
      this.logger.error(`Failed to get raw requests for session ${sessionId}: ${error.message}`);
    }

    return results.sort((a, b) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }

  /**
   * Query raw requests by date range
   * @param startDate - Start date (inclusive)
   * @param endDate - End date (inclusive)
   * @returns Array of raw request entries
   */
  async queryByDateRange(startDate: Date, endDate: Date): Promise<RawRequestEntry[]> {
    const results: RawRequestEntry[] = [];

    try {
      const indexPath = path.join(this.rawRequestsPath, 'index.jsonl');
      const content = await fs.readFile(indexPath, 'utf-8');
      const lines = content.split('\n').filter(line => line.trim());

      for (const line of lines) {
        const indexEntry: RawRequestIndexEntry = JSON.parse(line);
        const entryDate = new Date(indexEntry.timestamp);

        if (entryDate >= startDate && entryDate <= endDate) {
          try {
            const fileContent = await fs.readFile(indexEntry.path, 'utf-8');
            results.push(JSON.parse(fileContent) as RawRequestEntry);
          } catch {
            continue;
          }
        }
      }
    } catch (error) {
      this.logger.error(`Failed to query raw requests by date range: ${error.message}`);
    }

    return results.sort((a, b) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }
}
