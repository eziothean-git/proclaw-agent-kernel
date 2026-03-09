import { Controller, Get, Post, Body, Param, UsePipes, ValidationPipe } from '@nestjs/common';
import { ApiTags, ApiOperation, ApiResponse, ApiProperty } from '@nestjs/swagger';
import { IsString, IsNotEmpty, IsOptional, MaxLength } from 'class-validator';
import { GatewayService } from './gateway.service';

export class ChatRequestDto {
  @ApiProperty({ description: 'Session ID (optional, new session created if not provided)', required: false })
  @IsOptional()
  @IsString()
  sessionId?: string;

  @ApiProperty({ description: 'Message to send to the agent' })
  @IsString()
  @IsNotEmpty()
  @MaxLength(32768)
  message: string;

  @ApiProperty({ description: 'User identifier' })
  @IsString()
  @IsNotEmpty()
  @MaxLength(256)
  userId: string;

  @ApiProperty({ description: 'Platform identifier (e.g. http, cli, qq)', required: false })
  @IsOptional()
  @IsString()
  @MaxLength(64)
  platform?: string;

  @ApiProperty({ description: 'Device identifier', required: false })
  @IsOptional()
  @IsString()
  @MaxLength(256)
  deviceId?: string;

  @ApiProperty({ description: 'Additional metadata', required: false })
  @IsOptional()
  metadata?: Record<string, unknown>;
}

interface ChatResponseDto {
  requestId: string;
  sessionId: string;
  status: 'accepted';
  timestamp: string;
  message: string;
}

@ApiTags('gateway')
@Controller('api/v1')
@UsePipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: false }))
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
