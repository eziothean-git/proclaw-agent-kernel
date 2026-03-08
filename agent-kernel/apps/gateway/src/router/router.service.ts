import { Injectable, Logger } from '@nestjs/common';

interface RouteRequestDto {
  userId: string;
  message: string;
  metadata?: Record<string, unknown>;
}

interface RouteResponseDto {
  sessionId: string;
  action: 'create' | 'reuse' | 'queue';
  reason: string;
}

interface SessionInfo {
  sessionId: string;
  userId: string;
  createdAt: Date;
  lastActivity: Date;
  taskCount: number;
  isProcessing: boolean;
}

@Injectable()
export class RouterService {
  private readonly logger = new Logger(RouterService.name);
  private sessions = new Map<string, SessionInfo>();

  /**
   * Determine routing decision for a request
   */
  async determineRoute(dto: RouteRequestDto): Promise<RouteResponseDto> {
    const { userId } = dto;
    
    // Find active sessions for user
    const userSessions = this.findUserSessions(userId);
    
    if (userSessions.length === 0) {
      // No active session - create new
      const sessionId = this.generateSessionId();
      this.logger.log(`Creating new session ${sessionId} for user ${userId}`);
      
      return {
        sessionId,
        action: 'create',
        reason: 'No active session found',
      };
    }

    // Check for idle sessions (not processing)
    const idleSessions = userSessions.filter(s => !s.isProcessing);
    
    if (idleSessions.length > 0) {
      // Reuse most recent idle session
      const session = idleSessions[0];
      this.logger.log(`Reusing session ${session.sessionId} for user ${userId}`);
      
      return {
        sessionId: session.sessionId,
        action: 'reuse',
        reason: 'Existing idle session available',
      };
    }

    // All sessions busy - queue to most recent
    const mostRecent = userSessions[0];
    this.logger.log(`Queueing to busy session ${mostRecent.sessionId}`);
    
    return {
      sessionId: mostRecent.sessionId,
      action: 'queue',
      reason: 'All sessions busy, queued for processing',
    };
  }

  /**
   * Get active sessions for a user
   */
  async getActiveSessions(userId: string): Promise<{
    sessions: Array<{
      sessionId: string;
      lastActivity: string;
      taskCount: number;
    }>;
  }> {
    const userSessions = this.findUserSessions(userId);
    
    return {
      sessions: userSessions.map(s => ({
        sessionId: s.sessionId,
        lastActivity: s.lastActivity.toISOString(),
        taskCount: s.taskCount,
      })),
    };
  }

  /**
   * Get session context for Python layer
   */
  async getSessionContext(sessionId: string): Promise<{
    sessionId: string;
    context: Record<string, unknown>;
  }> {
    const session = this.sessions.get(sessionId);
    
    if (!session) {
      return {
        sessionId,
        context: {},
      };
    }

    return {
      sessionId,
      context: {
        userId: session.userId,
        createdAt: session.createdAt.toISOString(),
        lastActivity: session.lastActivity.toISOString(),
        taskCount: session.taskCount,
        isProcessing: session.isProcessing,
      },
    };
  }

  /**
   * Register a new session
   */
  async registerSession(sessionId: string, userId: string): Promise<void> {
    this.sessions.set(sessionId, {
      sessionId,
      userId,
      createdAt: new Date(),
      lastActivity: new Date(),
      taskCount: 0,
      isProcessing: false,
    });
    
    this.logger.log(`Registered session ${sessionId} for user ${userId}`);
  }

  /**
   * Update session activity
   */
  async updateSessionActivity(sessionId: string): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (session) {
      session.lastActivity = new Date();
      session.taskCount++;
    }
  }

  /**
   * Set session processing state
   */
  async setSessionProcessing(sessionId: string, isProcessing: boolean): Promise<void> {
    const session = this.sessions.get(sessionId);
    if (session) {
      session.isProcessing = isProcessing;
    }
  }

  private findUserSessions(userId: string): SessionInfo[] {
    return Array.from(this.sessions.values())
      .filter(s => s.userId === userId)
      .sort((a, b) => b.lastActivity.getTime() - a.lastActivity.getTime());
  }

  private generateSessionId(): string {
    return `sess_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
}
