import { Injectable, Logger } from '@nestjs/common';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import { promises as fs } from 'fs';
import { exec as execCallback } from 'child_process';
import * as path from 'path';
import { promisify } from 'util';
import { KernelService } from '../kernel/kernel.service';

const execAsync = promisify(execCallback);

interface ToolCallRequest {
  session_id: string;
  request_id: string;
  skill_name: string;
  tool_name: string;
  parameters: Record<string, unknown>;
  timeout?: number;
}

interface ToolCallResult {
  success: boolean;
  result?: unknown;
  error?: string;
  executionTime: number;
}

interface PythonKernelRequest {
  session_id: string;
  user_id: string;
  message: string;
  request_id: string;
  callback_url?: string;
  context?: Record<string, unknown>;
}

@Injectable()
export class ExecutorService {
  private readonly logger = new Logger(ExecutorService.name);
  private mcpClients = new Map<string, Client>();
  private activeExecutions = new Map<string, AbortController>();
  private readonly blockedCommands = ['rm -rf /', 'mkfs', 'dd if=/dev/zero', '>:', ':(){ :|: & };:'];

  constructor(private readonly kernelService: KernelService) {}

  /**
   * Execute a request through the Python Kernel
   */
  async executeWithKernel(request: PythonKernelRequest): Promise<unknown> {
    this.logger.log(`Executing request ${request.request_id} via Python Kernel`);

    const response = await this.kernelService.execute({
      session_id: request.session_id,
      user_id: request.user_id,
      message: request.message,
      request_id: request.request_id,
      callback_url: request.callback_url ?? '',
      metadata: request.context,
    });

    this.logger.log(`Request ${request.request_id} dispatched to kernel with status: ${response.status}`);
    return response;
  }

  /**
   * Execute a tool call via MCP
   */
  async executeToolCall(request: ToolCallRequest): Promise<ToolCallResult> {
    const { request_id, skill_name, timeout = 30000 } = request;

    this.logger.log(`Executing tool call ${request_id}: ${skill_name}.${request.tool_name}`);

    const startTime = Date.now();
    const abortController = new AbortController();
    this.activeExecutions.set(request_id, abortController);

    try {
      // Set up timeout
      const timeoutHandle = setTimeout(() => {
        abortController.abort();
      }, timeout);

      // Get or create MCP client for skill
      const result = await this.executeSkill(request, abortController.signal);

      clearTimeout(timeoutHandle);

      const executionTime = Date.now() - startTime;
      
      return {
        success: true,
        result,
        executionTime,
      };
    } catch (error) {
      const executionTime = Date.now() - startTime;

      this.logger.error(`Tool call ${request_id} failed: ${error.message}`);

      return {
        success: false,
        error: error.message,
        executionTime,
      };
    } finally {
      this.activeExecutions.delete(request_id);
    }
  }

  /**
   * Cancel an ongoing execution
   */
  async cancelExecution(requestId: string): Promise<boolean> {
    const controller = this.activeExecutions.get(requestId);
    if (!controller) return false;

    controller.abort();
    this.activeExecutions.delete(requestId);
    this.logger.log(`Cancelled execution ${requestId}`);
    
    return true;
  }

  /**
   * Get or create MCP client for a skill
   */
  private async getMcpClient(skillName: string): Promise<Client<any, any, any>> {
    if (this.mcpClients.has(skillName)) {
      return this.mcpClients.get(skillName)!;
    }

    // TODO: Load skill configuration from database or config
    const skillEntrypoint = path.resolve(process.cwd(), 'skills', 'local', skillName, 'dist', 'index.js');
    const transport = new StdioClientTransport({
      command: 'node',
      args: [skillEntrypoint],
    });

    const client = new Client(
      { name: 'agent-kernel-gateway', version: '0.1.0' },
      { capabilities: { tools: {} } }
    );

    await client.connect(transport);
    this.mcpClients.set(skillName, client);
    
    this.logger.log(`Connected to MCP skill: ${skillName}`);
    return client;
  }

  /**
   * Execute a tool (simplified interface for controller)
   */
  async executeTool(
    skillName: string,
    toolName: string,
    args: Record<string, unknown>,
    requestId?: string,
  ): Promise<{ success: boolean; result?: unknown; error?: string; execution_time_ms?: number }> {
    const result = await this.executeToolCall({
      session_id: 'anonymous',
      request_id: requestId || `req-${Date.now()}`,
      skill_name: skillName,
      tool_name: toolName,
      parameters: args,
    });

    return {
      success: result.success,
      result: result.result,
      error: result.error,
      execution_time_ms: result.executionTime,
    };
  }

