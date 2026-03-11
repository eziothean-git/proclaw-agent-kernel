import { Module, Global } from '@nestjs/common';
import { TelemetryService } from './telemetry.service';
import { TelemetryAggregatorService } from './telemetry-aggregator.service';
import { TelemetryController } from './telemetry.controller';

@Global()
@Module({
  providers: [TelemetryService, TelemetryAggregatorService],
  controllers: [TelemetryController],
  exports: [TelemetryService, TelemetryAggregatorService],
})
export class TelemetryModule {}
