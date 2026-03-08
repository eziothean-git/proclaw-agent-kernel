export class ToolExecuteRequestDto {
  skill_name: string;
  tool_name: string;
  arguments: Record<string, any>;
  request_id?: string;
}

export class ToolExecuteResponseDto {
  success: boolean;
  result?: any;
  error?: string;
  execution_time_ms?: number;
}

export class ToolInfo {
  name: string;
  description: string;
  parameters: any;
}
