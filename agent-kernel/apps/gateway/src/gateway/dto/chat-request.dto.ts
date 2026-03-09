import { IsNotEmpty, IsOptional, IsString, Matches, MaxLength } from 'class-validator';
import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';

export class ChatRequestDto {
  @ApiPropertyOptional({ description: 'Existing session ID to continue' })
  @IsOptional()
  @IsString()
  sessionId?: string;

  @ApiProperty({ description: 'User message', maxLength: 10000 })
  @IsNotEmpty()
  @IsString()
  @MaxLength(10000)
  message: string;

  @ApiProperty({ description: 'User identifier' })
  @IsNotEmpty()
  @IsString()
  @MaxLength(256)
  @Matches(/^[\w@.+-]+$/, { message: 'userId must contain only alphanumeric characters, @, ., +, -, or _' })
  userId: string;

  @ApiPropertyOptional({ description: 'Source platform (e.g. http, cli)' })
  @IsOptional()
  @IsString()
  @MaxLength(64)
  platform?: string;

  @ApiPropertyOptional({ description: 'Device identifier' })
  @IsOptional()
  @IsString()
  @MaxLength(256)
  deviceId?: string;

  @ApiPropertyOptional({ description: 'Additional metadata' })
  @IsOptional()
  metadata?: Record<string, unknown>;
}
