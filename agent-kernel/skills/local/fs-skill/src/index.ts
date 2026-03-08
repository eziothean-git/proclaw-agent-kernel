import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import * as fs from 'fs/promises';
import * as path from 'path';
import { z } from 'zod';

// Tool input schemas
const ReadFileSchema = z.object({
  path: z.string().describe('Path to the file to read'),
});

const WriteFileSchema = z.object({
  path: z.string().describe('Path to the file to write'),
  content: z.string().describe('Content to write to the file'),
});

const ListDirectorySchema = z.object({
  path: z.string().describe('Path to the directory to list'),
});

class FileSystemSkill {
  private server: Server;
  private allowedPaths: string[];

  constructor() {
    this.allowedPaths = process.env.ALLOWED_PATHS?.split(',') || [process.cwd()];
    
    this.server = new Server(
      {
        name: 'fs-skill',
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
            name: 'read_file',
            description: 'Read the contents of a file',
            inputSchema: {
              type: 'object',
              properties: {
                path: {
                  type: 'string',
                  description: 'Path to the file',
                },
              },
              required: ['path'],
            },
          },
          {
            name: 'write_file',
            description: 'Write content to a file',
            inputSchema: {
              type: 'object',
              properties: {
                path: {
                  type: 'string',
                  description: 'Path to the file',
                },
                content: {
                  type: 'string',
                  description: 'Content to write',
                },
              },
              required: ['path', 'content'],
            },
          },
          {
            name: 'list_directory',
            description: 'List the contents of a directory',
            inputSchema: {
              type: 'object',
              properties: {
                path: {
                  type: 'string',
                  description: 'Path to the directory',
                },
              },
              required: ['path'],
            },
          },
        ],
      };
    });

    this.server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;

      try {
        switch (name) {
          case 'read_file': {
            const { path: filePath } = ReadFileSchema.parse(args);
            return await this.readFile(filePath);
          }
          case 'write_file': {
            const { path: filePath, content } = WriteFileSchema.parse(args);
            return await this.writeFile(filePath, content);
          }
          case 'list_directory': {
            const { path: dirPath } = ListDirectorySchema.parse(args);
            return await this.listDirectory(dirPath);
          }
          default:
            throw new Error(`Unknown tool: ${name}`);
        }
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

  private async readFile(filePath: string) {
    const resolvedPath = this.validatePath(filePath);
    const content = await fs.readFile(resolvedPath, 'utf-8');
    
    return {
      content: [
        {
          type: 'text',
          text: content,
        },
      ],
    };
  }

  private async writeFile(filePath: string, content: string) {
    const resolvedPath = this.validatePath(filePath);
    await fs.mkdir(path.dirname(resolvedPath), { recursive: true });
    await fs.writeFile(resolvedPath, content, 'utf-8');
    
    return {
      content: [
        {
          type: 'text',
          text: `Successfully wrote to ${filePath}`,
        },
      ],
    };
  }

  private async listDirectory(dirPath: string) {
    const resolvedPath = this.validatePath(dirPath);
    const entries = await fs.readdir(resolvedPath, { withFileTypes: true });
    
    const formatted = entries.map((entry) => {
      const icon = entry.isDirectory() ? '📁' : '📄';
      return `${icon} ${entry.name}`;
    });

    return {
      content: [
        {
          type: 'text',
          text: `Contents of ${dirPath}:\n${formatted.join('\n')}`,
        },
      ],
    };
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
    console.error('File System Skill running on stdio');
  }
}

async function main() {
  const skill = new FileSystemSkill();
  await skill.run();
}

main().catch(console.error);
