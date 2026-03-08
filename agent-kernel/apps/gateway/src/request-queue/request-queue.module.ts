import { Module } from '@nestjs/common';
import { RequestQueueService } from './request-queue.service';
import { KernelModule } from '../kernel/kernel.module';
import { RouterModule } from '../router/router.module';

@Module({
  imports: [KernelModule, RouterModule],
  providers: [RequestQueueService],
  exports: [RequestQueueService],
})
export class RequestQueueModule {}
