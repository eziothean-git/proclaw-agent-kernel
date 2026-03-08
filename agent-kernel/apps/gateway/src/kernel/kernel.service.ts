import { Injectable, Logger, HttpException, HttpStatus } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { AxiosError } from 'axios';
import { ExecuteRequestDto, ExecuteResponseDto } from './dto/execute-request.dto';

@Injectable()
export class KernelService {
  private readonly logger = new Logger(KernelService.name);
  private readonly kernelUrl: string;
  private readonly timeout: number;

  constructor(private readonly httpService: HttpService) {
    this.kernelUrl = process.env.PYTHON_KERNEL_URL || 'http://localhost:8000';
    this.timeout = parseInt(process.env.PYTHON_KERNEL_TIMEOUT || '30000', 10);
    this.logger.log(`KernelService initialized with URL: ${this.kernelUrl}`);
  }

  /**
   * Execute a request in Python Kernel
   */
  async execute(dto: ExecuteRequestDto): Promise<ExecuteResponseDto> {
    const url = `${this.kernelUrl}/v1/execute`;
    
    this.logger.log(`Executing request ${dto.request_id} for session ${dto.session_id}`);

    try {
      const response: any = await firstValueFrom(
        this.httpService.post<ExecuteResponseDto>(url, dto, {
          timeout: this.timeout,
          headers: {
            'Content-Type': 'application/json',
          },
        })
      );

      this.logger.log(`Request ${dto.request_id} completed with status: ${response.data?.status}`);
      return response.data as ExecuteResponseDto;

    } catch (error) {
      if (error instanceof AxiosError) {
        if (error.code === 'ECONNREFUSED') {
          this.logger.error(`Python Kernel unavailable at ${this.kernelUrl}`);
          throw new HttpException(
            'Python Kernel unavailable',
            HttpStatus.SERVICE_UNAVAILABLE
          );
        }
        
        if (error.code === 'ETIMEDOUT' || error.code === 'ECONNABORTED') {
          this.logger.error(`Request ${dto.request_id} timed out after ${this.timeout}ms`);
          throw new HttpException(
            'Request timeout',
            HttpStatus.REQUEST_TIMEOUT
          );
        }

        if (error.response) {
          this.logger.error(`Python Kernel returned error: ${error.response.status} - ${error.response.data}`);
          throw new HttpException(
            error.response.data?.error || 'Internal server error',
            error.response.status || HttpStatus.INTERNAL_SERVER_ERROR
          );
        }
      }

      this.logger.error(`Unexpected error: ${error.message}`);
      throw new HttpException(
        'Failed to execute request',
        HttpStatus.INTERNAL_SERVER_ERROR
      );
    }
  }

  /**
   * Get session status from Python Kernel
   */
  async getSessionStatus(sessionId: string): Promise<any> {
    const url = `${this.kernelUrl}/v1/sessions/${sessionId}/status`;
    
    this.logger.debug(`Getting status for session ${sessionId}`);

    try {
      const response: any = await firstValueFrom(
        this.httpService.get(url, {
          timeout: 5000, // Shorter timeout for status checks
        })
      );

      return response.data as any;

    } catch (error) {
      if (error instanceof AxiosError) {
        if (error.code === 'ECONNREFUSED') {
          this.logger.error('Python Kernel unavailable');
          throw new HttpException(
            'Python Kernel unavailable',
            HttpStatus.SERVICE_UNAVAILABLE
          );
        }

        if (error.response?.status === 404) {
          this.logger.warn(`Session ${sessionId} not found in Python Kernel`);
          return null;
        }
      }

      this.logger.error(`Failed to get session status: ${error.message}`);
      throw new HttpException(
        'Failed to get session status',
        HttpStatus.INTERNAL_SERVER_ERROR
      );
    }
  }

  /**
   * Get task status from Python Kernel
   */
  async getTaskStatus(taskId: string): Promise<any> {
    const url = `${this.kernelUrl}/v1/tasks/${taskId}`;
    
    this.logger.debug(`Getting status for task ${taskId}`);

    try {
      const response: any = await firstValueFrom(
        this.httpService.get(url, {
          timeout: 5000,
        })
      );

      return response.data as any;

    } catch (error) {
      if (error instanceof AxiosError) {
        if (error.code === 'ECONNREFUSED') {
          this.logger.error('Python Kernel unavailable');
          throw new HttpException(
            'Python Kernel unavailable',
            HttpStatus.SERVICE_UNAVAILABLE
          );
        }

        if (error.response?.status === 404) {
          this.logger.warn(`Task ${taskId} not found in Python Kernel`);
          return null;
        }
      }

      this.logger.error(`Failed to get task status: ${error.message}`);
      throw new HttpException(
        'Failed to get task status',
        HttpStatus.INTERNAL_SERVER_ERROR
      );
    }
  }

  /**
   * Health check for Python Kernel
   */
  async healthCheck(): Promise<boolean> {
    const url = `${this.kernelUrl}/health`;
    
    try {
      const response: any = await firstValueFrom(
        this.httpService.get(url, {
          timeout: 5000,
        })
      );

      return response.status === 200;

    } catch (error) {
      this.logger.warn(`Health check failed: ${error.message}`);
      return false;
    }
  }
}
