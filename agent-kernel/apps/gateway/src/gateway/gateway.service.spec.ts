import { Test, TestingModule } from '@nestjs/testing';
import { GatewayService } from './gateway.service';
import { StorageService, OutputMessage } from '../core/storage.service';
import { IRConverterService } from '../core/ir-converter.service';
import { RouterService } from '../router/router.service';

// ─── minimal mocks ────────────────────────────────────────────────────────────

const mockStorageService = {
  saveRequestToInbox: jest.fn(),
  getResponseFromOutbox: jest.fn(),
  getRequestStatus: jest.fn(),
  watchOutbox: jest.fn(),
  watchRequest: jest.fn(),
  stopWatching: jest.fn(),
};

const mockIRConverter = {
  convertToInputIR: jest.fn(),
};

const mockRouterService = {
  determineRoute: jest.fn(),
  registerSession: jest.fn(),
  getActiveSessions: jest.fn(),
  getSessionContext: jest.fn(),
  updateSessionActivity: jest.fn(),
  setSessionProcessing: jest.fn(),
};

function makeOutputMessage(requestId: string, sessionId = 'sess-1'): OutputMessage {
  return {
    header: { requestId, sessionId, timestamp: new Date().toISOString() },
    status: 'completed',
    body: 'AI response',
  };
}

// ─── tests ────────────────────────────────────────────────────────────────────

