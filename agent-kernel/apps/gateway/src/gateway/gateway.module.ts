import { Module } from '@nestjs/common';
import { GatewayController } from './gateway.controller';
import { GatewayService } from './gateway.service';
import { RequestQueueModule } from '../request-queue/request-queue.module';
import { RouterModule } from '../router/router.module';
import { KernelModule } from '../kernel/kernel.module';

@Module({
  imports: [
    RequestQueueModule,
    RouterModule,
    KernelModule,
  ],
  controllers: [GatewayController],
  providers: [GatewayService],
  exports: [GatewayService],
})
export class GatewayModule {}
