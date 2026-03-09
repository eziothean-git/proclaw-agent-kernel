import { Test, TestingModule } from '@nestjs/testing';
import { ConfigService } from '@nestjs/config';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';
import { StorageService, InputMessage, OutputMessage } from './storage.service';

describe('StorageService', () => {
  let service: StorageService;
  let tmpDir: string;

  beforeEach(async () => {
    tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), 'gateway-test-'));

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        StorageService,
        {
          provide: ConfigService,
          useValue: {
            get: (key: string, defaultVal?: string) => {
              if (key === 'GATEWAY_STORAGE_PATH') return tmpDir;
              if (key === 'OUTBOX_POLL_INTERVAL_MS') return '9999999'; // prevent automatic polling in tests
              return defaultVal;
            },
          },
        },
      ],
    }).compile();

    service = module.get<StorageService>(StorageService);
    await service.onModuleInit();
  });

  afterEach(async () => {
    await fs.rm(tmpDir, { recursive: true, force: true });
  });

  function makeInputMessage(overrides: Partial<InputMessage['header']> = {}): InputMessage {
    return {
      header: {
        timestamp: new Date().toISOString(),
        platform: 'test',
        deviceId: 'device-1',
        userId: 'user-1',
        requestId: `req-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        priority: 0,
        ...overrides,
      },
      body: 'Hello agent',
    };
  }

  function makeOutputMessage(requestId: string, sessionId = 'sess-1'): OutputMessage {
    return {
      header: {
        requestId,
        sessionId,
        timestamp: new Date().toISOString(),
        processingTimeMs: 42,
      },
      status: 'completed',
      body: 'Hello user',
    };
  }

  // ──────────────────────────────────────────────
  // Directory initialization
  // ──────────────────────────────────────────────
  describe('onModuleInit', () => {
    it('should create required subdirectories', async () => {
      const dirs = ['inbox', 'outbox', 'pending', 'attachments', 'sessions', 'errors', 'archive', 'logs'];
      for (const dir of dirs) {
        const stat = await fs.stat(path.join(tmpDir, dir));
        expect(stat.isDirectory()).toBe(true);
      }
    });
  });

  // ──────────────────────────────────────────────
  // saveRequestToInbox
  // ──────────────────────────────────────────────
  describe('saveRequestToInbox', () => {
    it('should write a date-partitioned JSON file', async () => {
      const msg = makeInputMessage();
      const filePath = await service.saveRequestToInbox(msg);

      expect(filePath).toContain(path.join(tmpDir, 'inbox'));
      const content = await fs.readFile(filePath, 'utf-8');
      const saved = JSON.parse(content) as InputMessage;
      expect(saved.header.requestId).toBe(msg.header.requestId);
      expect(saved.body).toBe('Hello agent');
    });

    it('should append an entry to inbox/index.jsonl', async () => {
      const msg = makeInputMessage();
      await service.saveRequestToInbox(msg);

      const indexPath = path.join(tmpDir, 'inbox', 'index.jsonl');
      const content = await fs.readFile(indexPath, 'utf-8');
      const lines = content.split('\n').filter(Boolean);
      expect(lines).toHaveLength(1);

      const entry = JSON.parse(lines[0]);
      expect(entry.requestId).toBe(msg.header.requestId);
      expect(entry.status).toBe('pending');
      expect(entry.userId).toBe('user-1');
    });

    it('should append multiple entries to the same index', async () => {
      await service.saveRequestToInbox(makeInputMessage({ requestId: 'r1' }));
      await service.saveRequestToInbox(makeInputMessage({ requestId: 'r2' }));

      const indexPath = path.join(tmpDir, 'inbox', 'index.jsonl');
      const content = await fs.readFile(indexPath, 'utf-8');
      const lines = content.split('\n').filter(Boolean);
      expect(lines).toHaveLength(2);
    });
  });

  // ──────────────────────────────────────────────
  // saveResponseToOutbox + getResponseFromOutbox
  // ──────────────────────────────────────────────
  describe('saveResponseToOutbox / getResponseFromOutbox', () => {
    it('should persist and retrieve a response by requestId', async () => {
      const requestId = 'req-abc-123';
      const response = makeOutputMessage(requestId);
      await service.saveResponseToOutbox(response);

      const retrieved = await service.getResponseFromOutbox(requestId);
      expect(retrieved).not.toBeNull();
      expect(retrieved!.header.requestId).toBe(requestId);
      expect(retrieved!.status).toBe('completed');
      expect(retrieved!.body).toBe('Hello user');
    });

    it('should return null for unknown requestId', async () => {
      const result = await service.getResponseFromOutbox('nonexistent-id');
      expect(result).toBeNull();
    });

    it('should emit "response" event when saving to outbox', async () => {
      const requestId = 'req-emit-test';
      const response = makeOutputMessage(requestId);

      const received: OutputMessage[] = [];
      service.watchOutbox((r) => received.push(r));
      await service.saveResponseToOutbox(response);

      expect(received).toHaveLength(1);
      expect(received[0].header.requestId).toBe(requestId);
    });

    it('should not emit duplicate events when response arrives via saveResponseToOutbox', async () => {
      const requestId = 'req-no-dup';
      const response = makeOutputMessage(requestId);

      // Mark as watched (simulating waitForResponse)
      service.watchRequest(requestId);

      const received: OutputMessage[] = [];
      service.watchOutbox((r) => received.push(r));

      await service.saveResponseToOutbox(response);

      // Manually trigger pollOutbox - should NOT re-emit because already emitted
      // Access private method via type casting for testing
      await (service as any).pollOutbox();

      expect(received).toHaveLength(1);
    });
  });

  // ──────────────────────────────────────────────
  // getRequestStatus
  // ──────────────────────────────────────────────
  describe('getRequestStatus', () => {
    it('should return "not_found" for unknown requestId', async () => {
      const result = await service.getRequestStatus('unknown-id');
      expect(result.status).toBe('not_found');
    });

    it('should return "pending" for a request in inbox', async () => {
      const msg = makeInputMessage({ requestId: 'status-test-1' });
      await service.saveRequestToInbox(msg);

      const result = await service.getRequestStatus('status-test-1');
      expect(result.status).toBe('pending');
    });

    it('should return "completed" for a request in outbox (takes priority over inbox)', async () => {
      const requestId = 'status-test-2';
      const msg = makeInputMessage({ requestId });
      await service.saveRequestToInbox(msg);

      const response = makeOutputMessage(requestId);
      await service.saveResponseToOutbox(response);

      const result = await service.getRequestStatus(requestId);
      expect(result.status).toBe('completed');
    });
  });

  // ──────────────────────────────────────────────
  // getRequest
  // ──────────────────────────────────────────────
  describe('getRequest', () => {
    it('should retrieve a saved inbox request by requestId', async () => {
      const msg = makeInputMessage({ requestId: 'get-req-1' });
      await service.saveRequestToInbox(msg);

      const retrieved = await service.getRequest('get-req-1');
      expect(retrieved).not.toBeNull();
      expect(retrieved!.body).toBe('Hello agent');
    });

    it('should return null when requestId not in inbox', async () => {
      const result = await service.getRequest('does-not-exist');
      expect(result).toBeNull();
    });
  });

  // ──────────────────────────────────────────────
  // saveAttachment
  // ──────────────────────────────────────────────
  describe('saveAttachment', () => {
    it('should save a file buffer and return metadata with checksum', async () => {
      const buffer = Buffer.from('hello attachment');
      const meta = await service.saveAttachment(buffer, {
        index: 0,
        originalName: 'test.txt',
        mimeType: 'text/plain',
      });

      expect(meta.sizeBytes).toBe(buffer.length);
      expect(meta.checksum).toMatch(/^[a-f0-9]{64}$/); // sha256 hex
      expect(meta.localPath).toContain(tmpDir);

      const saved = await fs.readFile(meta.localPath);
      expect(saved.equals(buffer)).toBe(true);
    });

    it('should sanitize dangerous characters in filename (path traversal prevention)', async () => {
      const buffer = Buffer.from('data');
      const meta = await service.saveAttachment(buffer, {
        index: 0,
        originalName: '../../../etc/passwd',
        mimeType: 'text/plain',
      });
      // After path.basename() + sanitization, only 'passwd' part should remain (no .. components)
      expect(path.basename(meta.localPath)).not.toContain('..');
      expect(path.basename(meta.localPath)).not.toContain('/');
    });
  });

  // ──────────────────────────────────────────────
  // saveError
  // ──────────────────────────────────────────────
  describe('saveError', () => {
    it('should persist error details and write to errors/index.jsonl', async () => {
      const requestId = 'err-req-1';
      await service.saveError(requestId, {
        category: 'kernel_error',
        message: 'Something went wrong',
        recoverable: false,
      });

      const indexPath = path.join(tmpDir, 'errors', 'index.jsonl');
      const content = await fs.readFile(indexPath, 'utf-8');
      const lines = content.split('\n').filter(Boolean);
      expect(lines).toHaveLength(1);

      const entry = JSON.parse(lines[0]);
      expect(entry.requestId).toBe(requestId);
      expect(entry.category).toBe('kernel_error');
      expect(entry.recoverable).toBe(false);
    });
  });

  // ──────────────────────────────────────────────
  // watchRequest / stopWatching
  // ──────────────────────────────────────────────
  describe('watchRequest / stopWatching', () => {
    it('should track and remove watched requestIds', () => {
      service.watchRequest('r-watch-1');
      expect((service as any).watchedRequestIds.has('r-watch-1')).toBe(true);

      service.stopWatching('r-watch-1');
      expect((service as any).watchedRequestIds.has('r-watch-1')).toBe(false);
    });
  });

  // ──────────────────────────────────────────────
  // getRequestHistory (async generator)
  // ──────────────────────────────────────────────
  describe('getRequestHistory', () => {
    it('should yield inbox + outbox records for a sessionId', async () => {
      const requestId = 'hist-req-1';
      const sessionId = 'hist-sess-1';
      const msg = makeInputMessage({ requestId, sessionId });
      await service.saveRequestToInbox(msg);

      const response = makeOutputMessage(requestId, sessionId);
      await service.saveResponseToOutbox(response);

      const records: unknown[] = [];
      for await (const record of service.getRequestHistory(sessionId)) {
        records.push(record);
      }

      expect(records).toHaveLength(2);
    });

    it('should yield nothing for unknown sessionId', async () => {
      const records: unknown[] = [];
      for await (const record of service.getRequestHistory('unknown-session')) {
        records.push(record);
      }
      expect(records).toHaveLength(0);
    });
  });
});