describe('GatewayService', () => {
  let service: GatewayService;

  beforeEach(async () => {
    jest.clearAllMocks();

    // Default happy-path mock behavior
    mockRouterService.determineRoute.mockResolvedValue({
      sessionId: 'sess-auto',
      action: 'create',
      reason: 'No active session',
    });
    mockRouterService.registerSession.mockResolvedValue(undefined);
    mockRouterService.getActiveSessions.mockResolvedValue({ sessions: [] });
    mockRouterService.getSessionContext.mockResolvedValue({
      sessionId: 'sess-1',
      context: { isProcessing: false },
    });
    mockIRConverter.convertToInputIR.mockResolvedValue({
      header: {
        requestId: 'req-mock',
        timestamp: new Date().toISOString(),
        platform: 'http',
        deviceId: 'device-1',
        userId: 'user-1',
        sessionId: 'sess-auto',
        priority: 0,
      },
      body: 'Hello',
    });
    mockStorageService.saveRequestToInbox.mockResolvedValue('/var/gateway/inbox/2026-01-01/req-mock.json');
    mockStorageService.watchOutbox.mockImplementation(() => {});
    mockStorageService.watchRequest.mockImplementation(() => {});
    mockStorageService.stopWatching.mockImplementation(() => {});

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        GatewayService,
        { provide: StorageService, useValue: mockStorageService },
        { provide: IRConverterService, useValue: mockIRConverter },
        { provide: RouterService, useValue: mockRouterService },
      ],
    }).compile();

    service = module.get<GatewayService>(GatewayService);
  });

  // ──────────────────────────────────────────────
  // handleChatRequest — happy path
  // ──────────────────────────────────────────────
  describe('handleChatRequest', () => {
    it('should accept request, write to inbox, and return accepted status immediately', async () => {
      const result = await service.handleChatRequest({
        userId: 'user-1',
        message: 'Hello agent',
        platform: 'http',
      });

      expect(result.status).toBe('accepted');
      expect(result.requestId).toBeTruthy();
      expect(result.sessionId).toBe('sess-auto');
      expect(mockStorageService.saveRequestToInbox).toHaveBeenCalledTimes(1);
      expect(mockIRConverter.convertToInputIR).toHaveBeenCalledTimes(1);
    });

    it('should reuse existing session when sessionId is provided and session is known', async () => {
      mockRouterService.getActiveSessions.mockResolvedValue({
        sessions: [{ sessionId: 'sess-existing', lastActivity: new Date().toISOString(), taskCount: 0 }],
      });

      const result = await service.handleChatRequest({
        userId: 'user-1',
        message: 'continue',
        sessionId: 'sess-existing',
      });

      expect(result.sessionId).toBe('sess-existing');
      // Should NOT call registerSession because session already exists
      expect(mockRouterService.registerSession).not.toHaveBeenCalled();
    });

    it('should call registerSession when provided sessionId is unknown', async () => {
      mockRouterService.getActiveSessions.mockResolvedValue({ sessions: [] });

      await service.handleChatRequest({
        userId: 'user-1',
        message: 'first message',
        sessionId: 'sess-brand-new',
      });

      expect(mockRouterService.registerSession).toHaveBeenCalledWith('sess-brand-new', 'user-1');
    });

    it('should create a new session when no sessionId provided and no active sessions', async () => {
      mockRouterService.determineRoute.mockResolvedValue({
        sessionId: 'sess-new',
        action: 'create',
        reason: 'No session',
      });

      const result = await service.handleChatRequest({
        userId: 'user-1',
        message: 'first message',
      });

      expect(result.sessionId).toBe('sess-new');
      expect(mockRouterService.registerSession).toHaveBeenCalledWith('sess-new', 'user-1');
    });

    it('should not call registerSession when routing decision is reuse', async () => {
      mockRouterService.determineRoute.mockResolvedValue({
        sessionId: 'sess-reuse',
        action: 'reuse',
        reason: 'Idle session exists',
      });

      await service.handleChatRequest({ userId: 'user-1', message: 'hi' });

      expect(mockRouterService.registerSession).not.toHaveBeenCalled();
    });
  });

  // ──────────────────────────────────────────────
  // waitForResponse
  // ──────────────────────────────────────────────
  describe('waitForResponse', () => {
    it('should resolve when a matching response event is emitted', async () => {
      const requestId = 'req-wait-1';
      const expectedOutput = makeOutputMessage(requestId);

      // Capture the watchOutbox callback so we can simulate a response
      let outboxCallback: ((r: OutputMessage) => void) | null = null;
      mockStorageService.watchOutbox.mockImplementation((cb: (r: OutputMessage) => void) => {
        outboxCallback = cb;
      });

      // Rebuild service to capture the new outboxCallback
      const module = await Test.createTestingModule({
        providers: [
          GatewayService,
          { provide: StorageService, useValue: mockStorageService },
          { provide: IRConverterService, useValue: mockIRConverter },
          { provide: RouterService, useValue: mockRouterService },
        ],
      }).compile();
      const svc = module.get<GatewayService>(GatewayService);

      // Start waiting
      const waitPromise = svc.waitForResponse(requestId, 5000);

      // Simulate kernel callback arriving
      setImmediate(() => {
        outboxCallback!(expectedOutput);
      });

      const result = await waitPromise;
      expect(result.header.requestId).toBe(requestId);
      expect(result.body).toBe('AI response');
    });

    it('should reject with timeout when no response arrives within deadline', async () => {
      const requestId = 'req-timeout';

      await expect(
        service.waitForResponse(requestId, 50), // 50ms timeout
      ).rejects.toThrow(/[Tt]imeout/);
    });

    it('should not resolve for a different requestId', async () => {
      let outboxCallback: ((r: OutputMessage) => void) | null = null;
      mockStorageService.watchOutbox.mockImplementation((cb: (r: OutputMessage) => void) => {
        outboxCallback = cb;
      });

      const module = await Test.createTestingModule({
        providers: [
          GatewayService,
          { provide: StorageService, useValue: mockStorageService },
          { provide: IRConverterService, useValue: mockIRConverter },
          { provide: RouterService, useValue: mockRouterService },
        ],
      }).compile();
      const svc = module.get<GatewayService>(GatewayService);

      const waitPromise = svc.waitForResponse('req-target', 100);

      // Deliver a response for a DIFFERENT requestId
      setImmediate(() => {
        outboxCallback!(makeOutputMessage('req-other'));
      });

      await expect(waitPromise).rejects.toThrow(/[Tt]imeout/);
    });
  });

  // ──────────────────────────────────────────────
  // getRequestStatus
  // ──────────────────────────────────────────────
  describe('getRequestStatus', () => {
    it('should return not_found for unknown requestId', async () => {
      mockStorageService.getRequestStatus.mockResolvedValue({ status: 'not_found' });

      const result = await service.getRequestStatus('req-ghost');
      expect(result.status).toBe('not_found');
      expect(result.response).toBeUndefined();
    });

    it('should return pending status without response body', async () => {
      mockStorageService.getRequestStatus.mockResolvedValue({ status: 'pending' });

      const result = await service.getRequestStatus('req-pending');
      expect(result.status).toBe('pending');
      expect(result.response).toBeUndefined();
    });

    it('should return completed status with response body', async () => {
      const requestId = 'req-done';
      const response = makeOutputMessage(requestId);
      mockStorageService.getRequestStatus.mockResolvedValue({ status: 'completed' });
      mockStorageService.getResponseFromOutbox.mockResolvedValue(response);

      const result = await service.getRequestStatus(requestId);
      expect(result.status).toBe('completed');
      expect(result.response).toBeDefined();
      expect((result.response as OutputMessage).body).toBe('AI response');
    });

    it('should return failed status with response body', async () => {
      const requestId = 'req-failed';
      const response: OutputMessage = {
        ...makeOutputMessage(requestId),
        status: 'failed',
        error: { category: 'system_error', message: 'boom', recoverable: false },
      };
      mockStorageService.getRequestStatus.mockResolvedValue({ status: 'failed' });
      mockStorageService.getResponseFromOutbox.mockResolvedValue(response);

      const result = await service.getRequestStatus(requestId);
      expect(result.status).toBe('failed');
    });
  });

  // ──────────────────────────────────────────────
  // getSessionStatus
  // ──────────────────────────────────────────────
  describe('getSessionStatus', () => {
    it('should return idle status when session is not processing', async () => {
      mockRouterService.getSessionContext.mockResolvedValue({
        sessionId: 'sess-idle',
        context: { isProcessing: false },
      });

      const result = await service.getSessionStatus('sess-idle');
      expect(result.sessionId).toBe('sess-idle');
      expect(result.status).toBe('idle');
    });

    it('should return processing status when session is active', async () => {
      mockRouterService.getSessionContext.mockResolvedValue({
        sessionId: 'sess-active',
        context: { isProcessing: true },
      });

      const result = await service.getSessionStatus('sess-active');
      expect(result.status).toBe('processing');
    });

    it('should return zero queue counts when no storage index exists', async () => {
      const result = await service.getSessionStatus('sess-empty');
      expect(result.queueStatus.pending).toBe(0);
      expect(result.queueStatus.processing).toBe(0);
      expect(result.queueStatus.completed).toBe(0);
    });
  });
});
