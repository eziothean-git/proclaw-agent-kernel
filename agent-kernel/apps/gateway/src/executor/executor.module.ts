import { Module } from '@nestjs/common';
import { ExecutorService } from './executor.service';
import { ExecutorController } from './executor.controller';
import { KernelModule } from '../kernel/kernel.module';

@Module({
  imports: [KernelModule],
  controllers: [ExecutorController],
  providers: [ExecutorService],
  exports: [ExecutorService],
})
export class ExecutorModule {}
