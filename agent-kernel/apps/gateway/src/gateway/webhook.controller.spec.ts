import { Test, TestingModule } from '@nestjs/testing';
import { WebhookController } from './webhook.controller';
import { StorageService, OutputMessage } from '../core/storage.service';
import { IRConverterService } from '../core/ir-converter.service';

const mockStorageService = {
  saveResponseToOutbox: jest.fn(),
};

const mockIRConverter = {};

describe('WebhookController', () => {
  let controller: WebhookController;

  beforeEach(async () => {
    jest.clearAllMocks();
    mockStorageService.saveResponseToOutbox.mockResolvedValue('/outbox/2026-01-01/req.json');

    const module: TestingModule = await Test.createTestingModule({
      controllers: [WebhookController],
      providers: [
        { provide: StorageService, useValue: mockStorageService },
        { provide: IRConverterService, useValue: mockIRConverter },
      ],
    }).compile();

    controller = module.get<WebhookController>(WebhookController);
  });

  describe('handleKernelResponse', () => {
    it('should save a completed response to outbox and return acknowledgment', async () => {
      const dto = {
        request_id: 'req-kernel-1',
        session_id: 'sess-k1',
        status: 'completed' as const,
        header: {
          timestamp: new Date().toISOString(),
          processing_time_ms: 123,
          model_version: 'gpt-4',
          compiler_version: '1.0',
        },
        body: 'Kernel answer',
      };

      const result = await controller.handleKernelResponse(dto);

      expect(result.received).toBe(true);
      expect(result.request_id).toBe('req-kernel-1');

      // Verify the OutputMessage was constructed and saved correctly
      const saved = mockStorageService.saveResponseToOutbox.mock.calls[0][0] as OutputMessage;
      expect(saved.header.requestId).toBe('req-kernel-1');
      expect(saved.header.sessionId).toBe('sess-k1');
      expect(saved.status).toBe('completed');
      expect(saved.body).toBe('Kernel answer');
      expect(saved.header.processingTimeMs).toBe(123);
      expect(saved.header.modelVersion).toBe('gpt-4');
    });

    it('should save a failed response and preserve error details', async () => {
      const dto = {
        request_id: 'req-kernel-fail',
        session_id: 'sess-fail',
        status: 'failed' as const,
        header: { timestamp: new Date().toISOString() },
        body: '',
        error: {
          category: 'system_error',
          code: 'ERR_001',
          message: 'Internal failure',
          stack_trace: 'at line 42',
          recoverable: false,
        },
      };

      await controller.handleKernelResponse(dto);

      const saved = mockStorageService.saveResponseToOutbox.mock.calls[0][0] as OutputMessage;
      expect(saved.status).toBe('failed');
      expect(saved.error?.category).toBe('system_error');
      expect(saved.error?.code).toBe('ERR_001');
      expect(saved.error?.recoverable).toBe(false);
      expect(saved.error?.stackTrace).toBe('at line 42');
    });

    it('should preserve artifacts when provided', async () => {
      const dto = {
        request_id: 'req-art',
        session_id: 'sess-art',
        status: 'completed' as const,
        header: { timestamp: new Date().toISOString() },
        body: 'done',
        artifacts: { graph: { nodes: 5 }, summary: 'artifact summary' },
      };

      await controller.handleKernelResponse(dto);

      const saved = mockStorageService.saveResponseToOutbox.mock.calls[0][0] as OutputMessage;
      expect(saved.artifacts?.['graph']).toEqual({ nodes: 5 });
    });

    it('should propagate storage errors', async () => {
      mockStorageService.saveResponseToOutbox.mockRejectedValue(new Error('disk full'));

      const dto = {
        request_id: 'req-err',
        session_id: 'sess-err',
        status: 'completed' as const,
        header: { timestamp: new Date().toISOString() },
        body: 'ok',
      };

      await expect(controller.handleKernelResponse(dto)).rejects.toThrow('disk full');
    });

    it('should handle partial status correctly', async () => {
      const dto = {
        request_id: 'req-partial',
        session_id: 'sess-partial',
        status: 'partial' as const,
        header: { timestamp: new Date().toISOString() },
        body: 'partial result so far',
      };

      const result = await controller.handleKernelResponse(dto);
      expect(result.received).toBe(true);

      const saved = mockStorageService.saveResponseToOutbox.mock.calls[0][0] as OutputMessage;
      expect(saved.status).toBe('partial');
    });
  });
});
