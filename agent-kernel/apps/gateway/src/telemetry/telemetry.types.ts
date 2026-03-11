/**
 * Telemetry Types - 遥测事件类型定义
 */

export type TelemetryLevel = 'minimal' | 'standard' | 'detailed' | 'debug';

export interface TelemetryConfig {
  level: TelemetryLevel;
  components: ('prime' | 'session_host' | 'scheduler' | 'agent_thread')[];
  include: {
    working_set: boolean;   // Agent 看到的
    skill_calls: boolean;   // Agent 做的
    agent_output: boolean;  // Agent 写的
    reasoning: boolean;     // Agent 思考的
    performance: boolean;   // 性能指标
  };
  sample_rate: number;      // 0.0 - 1.0
}

export interface TelemetryEvent {
  // 元数据
  trace_id: string;
  request_id: string;
  session_id?: string;
  timestamp: string;
  level?: TelemetryLevel;
  
  // 位置信息
  layer: number;              // 1-7
  layer_name: string;         // "Prime", "SessionHost", "AgentThread"
  component: string;          // 具体组件名
  operation: string;          // 操作名
  phase?: string;             // "explore" | "execute" | "complete"
  
  // 状态
  status: 'start' | 'progress' | 'complete' | 'error';
  progress_pct?: number;
  message?: string;
  
  // Agent 工作详情
  payload?: {
    // Agent 看到的
    saw?: {
      working_set_summary: string;
      context_size: number;
      key_points?: string[];
    };
    
    // Agent 做的
    did?: {
      skill_name: string;
      params: Record<string, any>;
      execution_time_ms: number;
      result_status: 'success' | 'error';
    };
    
    // Agent 写的
    wrote?: {
      output_type: 'action' | 'thought' | 'final_answer';
      content: string;
    };
    
    // Agent 思考的
    thought?: {
      reasoning: string;
      plan?: string[];
      confidence?: number;
    };
  };
  
  // 性能指标
  metrics?: {
    elapsed_ms: number;
    llm_calls?: number;
    tokens_in?: number;
    tokens_out?: number;
  };
  
  // 子线程信息 (如果是 Session Host 或 Scheduler)
  sub_threads?: {
    thread_id: string;
    status: string;
    progress_pct: number;
    current_phase?: string;
  }[];
}

// 从 Gateway 发送到客户端的 SSE 事件
export interface TelemetryStreamEvent {
  type: 'telemetry' | 'complete' | 'error' | 'heartbeat';
  timestamp: string;
  requestId: string;
  data?: TelemetryEvent;
  error?: string;
}
