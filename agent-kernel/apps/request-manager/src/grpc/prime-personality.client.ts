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

    const validTimeoutMs = typeof timeoutMs === 'number' && !isNaN(timeoutMs) && timeoutMs > 0
      ? timeoutMs
      : 120000;

    const request = {
      inputMessage: {
        header: {
          timestamp: new Date().toISOString(),
          platform: 'request-manager',
          deviceId: '',
          userId: task.userId,
          sessionId: task.sessionId,
          requestId: task.requestId,
          sourceIp: '',
          clientVersion: '1.0.0',
          priority: task.priority,
        },
        body: task.body,
        metadata: {
          attachments: [],
          tags: [],
        },
        context: {
          sessionId: task.sessionId,
          conversationHistory: [],
          windowSize: 10,
          fullContextPath: '',
          totalTurns: 0,
        },
      },
    };

    this.logger.log(`Sending gRPC request to Prime: requestId=${task.requestId}`);
    
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
            reject(error);
          } else {
            const ir = response.ir;
            const contentText = ir?.content?.text || '';
            
            resolve({
              content: contentText,
              actions: ir?.processes?.map((p: any) => ({
                type: 'process',
                skill: p.name,
                tool: p.capabilities?.[0] || '',
                status: 'completed',
                durationMs: 0,
                result: { goal: p.goal },
              })) || [],
              metrics: {
                totalDurationMs: 0,
                tokenCountInput: 0,
                tokenCountOutput: 0,
                modelVersion: '',
                llmCallsCount: 0,
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