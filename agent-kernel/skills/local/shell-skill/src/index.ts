import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { exec } from 'child_process';
import { promisify } from 'util';
import { z } from 'zod';
import * as path from 'path';

const execAsync = promisify(exec);

// Tool input schemas
const ExecuteCommandSchema = z.object({
  command: z.string().describe('Shell command to execute'),
  timeout: z.number().optional().describe('Timeout in seconds (default: 30)'),
  workingDir: z.string().optional().describe('Working directory for execution'),
});

class ShellSkill {
  private server: Server;
  private blockedCommands: string[];
  private allowedPaths: string[];

  constructor() {
    this.blockedCommands = [
      'rm -rf /',
      'mkfs',
      'dd if=/dev/zero',
      '>:',
      ':(){ :|: & };:',
    ];
    
    this.allowedPaths = process.env.ALLOWED_PATHS?.split(',') || [process.cwd()];
    
    this.server = new Server(
      {
        name: 'shell-skill',
        version: '0.1.0',
      },
      {
        capabilities: {
          tools: {},
        },
      }
    );

    this.setupToolHandlers();
  }

  private setupToolHandlers(): void {
    this.server.setRequestHandler(ListToolsRequestSchema, async () => {
      return {
        tools: [
          {
            name: 'execute_command',
            description: 'Execute a shell command with safety controls',
            inputSchema: {
              type: 'object',
              properties: {
                command: {
                  type: 'string',
                  description: 'Shell command to execute',
                },
                timeout: {
                  type: 'number',
                  description: 'Timeout in seconds (default: 30)',
                },
                workingDir: {
                  type: 'string',
                  description: 'Working directory for execution',
                },
              },
              required: ['command'],
            },
          },
        ],
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        if (name === 'execute_command') {
          const { command, timeout, workingDir } = ExecuteCommandSchema.parse(args);
          return await this.executeCommand(command, timeout, workingDir);
        }
        throw new Error(`Unknown tool: ${name}`);
      } catch (error) {
        return {
          content: [
            {
              type: 'text',
              text: `Error: ${error instanceof Error ? error.message : String(error)}`,
            },
          ],
          isError: true,
        };
      }
    });
  }

  private async executeCommand(
    command: string,
    timeout = 30,
    workingDir?: string
  ) {
    // Safety check
    if (this.isBlocked(command)) {
      throw new Error('Command blocked for safety reasons');
    }

    // Validate working directory
    const cwd = workingDir ? this.validatePath(workingDir) : process.cwd();

    try {
      const { stdout, stderr } = await execAsync(command, {
        timeout: timeout * 1000,
        cwd,
        maxBuffer: 1024 * 1024, // 1MB buffer
      });

      let output = '';
      if (stdout) {
        output += `STDOUT:\n${stdout}\n`;
      }
      if (stderr) {
        output += `STDERR:\n${stderr}\n`;
      }

      return {
        content: [
          {
            type: 'text',
            text: output || 'Command executed successfully (no output)',
          },
        ],
      };
    } catch (error) {
      if (error instanceof Error) {
        // Handle timeout
        if (error.message.includes('ETIMEDOUT')) {
          throw new Error(`Command timed out after ${timeout} seconds`);
        }
        throw error;
      }
      throw new Error(String(error));
    }
  }

  private isBlocked(command: string): boolean {
    return this.blockedCommands.some((blocked) => command.includes(blocked));
  }

  private validatePath(inputPath: string): string {
    const resolved = path.resolve(inputPath);
    
    for (const allowed of this.allowedPaths) {
      const allowedResolved = path.resolve(allowed);
      if (resolved.startsWith(allowedResolved)) {
        return resolved;
      }
    }
    
    throw new Error(`Path ${inputPath} is outside allowed directories`);
  }

  async run(): Promise<void> {
    const transport = new StdioServerTransport();
    await this.server.connect(transport);
    console.error('Shell Skill running on stdio');
  }
}

async function main() {
  const skill = new ShellSkill();
  await skill.run();
}

main().catch(console.error);
