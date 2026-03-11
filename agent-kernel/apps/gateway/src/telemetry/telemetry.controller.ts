import { Controller, Post, Body, Logger } from '@nestjs/common';
import { ApiOperation, ApiTags } from '@nestjs/swagger';
import { TelemetryAggregatorService } from './telemetry-aggregator.service';
import { TelemetryEvent } from './telemetry.types';

@ApiTags('telemetry')
@Controller('v1/telemetry')
export class TelemetryController {
  private readonly logger = new Logger(TelemetryController.name);

  constructor(private readonly telemetryAggregator: TelemetryAggregatorService) {}

  @Post('event')
  @ApiOperation({ summary: 'Receive telemetry event from Python Kernel' })
  async receiveEvent(@Body() event: TelemetryEvent): Promise<{ success: boolean }> {
    try {
      await this.telemetryAggregator.receiveEvent(event);
      return { success: true };
    } catch (error) {
      this.logger.error(`Failed to process telemetry event: ${error.message}`);
      return { success: false };
    }
  }

  @Post('batch')
  @ApiOperation({ summary: 'Receive batch telemetry events from Python Kernel' })
  async receiveBatch(@Body() events: { events: TelemetryEvent[] }): Promise<{ 
    success: boolean; 
    processed: number;
    failed: number;
  }> {
    let processed = 0;
    let failed = 0;

    for (const event of events.events) {
      try {
        await this.telemetryAggregator.receiveEvent(event);
        processed++;
      } catch (error) {
        this.logger.error(`Failed to process telemetry event: ${error.message}`);
        failed++;
      }
    }

    return { 
      success: failed === 0, 
      processed, 
      failed 
    };
  }
}
