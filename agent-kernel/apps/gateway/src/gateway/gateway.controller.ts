import { Controller, Get, Post, Body, Param } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse } from '@nestjs/swagger';
import { GatewayService } from './gateway.service';
import { ChatRequestDto } from './dto/chat-request.dto';

interface ChatResponseDto {
  requestId: string;
  sessionId: string;
  status: 'accepted';
  timestamp: string;
  message: string;
}

@ApiTags('gateway')
@Controller('api/v1')
export class GatewayController {
  constructor(private readonly gatewayService: GatewayService) {}

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
    storage: string;
    timestamp: string;
    version: string;
  }> {
    return {
      status: 'healthy',
      gateway: 'healthy',
      storage: 'healthy',
      timestamp: new Date().toISOString(),
      version: '0.2.0',
    };
  }

  @Get('requests/:requestId')
  @ApiOperation({ summary: 'Get request result' })
  @ApiResponse({ status: 200, description: 'Request result retrieved' })
  async getRequestResult(@Param('requestId') requestId: string): Promise<{
    requestId: string;
    status: string;
    response?: unknown;
  }> {
    return this.gatewayService.getRequestStatus(requestId);
  }

  @Get('requests/:requestId/status')
  @ApiOperation({ summary: 'Get request status (lightweight)' })
  @ApiResponse({ status: 200, description: 'Request status retrieved' })
  async getRequestStatus(@Param('requestId') requestId: string): Promise<{
    requestId: string;
    status: string;
  }> {
    const result = await this.gatewayService.getRequestStatus(requestId);
    return {
      requestId: result.requestId,
      status: result.status,
    };
  }

  @Get('sessions/:sessionId/status')
  @ApiOperation({ summary: 'Get session status' })
  @ApiResponse({ status: 200, description: 'Session status retrieved' })
  async getSessionStatus(@Param('sessionId') sessionId: string): Promise<{
    sessionId: string;
    status: string;
    activeTasks: number;
    queueStatus: {
      pending: number;
      processing: number;
      completed: number;
    };
  }> {
    return this.gatewayService.getSessionStatus(sessionId);
  }
}
