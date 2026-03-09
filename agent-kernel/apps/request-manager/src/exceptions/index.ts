export class QueueFullException extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'QueueFullException';
  }
}

export class RequestNotFoundException extends Error {
  constructor(requestId: string) {
    super(`Request ${requestId} not found`);
    this.name = 'RequestNotFoundException';
  }
}

export class RequestAlreadyProcessingException extends Error {
  constructor(requestId: string) {
    super(`Request ${requestId} is already being processed`);
    this.name = 'RequestAlreadyProcessingException';
  }
}

export class TimeoutException extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'TimeoutException';
  }
}

export class MaxRetriesExceededException extends Error {
  constructor(requestId: string) {
    super(`Request ${requestId} exceeded maximum retry attempts`);
    this.name = 'MaxRetriesExceededException';
  }
}

export class SessionLockedException extends Error {
  constructor(sessionId: string) {
    super(`Session ${sessionId} is currently locked`);
    this.name = 'SessionLockedException';
  }
}

export class GrpcError extends Error {
  public code: number;
  
  constructor(message: string, code: number) {
    super(message);
    this.name = 'GrpcError';
    this.code = code;
  }
}

export class CancelledException extends Error {
  constructor(requestId: string) {
    super(`Request ${requestId} was cancelled`);
    this.name = 'CancelledException';
  }
}