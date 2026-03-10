import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import * as path from 'path';
import { RequestTask, ProcessResult } from '../interfaces';
import { GrpcError } from '../exceptions';

@Injectable()
export class PrimePersonalityClient implements OnModuleInit {
  private readonly logger = new Logger(PrimePersonalityClient.name);
  private client: any;
  private readonly protoPath: string;
  private readonly serviceUrl: string;

  constructor(private readonly configService: ConfigService) {
    // 尝试多个路径来找到 proto 文件
    const possiblePaths = [
      path.join(__dirname, '../../src/proto/prime-personality.proto'), // 开发模式 (ts-node)
      path.join(__dirname, '../../proto/prime-personality.proto'),     // 生产模式 (dist)
      path.join(process.cwd(), 'src/proto/prime-personality.proto'),   // 当前工作目录
      path.join(process.cwd(), 'proto/prime-personality.proto'),       // 备选
    ];
    
    this.protoPath = possiblePaths.find(p => {
      try {
        require('fs').accessSync(p);
        return true;
      } catch {
        return false;
      }
    }) || possiblePaths[0]; // 默认使用第一个路径
    
    this.serviceUrl = this.configService.get<string>('PRIME_PERSONALITY_GRPC_URL', 'localhost:50051');
  }

  async onModuleInit(): Promise<void> {
    try {
      const packageDefinition = protoLoader.loadSync(this.protoPath, {
        keepCase: false,  // 自动将 snake_case 转换为 camelCase
        longs: String,
        enums: String,
        defaults: true,
        oneofs: true,
      });

      const proto = grpc.loadPackageDefinition(packageDefinition) as any;
      const PrimePersonality = proto.primepersonality.PrimePersonality;

      this.client = new PrimePersonality(
        this.serviceUrl,
        grpc.credentials.createInsecure()
      );

      this.logger.log(`Prime Personality client initialized at ${this.serviceUrl}`);
    } catch (error) {
      this.logger.error(`Failed to initialize gRPC client: ${error.message}`);
      // 不抛出错误，允许服务继续启动
    }
  }

  async processRequest(task: RequestTask, timeoutMs: number): Promise<ProcessResult> {
    if (!this.client) {
      throw new Error('gRPC client not initialized');
    }

    // Validate timeoutMs to prevent "Invalid time value" error
    const validTimeoutMs = typeof timeoutMs === 'number' && !isNaN(timeoutMs) && timeoutMs > 0
      ? timeoutMs
      : 120000; // Default 2 minutes

    const deadline = new Date(Date.now() + validTimeoutMs);

    // Validate deadline is a valid date
    if (isNaN(deadline.getTime())) {
      this.logger.error(`Invalid deadline calculated: timeoutMs=${timeoutMs}, now=${Date.now()}`);
      throw new Error('Invalid deadline: unable to calculate valid timeout');
    }

    // Convert Date to protobuf Timestamp format
    const deadlineSeconds = Math.floor(deadline.getTime() / 1000);
    const deadlineNanos = (deadline.getTime() % 1000) * 1000000;

    const request = {
      requestId: task.requestId,
      sessionId: task.sessionId,
      userId: task.userId,
      priority: task.priority,
      body: task.body,
      context: {
        taskGoal: task.body.substring(0, 100),
        constraints: [],
        allowedCapabilities: [],
        workingMemory: Buffer.from(''),
        contextMetadata: task.metadata,
      },
      metadata: task.metadata,
      timeoutMs: validTimeoutMs,
      deadline: {
        seconds: deadlineSeconds.toString(),
        nanos: deadlineNanos,
      },
    };

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Prime Personality timeout after ${timeoutMs}ms`));
      }, timeoutMs);

      this.client.processRequest(request, (err: any, response: any) => {
        clearTimeout(timeout);
        
        if (err) {
          const code = err.code || grpc.status.UNKNOWN;
          reject(new GrpcError(err.message, code));
        } else {
          if (response.status === 3) { // FAILED
            const error = new Error(response.errorMessage || 'Processing failed');
            (error as any).category = response.errorCategory;
            (error as any).recoverable = response.recoverable;
            reject(error);
          } else {
            resolve({
              content: response.resultContent,
              actions: response.actions?.map((a: any) => ({
                type: a.type,
                skill: a.skill,
                tool: a.tool,
                status: a.status,
                durationMs: a.durationMs,
                result: a.result,
              })) || [],
              metrics: {
                totalDurationMs: response.metrics?.totalDurationMs,
                tokenCountInput: response.metrics?.tokenCountInput,
                tokenCountOutput: response.metrics?.tokenCountOutput,
                modelVersion: response.metrics?.modelVersion,
                llmCallsCount: response.metrics?.llmCallsCount,
              },
            });
          }
        }
      });
    });
  }

  async healthCheck(): Promise<{ healthy: boolean; version?: string }> {
    if (!this.client) {
      return { healthy: false };
    }

    return new Promise((resolve) => {
      const timeout = setTimeout(() => {
        resolve({ healthy: false });
      }, 5000);

      this.client.healthCheck({}, (err: any, response: any) => {
        clearTimeout(timeout);
        if (err) {
          resolve({ healthy: false });
        } else {
          resolve({
            healthy: response.healthy,
            version: response.version,
          });
        }
      });
    });
  }
}