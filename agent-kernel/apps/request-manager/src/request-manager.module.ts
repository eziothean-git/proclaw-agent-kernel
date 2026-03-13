import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { HttpModule } from '@nestjs/axios';
import { PersistenceService } from './services/persistence.service';
import { AuditLoggerService } from './services/audit-logger.service';
import { PriorityQueueService } from './services/priority-queue.service';
import { SessionAffinityService } from './services/session-affinity.service';
import { WorkerPoolService } from './services/worker-pool.service';
import { RetryHandlerService } from './services/retry-handler.service';
import { PriorityRequestManagerService } from './services/priority-request-manager.service';
import { RequestStateService } from './services/request-state.service';
import { RequestManagerGrpcServer } from './grpc/request-manager.server';
import { PrimePersonalityClient } from './grpc/prime-personality.client';

@Module({
  imports: [
    ConfigModule.forRoot({
      isGlobal: true,
      envFilePath: ['.env', '../.env', '../../.env'],
    }),
    HttpModule,
  ],
  providers: [
    PersistenceService,
    AuditLoggerService,
    PriorityQueueService,
    SessionAffinityService,
    WorkerPoolService,
    RetryHandlerService,
    PriorityRequestManagerService,
    RequestStateService,
    RequestManagerGrpcServer,
    PrimePersonalityClient,
  ],
  exports: [PriorityRequestManagerService],
})
export class RequestManagerModule {}