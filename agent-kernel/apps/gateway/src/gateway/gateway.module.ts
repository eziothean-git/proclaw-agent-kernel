import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { GatewayController } from './gateway.controller';
import { GatewayService } from './gateway.service';
import { WebhookController } from './webhook.controller';
import { RouterModule } from '../router/router.module';
import { CoreModule } from '../core/core.module';
import { KernelModule } from '../kernel/kernel.module';

@Module({
  imports: [CoreModule, RouterModule, KernelModule, HttpModule],
  controllers: [GatewayController, WebhookController],
  providers: [GatewayService],
  exports: [GatewayService],
})
export class GatewayModule {}
