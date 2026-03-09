import { Module } from '@nestjs/common';
import { StorageService } from './storage.service';
import { IRConverterService } from './ir-converter.service';

@Module({
  providers: [StorageService, IRConverterService],
  exports: [StorageService, IRConverterService],
})
export class CoreModule {}