  /**
   * List available tools from a skill
   */
  async listTools(skillName: string): Promise<unknown[]> {
    try {
      if (skillName === 'fs-skill') {
        return [
          { name: 'read_file', description: 'Read the contents of a file', parameters: { path: 'string' } },
          { name: 'write_file', description: 'Write content to a file', parameters: { path: 'string', content: 'string' } },
          { name: 'list_directory', description: 'List the contents of a directory', parameters: { path: 'string' } },
        ];
      }

      if (skillName === 'shell-skill') {
        return [
          { name: 'execute_command', description: 'Execute a shell command with safety controls', parameters: { command: 'string', timeout: 'number', workingDir: 'string' } },
        ];
      }

      const client = await this.getMcpClient(skillName);
      const tools = await client.listTools();
      return tools.tools || [];
    } catch (error) {
      this.logger.error(`Failed to list tools for ${skillName}: ${error.message}`);
      return [];
    }
  }

  /**
   * List all available skills
   */
  async listSkills(): Promise<string[]> {
    // TODO: Load from database or config file
    // For now, return hardcoded list based on available skills
    return ['fs-skill', 'shell-skill'];
  }

  private async executeSkill(request: ToolCallRequest, signal: AbortSignal): Promise<unknown> {
    if (request.skill_name === 'fs-skill' || request.skill_name === 'shell-skill') {
      return this.executeLocalSkill(request, signal);
    }

    const client = await this.getMcpClient(request.skill_name);
    return client.callTool({
      name: request.tool_name,
      arguments: request.parameters,
    }, undefined, { signal });
  }

  private async executeLocalSkill(request: ToolCallRequest, signal: AbortSignal): Promise<unknown> {
    if (request.skill_name === 'fs-skill') {
      return this.executeLocalFsTool(request.tool_name, request.parameters);
    }

    if (request.skill_name === 'shell-skill') {
      return this.executeLocalShellTool(request.parameters, signal);
    }

    throw new Error(`Unsupported local skill: ${request.skill_name}`);
  }

  private async executeLocalFsTool(toolName: string, parameters: Record<string, unknown>): Promise<unknown> {
    const requestedPath = String(parameters.path || '');
    const resolvedPath = this.resolveAllowedPath(requestedPath);

    if (toolName === 'read_file') {
      const content = await fs.readFile(resolvedPath, 'utf-8');
      return { content: [{ type: 'text', text: content }] };
    }

    if (toolName === 'list_directory') {
      const entries = await fs.readdir(resolvedPath, { withFileTypes: true });
      return {
        content: [
          {
            type: 'text',
            text: entries.map((entry) => `${entry.isDirectory() ? '[dir]' : '[file]'} ${entry.name}`).join('\n'),
          },
        ],
      };
    }

    if (toolName === 'write_file') {
      const content = String(parameters.content || '');
      await fs.mkdir(path.dirname(resolvedPath), { recursive: true });
      await fs.writeFile(resolvedPath, content, 'utf-8');
      return { content: [{ type: 'text', text: `Successfully wrote to ${requestedPath}` }] };
    }

    throw new Error(`Unsupported fs tool: ${toolName}`);
  }

  private async executeLocalShellTool(parameters: Record<string, unknown>, signal: AbortSignal): Promise<unknown> {
    const command = String(parameters.command || '');
    if (this.blockedCommands.some((blocked) => command.includes(blocked))) {
      throw new Error('Command blocked for safety reasons');
    }

    const timeout = Number(parameters.timeout || 30) * 1000;
    const requestedWorkingDir = parameters.workingDir ? String(parameters.workingDir) : process.cwd();
    const workingDir = this.resolveAllowedPath(requestedWorkingDir);

    const { stdout, stderr } = await execAsync(command, {
      cwd: workingDir,
      timeout,
      maxBuffer: 1024 * 1024,
      signal,
    });

    return {
      content: [
        {
          type: 'text',
          text: [stdout ? `STDOUT:\n${stdout}` : '', stderr ? `STDERR:\n${stderr}` : ''].filter(Boolean).join('\n\n') || 'Command executed successfully (no output)',
        },
      ],
    };
  }

  private resolveAllowedPath(inputPath: string): string {
    const resolved = path.resolve(inputPath);
    const allowedPaths = (process.env.ALLOWED_PATHS?.split(',') || [path.resolve(process.cwd(), 'data'), process.cwd()]).map((allowed) => path.resolve(allowed));

    if (allowedPaths.some((allowed) => resolved.startsWith(allowed))) {
      return resolved;
    }

    throw new Error(`Path ${inputPath} is outside allowed directories`);
  }
}
