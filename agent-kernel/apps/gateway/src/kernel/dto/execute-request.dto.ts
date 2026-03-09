export class ExecuteRequestDto {
  session_id: string;
  user_id: string;
  message: string;
  request_id: string;
  metadata?: Record<string, unknown>;
  callback_url: string;
}

export class ExecuteResponseDto {
  request_id: string;
  session_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  result?: any;
  error?: string;
  task_ids?: string[];
  processing_time_ms?: number;
  message?: string;
}
