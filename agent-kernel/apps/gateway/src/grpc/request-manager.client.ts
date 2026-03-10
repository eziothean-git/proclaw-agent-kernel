import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import * as path from 'path';
import { InputMessage } from '../core/storage.service';

interface SubmitRequestRequest {
  requestId: string;
  sessionId: string;
  userId: string;
  priority: number;
  body: string;
  metadata: { [key: string]: string };
}

interface SubmitRequestResponse {
  requestId: string;
  status: number;
  queuePosition: number;
  estimatedWaitMs: number;
  message: string;
}

interface GetRequestStatusRequest {
  requestId: string;
}

interface GetRequestStatusResponse {
  requestId: string;
  sessionId: string;
  status: number;
  progressPercent: number;
  waitTimeMs: number;
  processingTimeMs: number;
  retryCount: number;
  errorMessage: string;
  startedAt: string;
  completedAt: string;
}

interface CancelRequestRequest {
  requestId: string;
}

interface CancelRequestResponse {
  requestId: string;
  success: boolean;
  message: string;
}

@Injectable()
export class RequestManagerClient implements OnModuleInit {
  private readonly logger = new Logger(RequestManagerClient.name);
  private client: any;
  private readonly grpcUrl: string;
  private readonly protoPath: string;

  constructor(private readonly configService: ConfigService) {
    this.grpcUrl = this.configService.get<string>('REQUEST_MANAGER_GRPC_URL', 'localhost:50052');
    // 尝试多个路径来找到 proto 文件
    const possiblePaths = [
      path.join(__dirname, 'proto/request-manager.proto'),           // 开发模式
      path.join(process.cwd(), 'src/grpc/proto/request-manager.proto'), // 备选
      path.join(process.cwd(), 'dist/grpc/proto/request-manager.proto'), // 生产模式
    ];
    
    const fs = require('fs');
    this.protoPath = possiblePaths.find(p => {
      try {
        fs.accessSync(p);
        return true;
      } catch {
        return false;
      }
    }) || possiblePaths[0];
  }

  onModuleInit(): void {
    this.initializeClient();
  }

  private initializeClient(): void {
    try {
      const packageDefinition = protoLoader.loadSync(this.protoPath, {
        keepCase: false,
        longs: String,
        enums: String,
        defaults: true,
        oneofs: true,
      });

      const proto = grpc.loadPackageDefinition(packageDefinition) as any;
      const RequestManagerService = proto.requestmanager.RequestManager;

      this.client = new RequestManagerService(
        this.grpcUrl,
        grpc.credentials.createInsecure()
      );

      this.logger.log(`Request Manager gRPC client initialized at ${this.grpcUrl}`);
    } catch (error) {
      this.logger.error(`Failed to initialize gRPC client: ${error.message}`);
      throw error;
    }
  }

  /**
   * Submit a request to Request Manager
   * @param inputIR - The InputMessage (IR) to submit
   * @param priority - Priority level (0=P0 to 4=P4)
   * @returns Promise with submission response
   */
  async submitRequest(
    inputIR: InputMessage,
    priority: number = 3
  ): Promise<SubmitRequestResponse> {
    return new Promise((resolve, reject) => {
      // Convert InputMessage to JSON string for body
      const irBody = JSON.stringify(inputIR);
      
      // Convert metadata to string map
      const metadata: { [key: string]: string } = {};
      if (inputIR.metadata) {
        if (inputIR.metadata.tags) {
          metadata.tags = JSON.stringify(inputIR.metadata.tags);
        }
        if (inputIR.metadata.attachments) {
          metadata.attachments = JSON.stringify(inputIR.metadata.attachments);
        }
      }

      const request: SubmitRequestRequest = {
        requestId: inputIR.header.requestId,
        sessionId: inputIR.header.sessionId || '',
        userId: inputIR.header.userId,
        priority: priority,
        body: irBody,
        metadata: metadata,
      };

      this.client.submitRequest(request, (error: grpc.ServiceError | null, response: SubmitRequestResponse) => {
        if (error) {
          this.logger.error(`Failed to submit request: ${error.message}`);
          reject(error);
          return;
        }
        resolve(response);
      });
    });
  }

  /**
   * Get request status from Request Manager
   * @param requestId - The request ID to query
   * @returns Promise with status response
   */
  async getRequestStatus(requestId: string): Promise<GetRequestStatusResponse> {
    return new Promise((resolve, reject) => {
      const request: GetRequestStatusRequest = { requestId };

      this.client.getRequestStatus(request, (error: grpc.ServiceError | null, response: GetRequestStatusResponse) => {
        if (error) {
          this.logger.error(`Failed to get request status: ${error.message}`);
          reject(error);
          return;
        }
        resolve(response);
      });
    });
  }

  /**
   * Cancel a request in Request Manager
   * @param requestId - The request ID to cancel
   * @returns Promise with cancellation response
   */
  async cancelRequest(requestId: string): Promise<CancelRequestResponse> {
    return new Promise((resolve, reject) => {
      const request: CancelRequestRequest = { requestId };

      this.client.cancelRequest(request, (error: grpc.ServiceError | null, response: CancelRequestResponse) => {
        if (error) {
          this.logger.error(`Failed to cancel request: ${error.message}`);
          reject(error);
          return;
        }
        resolve(response);
      });
    });
  }

  /**
   * Check if client is connected
   * @returns boolean indicating connection status
   */
  isConnected(): boolean {
    return this.client !== undefined && this.client !== null;
  }
}
