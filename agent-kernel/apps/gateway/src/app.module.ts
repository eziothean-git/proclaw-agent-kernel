import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { GatewayModule } from './gateway/gateway.module';
import { RequestQueueModule } from './request-queue/request-queue.module';
import { SchedulerModule } from './scheduler/scheduler.module';
import { ExecutorModule } from './executor/executor.module';
import { RouterModule } from './router/router.module';
import { McpModule } from './mcp/mcp.module';
import { TelemetryModule } from './telemetry/telemetry.module';
import { KernelModule } from './kernel/kernel.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    TelemetryModule,
    KernelModule,
    GatewayModule,
    RequestQueueModule,
    SchedulerModule,
    ExecutorModule,
    RouterModule,
    McpModule,
  ],
})
export class AppModule {}
