import { Test, TestingModule } from '@nestjs/testing';
import { RouterService } from './router.service';

describe('RouterService', () => {
  let service: RouterService;

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [RouterService],
    }).compile();

    service = module.get<RouterService>(RouterService);
  });

  // ──────────────────────────────────────────────
  // determineRoute - new user (no sessions)
  // ──────────────────────────────────────────────
  describe('determineRoute — no existing sessions', () => {
    it('should return action=create and a new sessionId when user has no sessions', async () => {
      const result = await service.determineRoute({
        userId: 'user-new',
        message: 'hello',
      });

      expect(result.action).toBe('create');
      expect(result.sessionId).toBeTruthy();
      expect(typeof result.sessionId).toBe('string');
      expect(result.reason).toBeTruthy();
    });
  });

  // ──────────────────────────────────────────────
  // determineRoute - existing idle session
  // ──────────────────────────────────────────────
  describe('determineRoute — idle session exists', () => {
    it('should return action=reuse when user has an idle session', async () => {
      const userId = 'user-idle';
      const sessionId = 'sess-idle-1';
      await service.registerSession(sessionId, userId);

      const result = await service.determineRoute({ userId, message: 'hi' });

      expect(result.action).toBe('reuse');
      expect(result.sessionId).toBe(sessionId);
    });
  });

  // ──────────────────────────────────────────────
  // determineRoute - all sessions busy
  // ──────────────────────────────────────────────
  describe('determineRoute — all sessions processing', () => {
    it('should return action=queue when all sessions are busy', async () => {
      const userId = 'user-busy';
      const sessionId = 'sess-busy-1';
      await service.registerSession(sessionId, userId);
      await service.setSessionProcessing(sessionId, true);

      const result = await service.determineRoute({ userId, message: 'urgent' });

      expect(result.action).toBe('queue');
      expect(result.sessionId).toBe(sessionId);
    });
  });

  // ──────────────────────────────────────────────
  // registerSession
  // ──────────────────────────────────────────────
  describe('registerSession', () => {
    it('should register a session and make it available for routing', async () => {
      await service.registerSession('sess-reg-1', 'user-reg');

      const { sessions } = await service.getActiveSessions('user-reg');
      expect(sessions).toHaveLength(1);
      expect(sessions[0].sessionId).toBe('sess-reg-1');
    });

    it('should track task count separately per session', async () => {
      await service.registerSession('sess-tc-1', 'user-tc');
      await service.updateSessionActivity('sess-tc-1');
      await service.updateSessionActivity('sess-tc-1');

      const { sessions } = await service.getActiveSessions('user-tc');
      expect(sessions[0].taskCount).toBe(2);
    });
  });

  // ──────────────────────────────────────────────
  // getActiveSessions
  // ──────────────────────────────────────────────
  describe('getActiveSessions', () => {
    it('should return empty list for unknown userId', async () => {
      const { sessions } = await service.getActiveSessions('user-ghost');
      expect(sessions).toHaveLength(0);
    });

    it('should return only sessions belonging to the requested user', async () => {
      await service.registerSession('sess-a', 'user-a');
      await service.registerSession('sess-b', 'user-b');

      const { sessions } = await service.getActiveSessions('user-a');
      expect(sessions).toHaveLength(1);
      expect(sessions[0].sessionId).toBe('sess-a');
    });

    it('should return most-recently-active session first', async () => {
      const userId = 'user-order';
      await service.registerSession('sess-old', userId);
      await new Promise(r => setTimeout(r, 5)); // ensure timestamp differs
      await service.registerSession('sess-new', userId);

      const { sessions } = await service.getActiveSessions(userId);
      expect(sessions[0].sessionId).toBe('sess-new');
    });
  });

  // ──────────────────────────────────────────────
  // getSessionContext
  // ──────────────────────────────────────────────
  describe('getSessionContext', () => {
    it('should return context for a registered session', async () => {
      await service.registerSession('sess-ctx-1', 'user-ctx');
      const ctx = await service.getSessionContext('sess-ctx-1');

      expect(ctx.sessionId).toBe('sess-ctx-1');
      expect(ctx.context['userId']).toBe('user-ctx');
      expect(typeof ctx.context['createdAt']).toBe('string');
      expect(ctx.context['isProcessing']).toBe(false);
    });

    it('should return empty context for unknown sessionId', async () => {
      const ctx = await service.getSessionContext('sess-not-exist');
      expect(ctx.sessionId).toBe('sess-not-exist');
      expect(Object.keys(ctx.context)).toHaveLength(0);
    });
  });

  // ──────────────────────────────────────────────
  // setSessionProcessing / updateSessionActivity
  // ──────────────────────────────────────────────
  describe('setSessionProcessing', () => {
    it('should correctly toggle processing state', async () => {
      await service.registerSession('sess-proc-1', 'user-proc');
      await service.setSessionProcessing('sess-proc-1', true);

      let ctx = await service.getSessionContext('sess-proc-1');
      expect(ctx.context['isProcessing']).toBe(true);

      await service.setSessionProcessing('sess-proc-1', false);
      ctx = await service.getSessionContext('sess-proc-1');
      expect(ctx.context['isProcessing']).toBe(false);
    });

    it('should silently ignore unknown sessionId', async () => {
      // Should not throw
      await expect(
        service.setSessionProcessing('non-existent', true),
      ).resolves.not.toThrow();
    });
  });
});
