import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { GatewayModule } from './gateway/gateway.module';
import { RouterModule } from './router/router.module';
import { CoreModule } from './core/core.module';
import { CliModule } from './platform-adapters/cli/cli.module';
import { SchedulerModule } from './scheduler/scheduler.module';

@Module({
  imports: [
    ConfigModule.forRoot({ isGlobal: true }),
    CoreModule,
    GatewayModule,
    RouterModule,
    CliModule,
    SchedulerModule,
  ],
})
export class AppModule {}
