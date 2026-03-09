export interface ExternalMessage {
  message: string;
  userId: string;
  platform: string;
  deviceId: string;
  sessionId?: string;
  attachments?: Array<{
    buffer: Buffer;
    originalName: string;
    mimeType: string;
  }>;
  metadata?: {
    sourceIp?: string;
    clientVersion?: string;
    tags?: string[];
  };
}

export interface CompiledOutput {
  text: string;
  attachments?: Array<{
    path: string;
    mimeType: string;
    description?: string;
  }>;
  metadata?: Record<string, unknown>;
}

export interface RequestContext {
  requestId: string;
  sessionId?: string;
  userId: string;
  platform: string;
  connectionType?: string;
  socketId?: string;
}

export interface PlatformAdapter {
  readonly platform: string;
  
  // 接收外部消息
  onMessage(handler: (msg: ExternalMessage) => Promise<void>): void;
  
  // 发送回复给用户
  sendResponse(context: RequestContext, output: CompiledOutput): Promise<void>;
  
  // 平台特定格式编译
  compileForPlatform(ir: unknown): CompiledOutput;
  
  // 健康检查
  healthCheck(): Promise<boolean>;
}
