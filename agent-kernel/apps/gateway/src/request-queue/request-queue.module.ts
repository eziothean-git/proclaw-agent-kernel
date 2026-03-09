import { Module } from '@nestjs/common';
import { RequestQueueService } from './request-queue.service';
import { RouterModule } from '../router/router.module';

/**
 * @deprecated This module is deprecated. Gateway now uses filesystem mailbox pattern.
 * Requests are written directly to StorageService (inbox) instead of using in-memory queue.
 */
@Module({
  imports: [RouterModule],
  providers: [RequestQueueService],
  exports: [RequestQueueService],
})
export class RequestQueueModule {}
