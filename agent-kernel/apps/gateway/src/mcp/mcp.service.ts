import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';
import * as fs from 'fs';
import * as path from 'path';

interface SkillConfig {
  name: string;
  command: string;
  args: string[];
  env?: Record<string, string>;
}

interface ToolInfo {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

@Injectable()
export class McpService implements OnModuleInit {
  private readonly logger = new Logger(McpService.name);
  private clients = new Map<string, Client>();
  private skillConfigs: SkillConfig[] = [
    {
      name: 'fs-skill',
      command: 'node',
      args: [path.resolve(process.cwd(), 'skills', 'local', 'fs-skill', 'dist', 'index.js')],
    },
    {
      name: 'shell-skill',
      command: 'node',
      args: [path.resolve(process.cwd(), 'skills', 'local', 'shell-skill', 'dist', 'index.js')],
    },
  ];

  async onModuleInit() {
    this.logger.log('Initializing MCP clients...');
    await this.connectAllSkills();
  }

  /**
   * Connect to all configured skills
   */
  private async connectAllSkills(): Promise<void> {
    for (const config of this.skillConfigs) {
      try {
        await this.connectSkill(config);
      } catch (error) {
        this.logger.error(`Failed to connect to skill ${config.name}: ${error.message}`);
      }
    }
  }

  /**
   * Connect to a specific skill
   */
  private async connectSkill(config: SkillConfig): Promise<void> {
    this.logger.log(`Connecting to skill: ${config.name}`);

    const entrypoint = config.args[0];
    if (!fs.existsSync(entrypoint)) {
      this.logger.warn(`Skipping skill ${config.name}; entrypoint not found at ${entrypoint}`);
      return;
    }

    const transport = new StdioClientTransport({
      command: config.command,
      args: config.args,
      env: config.env,
    });

    const client = new Client(
      { name: 'agent-kernel-gateway', version: '0.1.0' },
      { capabilities: { tools: {}, resources: {}, prompts: {} } }
    );

    await client.connect(transport);
    this.clients.set(config.name, client);

    this.logger.log(`Successfully connected to skill: ${config.name}`);
  }

  /**
   * Get client for a skill
   */
  getClient(skillName: string): Client | undefined {
    return this.clients.get(skillName);
  }

  /**
   * List all connected skills
   */
  getConnectedSkills(): string[] {
    return Array.from(this.clients.keys());
  }

  /**
   * List tools available from a skill
   */
  async listTools(skillName: string): Promise<ToolInfo[]> {
    const client = this.clients.get(skillName);
    if (!client) {
      throw new Error(`Skill not found: ${skillName}`);
    }

    const result = await client.listTools();
    return result.tools.map(tool => ({
      name: tool.name,
      description: tool.description || '',
      parameters: tool.inputSchema,
    }));
  }

  /**
   * Call a tool on a skill
   */
  async callTool(
    skillName: string,
    toolName: string,
    parameters: Record<string, unknown>
  ): Promise<unknown> {
    const client = this.clients.get(skillName);
    if (!client) {
      throw new Error(`Skill not found: ${skillName}`);
    }

    this.logger.log(`Calling tool ${toolName} on skill ${skillName}`);

    const result = await client.callTool({
      name: toolName,
      arguments: parameters,
    });

    return result;
  }

  /**
   * Disconnect all skills
   */
  async disconnectAll(): Promise<void> {
    this.logger.log('Disconnecting all MCP clients...');
    
    for (const [name, client] of this.clients) {
      try {
        await client.close();
        this.logger.log(`Disconnected from skill: ${name}`);
      } catch (error) {
        this.logger.error(`Error disconnecting from ${name}: ${error.message}`);
      }
    }
    
    this.clients.clear();
  }
}
