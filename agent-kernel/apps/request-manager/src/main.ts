import { NestFactory } from '@nestjs/core';
import { RequestManagerModule } from './request-manager.module';

async function bootstrap() {
  const app = await NestFactory.create(RequestManagerModule, {
    logger: ['log', 'error', 'warn', 'debug', 'verbose'],
  });

  // 监听优雅关闭
  app.enableShutdownHooks();

  await app.init();
  
  console.log('========================================');
  console.log('Request Manager Started');
  console.log('========================================');
  console.log('Services:');
  console.log('  - gRPC Server: Gateway接口');
  console.log('  - gRPC Client: Prime Personality接口');
  console.log('  - Priority Queue: P0-P4');
  console.log('  - Worker Pool: Max 5 concurrent');
  console.log('  - Session Affinity: Enabled');
  console.log('  - Persistence: inbox + audit + state');
  console.log('========================================');
}

bootstrap().catch(err => {
  console.error('Failed to start Request Manager:', err);
  process.exit(1);
});