import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { GatewayController } from './gateway.controller';
import { GatewayService } from './gateway.service';
import { WebhookController } from './webhook.controller';
import { SseController } from './sse.controller';
import { RouterModule } from '../router/router.module';
import { CoreModule } from '../core/core.module';
import { KernelModule } from '../kernel/kernel.module';
import { RequestManagerClient } from '../grpc/request-manager.client';
import { RawRequestStorageService } from '../raw-request/raw-request-storage.service';

@Module({
  imports: [CoreModule, RouterModule, KernelModule, HttpModule],
  controllers: [GatewayController, WebhookController, SseController],
  providers: [GatewayService, RequestManagerClient, RawRequestStorageService],
  exports: [GatewayService, RequestManagerClient, RawRequestStorageService],
})
export class GatewayModule {}
