import { Controller, Get, Post, Body, Param } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import { GatewayService } from './gateway.service';
import { KernelService } from '../kernel/kernel.service';

interface ChatRequestDto {
  sessionId?: string;
  message: string;
  userId: string;
  metadata?: Record<string, unknown>;
}

interface ChatResponseDto {
  requestId: string;
  sessionId: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  timestamp: string;
}

@ApiTags('gateway')
@Controller('api/v1')
export class GatewayController {
  constructor(
    private readonly gatewayService: GatewayService,
    private readonly kernelService: KernelService,
  ) {}

  @Post('chat')
  @ApiOperation({ summary: 'Send a message to the agent' })
  @ApiResponse({ status: 201, description: 'Message accepted and queued' })
  @ApiResponse({ status: 400, description: 'Invalid request' })
  async chat(@Body() dto: ChatRequestDto): Promise<ChatResponseDto> {
    return this.gatewayService.handleChatRequest(dto);
  }

  @Get('health')
  @ApiOperation({ summary: 'Health check' })
  @ApiResponse({ status: 200, description: 'Service is healthy' })
  async getHealth(): Promise<{
    status: string;
    gateway: string;
    python_kernel: string;
    timestamp: string;
    version: string;
  }> {
    const pythonHealth = await this.kernelService.healthCheck();

    return {
      status: pythonHealth ? 'healthy' : 'degraded',
      gateway: 'healthy',
      python_kernel: pythonHealth ? 'healthy' : 'unavailable',
      timestamp: new Date().toISOString(),
      version: '0.1.0',
    };
  }

  @Get('sessions/:sessionId/status')
  @ApiOperation({ summary: 'Get session status' })
  @ApiResponse({ status: 200, description: 'Session status retrieved' })
  async getSessionStatus(@Param('sessionId') sessionId: string): Promise<{
    sessionId: string;
    status: string;
    activeTasks: number;
    activeTaskCount: number;
  }> {
    return this.gatewayService.getSessionStatus(sessionId);
  }
}
