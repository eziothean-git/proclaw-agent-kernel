import { Controller, Get, Post, Body, Param } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import { RouterService } from './router.service';

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

@ApiTags('router')
@Controller('api/v1/router')
export class RouterController {
  constructor(private readonly routerService: RouterService) {}

  @Post('route')
  @ApiOperation({ summary: 'Determine routing for a request' })
  @ApiResponse({ status: 200, description: 'Routing decision made' })
  async routeRequest(@Body() dto: RouteRequestDto): Promise<RouteResponseDto> {
    return this.routerService.determineRoute(dto);
  }

  @Get('sessions/:userId/active')
  @ApiOperation({ summary: 'Get active sessions for user' })
  @ApiResponse({ status: 200, description: 'Active sessions retrieved' })
  async getActiveSessions(@Param('userId') userId: string): Promise<{
    sessions: Array<{
      sessionId: string;
      lastActivity: string;
      taskCount: number;
    }>;
  }> {
    return this.routerService.getActiveSessions(userId);
  }

  @Post('sessions/:sessionId/context')
  @ApiOperation({ summary: 'Get session context for Python layer' })
  @ApiResponse({ status: 200, description: 'Session context retrieved' })
  async getSessionContext(@Param('sessionId') sessionId: string): Promise<{
    sessionId: string;
    context: Record<string, unknown>;
  }> {
    return this.routerService.getSessionContext(sessionId);
  }
}
