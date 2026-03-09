import { Module, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { CliAdapter } from './cli.adapter';

@Module({
  providers: [CliAdapter],
  exports: [CliAdapter],
})
export class CliModule implements OnModuleInit, OnModuleDestroy {
  constructor(private readonly cliAdapter: CliAdapter) {}

  async onModuleInit() {
    // CLI adapter only starts when explicitly enabled via env var
    if (process.env.ENABLE_CLI_ADAPTER === 'true') {
      await this.cliAdapter.start();
    }
  }

  async onModuleDestroy() {
    this.cliAdapter.stop();
  }
}
