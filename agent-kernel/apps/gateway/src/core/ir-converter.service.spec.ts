import { Test, TestingModule } from '@nestjs/testing';
import { IRConverterService } from './ir-converter.service';
import { StorageService, AttachmentMetadata } from './storage.service';

const mockStorageService = {
  saveAttachment: jest.fn(),
};

describe('IRConverterService', () => {
  let service: IRConverterService;

  beforeEach(async () => {
    jest.clearAllMocks();

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        IRConverterService,
        { provide: StorageService, useValue: mockStorageService },
      ],
    }).compile();

    service = module.get<IRConverterService>(IRConverterService);
    // onModuleInit loads schemas from disk; in unit tests skip actual file loading
    // by not calling onModuleInit — schemas remain null (validation gracefully skips)
  });

  // ──────────────────────────────────────────────
  // convertToInputIR
  // ──────────────────────────────────────────────
  describe('convertToInputIR', () => {
    it('should build a valid InputMessage from ExternalMessage', async () => {
      const result = await service.convertToInputIR(
        {
          message: 'Hello',
          userId: 'user-1',
          platform: 'http',
          deviceId: 'device-1',
          sessionId: 'sess-1',
        },
        'req-xyz',
      );

      expect(result.header.requestId).toBe('req-xyz');
      expect(result.header.userId).toBe('user-1');
      expect(result.header.platform).toBe('http');
      expect(result.header.deviceId).toBe('device-1');
      expect(result.header.sessionId).toBe('sess-1');
      expect(result.body).toBe('Hello');
      expect(result.header.timestamp).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    });

    it('should default priority to 0 when not provided', async () => {
      const result = await service.convertToInputIR(
        { message: 'test', userId: 'u', platform: 'cli', deviceId: 'd' },
        'req-1',
      );
      expect(result.header.priority).toBe(0);
    });

    it('should respect explicit priority', async () => {
      const result = await service.convertToInputIR(
        { message: 'urgent', userId: 'u', platform: 'cli', deviceId: 'd', priority: 5 },
        'req-2',
      );
      expect(result.header.priority).toBe(5);
    });

    it('should not include sessionId in header when not provided', async () => {
      const result = await service.convertToInputIR(
        { message: 'test', userId: 'u', platform: 'cli', deviceId: 'd' },
        'req-3',
      );
      expect(result.header.sessionId).toBeUndefined();
    });

    it('should process attachments via storageService.saveAttachment', async () => {
      const fakeMeta: AttachmentMetadata = {
        index: 0,
        localPath: '/tmp/att/test.txt',
        originalName: 'test.txt',
        mimeType: 'text/plain',
        sizeBytes: 4,
        checksum: 'abc',
      };
      mockStorageService.saveAttachment.mockResolvedValue(fakeMeta);

      const result = await service.convertToInputIR(
        {
          message: 'see attachment',
          userId: 'u',
          platform: 'http',
          deviceId: 'd',
          attachments: [{ buffer: Buffer.from('data'), originalName: 'test.txt', mimeType: 'text/plain' }],
        },
        'req-att',
      );

      expect(mockStorageService.saveAttachment).toHaveBeenCalledTimes(1);
      expect(result.metadata?.attachments).toHaveLength(1);
      expect(result.metadata?.attachments![0].localPath).toBe('/tmp/att/test.txt');
      // Body should have attachment placeholder appended
      expect(result.body).toContain('[attachment:0]');
    });

    it('should not add duplicate attachment placeholders if body already contains them', async () => {
      const fakeMeta: AttachmentMetadata = {
        index: 0,
        localPath: '/tmp/a.txt',
        originalName: 'a.txt',
        mimeType: 'text/plain',
        sizeBytes: 1,
        checksum: 'x',
      };
      mockStorageService.saveAttachment.mockResolvedValue(fakeMeta);

      const result = await service.convertToInputIR(
        {
          message: 'see [attachment:0] here',
          userId: 'u',
          platform: 'http',
          deviceId: 'd',
          attachments: [{ buffer: Buffer.from('x'), originalName: 'a.txt', mimeType: 'text/plain' }],
        },
        'req-no-dup',
      );

      // Should not append another [attachment:0]
      expect((result.body.match(/\[attachment:0\]/g) || []).length).toBe(1);
    });
  });

  // ──────────────────────────────────────────────
  // compileOutputIR
  // ──────────────────────────────────────────────
  describe('compileOutputIR', () => {
    const baseOutput = {
      header: { requestId: 'r1', sessionId: 's1', timestamp: '2026-01-01T00:00:00Z' },
      status: 'completed' as const,
      body: 'Response text',
    };

    it('should return text from ir.body for default platform', () => {
      const compiled = service.compileOutputIR(baseOutput, 'http');
      expect(compiled.text).toBe('Response text');
    });

    it('should return text from ir.body for cli platform', () => {
      const compiled = service.compileOutputIR(baseOutput, 'cli');
      expect(compiled.text).toBe('Response text');
    });

    it('should strip markdown headers for qq platform', () => {
      const qqOutput = { ...baseOutput, body: '# Heading\n**bold** text\n*italic*' };
      const compiled = service.compileOutputIR(qqOutput, 'qq');
      expect(compiled.text).not.toContain('#');
      expect(compiled.text).not.toContain('**');
    });

    it('should include attachment paths in compiled output', () => {
      const outputWithAtt = {
        ...baseOutput,
        metadata: {
          attachments: [{ localPath: '/tmp/out.txt', mimeType: 'text/plain', description: 'A file' }],
        },
      };
      const compiled = service.compileOutputIR(outputWithAtt, 'http');
      expect(compiled.attachments).toHaveLength(1);
      expect(compiled.attachments![0].path).toBe('/tmp/out.txt');
    });
  });

  // ──────────────────────────────────────────────
  // validateIR (with no schemas loaded)
  // ──────────────────────────────────────────────
  describe('validateIR', () => {
    it('should return valid:true when schemas not loaded (graceful degradation)', () => {
      const result = service.validateIR({ anything: true }, 'input');
      expect(result.valid).toBe(true);
    });
  });
});
