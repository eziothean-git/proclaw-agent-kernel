import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { KernelService } from './kernel.service';

@Module({
  imports: [
    HttpModule,
  ],
  providers: [KernelService],
  exports: [KernelService],
})
export class KernelModule {}
