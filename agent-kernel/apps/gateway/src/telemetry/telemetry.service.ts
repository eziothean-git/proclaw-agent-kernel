import { Injectable, Logger, OnModuleInit } from '@nestjs/common';
import { NodeSDK } from '@opentelemetry/sdk-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { trace, Tracer, Context, Span, SpanStatusCode } from '@opentelemetry/api';

@Injectable()
export class TelemetryService implements OnModuleInit {
  private readonly logger = new Logger(TelemetryService.name);
  private sdk: NodeSDK | null = null;
  private tracer: Tracer;

  constructor() {
    this.tracer = trace.getTracer('agent-kernel-gateway', '0.1.0');
  }

  onModuleInit() {
    this.initializeTelemetry();
  }

  private initializeTelemetry(): void {
    const otlpEndpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://localhost:4318';
    
    this.sdk = new NodeSDK({
      traceExporter: new OTLPTraceExporter({
        url: `${otlpEndpoint}/v1/traces`,
      }),
      instrumentations: [
        getNodeAutoInstrumentations({
          '@opentelemetry/instrumentation-fs': {
            enabled: false, // Disable fs instrumentation to reduce noise
          },
        }),
      ],
    });

    try {
      this.sdk.start();
      this.logger.log(`OpenTelemetry initialized with endpoint: ${otlpEndpoint}`);
    } catch (error) {
      this.logger.error(`Failed to initialize OpenTelemetry: ${error.message}`);
    }
  }

  /**
   * Start a span for tracing
   */
  startSpan(
    name: string,
    parentContext?: Context,
    attributes?: Record<string, string | number | boolean>
  ): Span {
    const span = this.tracer.startSpan(name, undefined, parentContext);
    
    if (attributes) {
      Object.entries(attributes).forEach(([key, value]) => {
        span.setAttribute(key, value);
      });
    }

    return span;
  }

  /**
   * Record an exception in a span
   */
  recordException(span: Span, error: Error): void {
    span.recordException(error);
    span.setStatus({
      code: SpanStatusCode.ERROR,
      message: error.message,
    });
  }

  /**
   * End a span
   */
  endSpan(span: Span): void {
    span.end();
  }

  /**
   * Create a child span with automatic cleanup
   */
  async withSpan<T>(
    name: string,
    fn: (span: Span) => Promise<T>,
    attributes?: Record<string, string | number | boolean>
  ): Promise<T> {
    const span = this.startSpan(name, undefined, attributes);
    
    try {
      const result = await fn(span);
      span.setStatus({ code: SpanStatusCode.OK });
      return result;
    } catch (error) {
      this.recordException(span, error as Error);
      throw error;
    } finally {
      span.end();
    }
  }

  /**
   * Get current active context
   */
  getActiveContext(): Context {
    return trace.getActiveSpan()?.spanContext() as unknown as Context;
  }
}
