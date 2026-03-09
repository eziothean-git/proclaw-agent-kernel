import { Injectable } from '@nestjs/common';
import { RequestTask } from '../interfaces';

@Injectable()
export class RequestStateService {
  private requests: Map<string, RequestTask> = new Map();

  set(requestId: string, task: RequestTask): void {
    this.requests.set(requestId, task);
  }

  get(requestId: string): RequestTask | undefined {
    return this.requests.get(requestId);
  }

  update(requestId: string, updates: Partial<RequestTask>): RequestTask | undefined {
    const task = this.requests.get(requestId);
    if (task) {
      Object.assign(task, updates);
    }
    return task;
  }

  delete(requestId: string): boolean {
    return this.requests.delete(requestId);
  }

  getAll(): RequestTask[] {
    return Array.from(this.requests.values());
  }

  getByStatus(status: number): RequestTask[] {
    return this.getAll().filter(task => task.status === status);
  }
}