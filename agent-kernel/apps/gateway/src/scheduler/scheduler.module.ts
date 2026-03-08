import { Module } from '@nestjs/common';
import { SchedulerService } from './scheduler.service';
import { RequestQueueModule } from '../request-queue/request-queue.module';

@Module({
  imports: [RequestQueueModule],
  providers: [SchedulerService],
  exports: [SchedulerService],
})
export class SchedulerModule {}
