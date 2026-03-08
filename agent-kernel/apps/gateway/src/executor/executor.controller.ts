import { Controller, Post, Get, Body, Param, Logger } from '@nestjs/common';
import { ExecutorService } from './executor.service';
import { ToolExecuteRequestDto, ToolExecuteResponseDto, ToolInfo } from './dto/tool-execute.dto';

@Controller('api/v1/executor')
export class ExecutorController {
  private readonly logger = new Logger(ExecutorController.name);

  constructor(private readonly executorService: ExecutorService) {}

  @Post('execute')
  async executeTool(
    @Body() dto: ToolExecuteRequestDto,
  ): Promise<ToolExecuteResponseDto> {
    this.logger.log(`Executing tool ${dto.tool_name} from skill ${dto.skill_name}`);

    try {
      const result = await this.executorService.executeTool(
        dto.skill_name,
        dto.tool_name,
        dto.arguments,
        dto.request_id,
      );

      return {
        success: result.success,
        result: result.result,
        error: result.error,
        execution_time_ms: result.execution_time_ms,
      };
    } catch (error) {
      this.logger.error(`Failed to execute tool: ${error.message}`);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  @Post('cancel/:requestId')
  async cancelExecution(
    @Param('requestId') requestId: string,
  ): Promise<{ success: boolean }> {
    this.logger.log(`Cancelling execution ${requestId}`);

    try {
      const success = await this.executorService.cancelExecution(requestId);
      return { success };
    } catch (error) {
      this.logger.error(`Failed to cancel execution: ${error.message}`);
      return { success: false };
    }
  }

  @Get('tools/:skillName')
  async listTools(
    @Param('skillName') skillName: string,
  ): Promise<{ tools: ToolInfo[] }> {
    this.logger.log(`Listing tools for skill ${skillName}`);

    try {
      const tools = await this.executorService.listTools(skillName);
      return {
        tools: tools.map((tool: any) => ({
          name: tool.name,
          description: tool.description,
          parameters: tool.parameters,
        })),
      };
    } catch (error) {
      this.logger.error(`Failed to list tools: ${error.message}`);
      return { tools: [] };
    }
  }

  @Get('skills')
  async listSkills(): Promise<string[]> {
    this.logger.log('Listing all skills');

    try {
      const skills = await this.executorService.listSkills();
      return skills;
    } catch (error) {
      this.logger.error(`Failed to list skills: ${error.message}`);
      return [];
    }
  }
}
