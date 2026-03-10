import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as fs from 'fs/promises';
import * as path from 'path';
import { createHash } from 'crypto';
import { AuditLogEntry, InboxEntry, StateSnapshot } from '../interfaces';

@Injectable()
export class PersistenceService implements OnModuleInit {
  private readonly logger = new Logger(PersistenceService.name);
  private readonly basePath: string;
  private readonly inboxPath: string;
  private readonly auditPath: string;
  private readonly statePath: string;
  private currentDate: string;

  constructor(private readonly configService: ConfigService) {
    // Use GATEWAY_STORAGE_PATH if available, fall back to STORAGE_BASE_PATH
    const gatewayPath = this.configService.get<string>('GATEWAY_STORAGE_PATH');
    this.basePath = gatewayPath 
      ? path.join(gatewayPath, 'request-manager')
      : this.configService.get<string>('STORAGE_BASE_PATH', '/var/gateway/request-manager');
    this.inboxPath = path.join(this.basePath, 'inbox');
    this.auditPath = path.join(this.basePath, 'audit');
    this.statePath = path.join(this.basePath, 'state');
    this.currentDate = this.getDateString();
  }

  async onModuleInit(): Promise<void> {
    await this.initializeStorage();
    this.logger.log(`Persistence service initialized at ${this.basePath}`);
  }

  private getDateString(): string {
    return new Date().toISOString().split('T')[0];
  }

  private async initializeStorage(): Promise<void> {
    try {
      await fs.mkdir(this.inboxPath, { recursive: true });
      await fs.mkdir(this.auditPath, { recursive: true });
      await fs.mkdir(this.statePath, { recursive: true });

      // 创建日期子目录
      const dateDir = path.join(this.auditPath, this.currentDate);
      await fs.mkdir(dateDir, { recursive: true });
    } catch (error) {
      this.logger.error(`Failed to initialize storage: ${error.message}`);
      throw error;
    }
  }

  // ============ Inbox Operations ============
  async saveToInbox(entry: InboxEntry): Promise<void> {
    const dateStr = this.getDateString();
    const dateDir = path.join(this.inboxPath, dateStr);
    await fs.mkdir(dateDir, { recursive: true });

    const filePath = path.join(dateDir, `${entry.requestId}.json`);
    entry.filePath = filePath;

    try {
      // 写入请求文件
      await fs.writeFile(filePath, JSON.stringify(entry, null, 2), 'utf-8');

      // 追加到索引
      const indexPath = path.join(this.inboxPath, 'index.jsonl');
      const indexEntry = {
        timestamp: entry.receivedAt,
        requestId: entry.requestId,
        sessionId: entry.sessionId,
        priority: entry.priority,
        path: filePath,
      };
      await fs.appendFile(indexPath, JSON.stringify(indexEntry) + '\n', 'utf-8');

      this.logger.debug(`Request saved to inbox: ${filePath}`);
    } catch (error) {
      this.logger.error(`Failed to save to inbox: ${error.message}`);
      throw error;
    }
  }

  async loadFromInbox(requestId: string): Promise<InboxEntry | null> {
    try {
      const indexPath = path.join(this.inboxPath, 'index.jsonl');
      const content = await fs.readFile(indexPath, 'utf-8');
      const lines = content.split('\n').filter(line => line.trim());

      for (const line of lines) {
        const entry = JSON.parse(line);
        if (entry.requestId === requestId) {
          const fileContent = await fs.readFile(entry.path, 'utf-8');
          return JSON.parse(fileContent) as InboxEntry;
        }
      }
      return null;
    } catch (error) {
      this.logger.error(`Failed to load from inbox: ${error.message}`);
      return null;
    }
  }

  // ============ Audit Log Operations ============
  async writeAuditLog(entry: AuditLogEntry): Promise<void> {
    const dateStr = this.getDateString();

    // 如果日期变化，更新当前日期
    if (dateStr !== this.currentDate) {
      this.currentDate = dateStr;
      const dateDir = path.join(this.auditPath, this.currentDate);
      await fs.mkdir(dateDir, { recursive: true });
    }

    try {
      const dateDir = path.join(this.auditPath, this.currentDate);
      const indexPath = path.join(dateDir, 'audit.jsonl');

      const fullEntry: AuditLogEntry = {
        ...entry,
        version: entry.version || '1.0',
        timestamp: entry.timestamp || new Date().toISOString(),
      };

      await fs.appendFile(indexPath, JSON.stringify(fullEntry) + '\n', 'utf-8');
    } catch (error) {
      this.logger.error(`Failed to write audit log: ${error.message}`);
      // 审计日志失败不应影响主流程
    }
  }

  async queryAuditLogs(
    requestId: string,
    startDate?: string,
    endDate?: string
  ): Promise<AuditLogEntry[]> {
    const results: AuditLogEntry[] = [];

    try {
      const dateDirs = await fs.readdir(this.auditPath);
      
      for (const dir of dateDirs) {
        if (startDate && dir < startDate) continue;
        if (endDate && dir > endDate) continue;

        const indexPath = path.join(this.auditPath, dir, 'audit.jsonl');
        try {
          const content = await fs.readFile(indexPath, 'utf-8');
          const lines = content.split('\n').filter(line => line.trim());

          for (const line of lines) {
            const entry = JSON.parse(line) as AuditLogEntry;
            if (entry.requestId === requestId) {
              results.push(entry);
            }
          }
        } catch {
          // 忽略不存在的文件
        }
      }
    } catch (error) {
      this.logger.error(`Failed to query audit logs: ${error.message}`);
    }

    return results.sort((a, b) => 
      new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    );
  }

  // ============ State Snapshot Operations ============
  async saveStateSnapshot(snapshot: StateSnapshot): Promise<void> {
    try {
      const filePath = path.join(this.statePath, 'current.json');
      await fs.writeFile(filePath, JSON.stringify(snapshot, null, 2), 'utf-8');

      // 同时保存历史快照
      const historyPath = path.join(
        this.statePath,
        `snapshot-${snapshot.timestamp.replace(/[:.]/g, '-')}.json`
      );
      await fs.writeFile(historyPath, JSON.stringify(snapshot, null, 2), 'utf-8');
    } catch (error) {
      this.logger.error(`Failed to save state snapshot: ${error.message}`);
    }
  }

  async loadStateSnapshot(): Promise<StateSnapshot | null> {
    try {
      const filePath = path.join(this.statePath, 'current.json');
      const content = await fs.readFile(filePath, 'utf-8');
      return JSON.parse(content) as StateSnapshot;
    } catch {
      return null;
    }
  }

  // ============ Utility Methods ============
  computeHash(data: string): string {
    return createHash('sha256').update(data).digest('hex').substring(0, 16);
  }
}