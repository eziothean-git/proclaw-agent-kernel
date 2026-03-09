import { Injectable, Logger, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { CronJob } from 'cron';
import { GatewayService } from '../gateway/gateway.service';

interface ScheduledTask {
  id: string;
  sessionId: string;
  userId: string;
  message: string;
  cronExpression?: string;
  executeAt?: Date;
  isHookCreated: boolean;
  priority: number;
  createdAt: Date;
}

@Injectable()
export class SchedulerService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(SchedulerService.name);
  private cronJobs = new Map<string, CronJob>();
  private scheduledTasks = new Map<string, ScheduledTask>();
  private timeoutHandles = new Map<string, NodeJS.Timeout>();

  constructor(private readonly gatewayService: GatewayService) {}

  onModuleInit() {
    this.logger.log('Scheduler service initialized');
  }

  onModuleDestroy() {
    // Clean up all cron jobs
    this.cronJobs.forEach(job => job.stop());
    this.cronJobs.clear();

    // Clean up all timeouts
    this.timeoutHandles.forEach(handle => clearTimeout(handle));
    this.timeoutHandles.clear();

    this.logger.log('Scheduler service destroyed');
  }

  /**
   * Schedule a one-time task
   */
  async scheduleOnce(
    sessionId: string,
    userId: string,
    message: string,
    executeAt: Date,
    isHookCreated: boolean = false,
  ): Promise<ScheduledTask> {
    const task: ScheduledTask = {
      id: this.generateId(),
      sessionId,
      userId,
      message,
      executeAt,
      isHookCreated,
      priority: isHookCreated ? 1 : 0,
      createdAt: new Date(),
    };

    this.scheduledTasks.set(task.id, task);

    const delay = executeAt.getTime() - Date.now();

    if (delay <= 0) {
      this.logger.warn(`Task ${task.id} scheduled in the past, executing immediately`);
      void this.executeTask(task);
    } else {
      this.logger.log(`Scheduled task ${task.id} for ${executeAt.toISOString()}`);
      const handle = setTimeout(() => void this.executeTask(task), delay);
      this.timeoutHandles.set(task.id, handle);
    }

    return task;
  }

  /**
   * Schedule a recurring task using cron expression
   */
  async scheduleRecurring(
    sessionId: string,
    userId: string,
    message: string,
    cronExpression: string,
    isHookCreated: boolean = false,
  ): Promise<ScheduledTask> {
    const task: ScheduledTask = {
      id: this.generateId(),
      sessionId,
      userId,
      message,
      cronExpression,
      isHookCreated,
      priority: isHookCreated ? 1 : 0,
      createdAt: new Date(),
    };

    this.scheduledTasks.set(task.id, task);

    const job = new CronJob(cronExpression, () => {
      void this.executeTask(task);
    });

    this.cronJobs.set(task.id, job);
    job.start();

    this.logger.log(`Scheduled recurring task ${task.id} with cron: ${cronExpression}`);
    return task;
  }

  /**
   * Cancel a scheduled task
   */
  async cancelTask(taskId: string): Promise<boolean> {
    const task = this.scheduledTasks.get(taskId);
    if (!task) return false;

    const timeoutHandle = this.timeoutHandles.get(taskId);
    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
      this.timeoutHandles.delete(taskId);
    }

    const cronJob = this.cronJobs.get(taskId);
    if (cronJob) {
      cronJob.stop();
      this.cronJobs.delete(taskId);
    }

    this.scheduledTasks.delete(taskId);
    this.logger.log(`Cancelled scheduled task ${taskId}`);

    return true;
  }

  /**
   * Get all scheduled tasks for a session
   */
  async getSessionTasks(sessionId: string): Promise<ScheduledTask[]> {
    return Array.from(this.scheduledTasks.values()).filter(
      task => task.sessionId === sessionId,
    );
  }

  /**
   * Execute a scheduled task by submitting it to GatewayService (filesystem mailbox)
   */
  private async executeTask(task: ScheduledTask): Promise<void> {
    this.logger.log(`Executing scheduled task ${task.id} for session ${task.sessionId}`);

    try {
      await this.gatewayService.handleChatRequest({
        sessionId: task.sessionId,
        userId: task.userId,
        message: task.message,
        platform: 'scheduler',
        deviceId: `scheduler-${task.id}`,
        metadata: {
          isHookCreated: task.isHookCreated,
          scheduledTaskId: task.id,
          priority: task.priority,
        },
      });

      this.logger.log(`Scheduled task ${task.id} submitted to gateway mailbox`);

      // If one-time task, clean up
      if (!task.cronExpression) {
        this.scheduledTasks.delete(task.id);
        this.timeoutHandles.delete(task.id);
      }
    } catch (error) {
      this.logger.error(`Failed to execute scheduled task ${task.id}: ${error.message}`);
    }
  }

  private generateId(): string {
    return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }
}
