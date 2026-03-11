import { Injectable, Logger } from '@nestjs/common';
import { Subject, Observable, filter, map } from 'rxjs';
import { TelemetryEvent, TelemetryConfig, TelemetryLevel } from './telemetry.types';

interface ClientSubscription {
  requestId: string;
  config: TelemetryConfig;
}

@Injectable()
export class TelemetryAggregatorService {
  private readonly logger = new Logger(TelemetryAggregatorService.name);
  private readonly eventSubject = new Subject<TelemetryEvent>();
  private readonly clientSubscriptions = new Map<string, ClientSubscription>();
  
  // 默认配置
  private readonly defaultConfig: TelemetryConfig = {
    level: 'standard',
    components: ['prime', 'session_host', 'scheduler', 'agent_thread'],
    include: {
      working_set: false,
      skill_calls: true,
      agent_output: true,
      reasoning: false,
      performance: true,
    },
    sample_rate: 1.0,
  };

  /**
   * 接收来自 Python Kernel 的遥测事件
   */
  async receiveEvent(event: TelemetryEvent): Promise<void> {
    // 验证事件
    if (!this.validateEvent(event)) {
      this.logger.warn(`Invalid telemetry event received: ${event?.request_id}`);
      return;
    }

    // 获取该请求的配置
    const config = await this.getConfig(event.request_id);
    
    // 根据配置过滤
    if (!this.shouldInclude(event, config)) {
      return;
    }

    // 推送到流
    this.eventSubject.next(event);
    
    this.logger.debug(
      `Telemetry event received: ${event.request_id} [${event.layer_name}] ${event.operation}`
    );
  }

  /**
   * 客户端订阅特定请求的遥测流
   */
  subscribeToRequest(
    requestId: string,
    clientConfig?: Partial<TelemetryConfig>
  ): Observable<TelemetryEvent> {
    const config = { ...this.defaultConfig, ...clientConfig };
    
    // 记录订阅
    this.clientSubscriptions.set(requestId, {
      requestId,
      config,
    });

    this.logger.log(`Client subscribed to telemetry stream: ${requestId}`);

    return this.eventSubject.pipe(
      filter(event => event.request_id === requestId),
      map(event => this.filterForClient(event, config))
    );
  }

  /**
   * 取消订阅
   */
  unsubscribeFromRequest(requestId: string): void {
    this.clientSubscriptions.delete(requestId);
    this.logger.log(`Client unsubscribed from telemetry stream: ${requestId}`);
  }

  /**
   * 获取请求的配置
   * 可以从 metadata 或持久化存储中读取
   */
  private async getConfig(requestId: string): Promise<TelemetryConfig> {
    const subscription = this.clientSubscriptions.get(requestId);
    if (subscription) {
      return subscription.config;
    }
    return this.defaultConfig;
  }

  /**
   * 验证遥测事件
   */
  private validateEvent(event: TelemetryEvent): boolean {
    return !!(
      event &&
      event.request_id &&
      event.trace_id &&
      event.timestamp &&
      event.layer &&
      event.component &&
      event.status
    );
  }

  /**
   * 根据配置决定是否包含此事件
   */
  private shouldInclude(event: TelemetryEvent, config: TelemetryConfig): boolean {
    // 级别检查
    const levelPriority: Record<TelemetryLevel, number> = {
      'minimal': 1,
      'standard': 2,
      'detailed': 3,
      'debug': 4,
    };

    const eventLevel = event.level || 'standard';
    if (levelPriority[eventLevel] > levelPriority[config.level]) {
      return false;
    }

    // 组件检查
    const componentMap: Record<string, string> = {
      'PrimePersonality': 'prime',
      'SessionHost': 'session_host',
      'Scheduler': 'scheduler',
      'AgentThread': 'agent_thread',
    };
    
    const componentType = componentMap[event.component] || event.component.toLowerCase();
    if (!config.components.includes(componentType as any)) {
      return false;
    }

    // 采样检查
    if (config.sample_rate < 1.0 && Math.random() > config.sample_rate) {
      return false;
    }

    return true;
  }

  /**
   * 根据客户端配置过滤事件内容
   */
  private filterForClient(
    event: TelemetryEvent,
    config: TelemetryConfig
  ): TelemetryEvent {
    // 如果不需要 payload，直接返回精简版
    if (!event.payload) {
      return event;
    }

    const filteredPayload: typeof event.payload = {};

    if (config.include.working_set && event.payload.saw) {
      filteredPayload.saw = event.payload.saw;
    }

    if (config.include.skill_calls && event.payload.did) {
      filteredPayload.did = event.payload.did;
    }

    if (config.include.agent_output && event.payload.wrote) {
      filteredPayload.wrote = event.payload.wrote;
    }

    if (config.include.reasoning && event.payload.thought) {
      filteredPayload.thought = event.payload.thought;
    }

    return {
      ...event,
      payload: Object.keys(filteredPayload).length > 0 ? filteredPayload : undefined,
    };
  }

  /**
   * 清理已完成的请求订阅
   */
  cleanupRequest(requestId: string): void {
    this.clientSubscriptions.delete(requestId);
  }
}
