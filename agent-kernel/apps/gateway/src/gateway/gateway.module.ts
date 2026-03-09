import { Module } from '@nestjs/common';
import { GatewayController } from './gateway.controller';
import { GatewayService } from './gateway.service';
import { WebhookController } from './webhook.controller';
import { RouterModule } from '../router/router.module';
import { CoreModule } from '../core/core.module';

@Module({
  imports: [CoreModule, RouterModule],
  controllers: [GatewayController, WebhookController],
  providers: [GatewayService],
  exports: [GatewayService],
})
export class GatewayModule {}
