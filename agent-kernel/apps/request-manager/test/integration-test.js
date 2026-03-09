#!/usr/bin/env node
/**
 * 简单的集成测试脚本 - 使用 snake_case 字段名
 */

const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const path = require('path');

const PROTO_PATH = path.join(__dirname, '../src/proto/request-manager.proto');

// 加载 proto - 使用 keepCase: false 自动转换
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: false,  // 自动将 snake_case 转换为 camelCase
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

const proto = grpc.loadPackageDefinition(packageDefinition);
const RequestManager = proto.requestmanager.RequestManager;

// 创建客户端
const client = new RequestManager(
  'localhost:50052',
  grpc.credentials.createInsecure()
);

console.log('🧪 开始测试 Request Manager...\n');

// 测试 1: 提交请求
function testSubmitRequest() {
  return new Promise((resolve, reject) => {
    console.log('测试 1: 提交请求 (使用 camelCase 字段名)');
    
    const request = {
      requestId: 'test-' + Date.now(),
      sessionId: 'session-test',
      userId: 'user-test',
      priority: 3, // P3_NORMAL
      body: 'Hello, this is a test message',
      metadata: { source: 'integration-test' },
      // receivedAt 是 google.protobuf.Timestamp 类型，暂时不发送
    };

    console.log('发送请求:', JSON.stringify(request, null, 2));

    client.submitRequest(request, (err, response) => {
      if (err) {
        console.error('❌ 提交请求失败:', err.message);
        reject(err);
      } else {
        console.log('✅ 提交请求成功');
        console.log('   Request ID:', response.requestId);
        console.log('   Status:', response.status);
        console.log('   Queue Position:', response.queuePosition);
        resolve(response.requestId);
      }
    });
  });
}

// 测试 2: 获取队列状态
function testGetQueueStatus() {
  return new Promise((resolve, reject) => {
    console.log('\n测试 2: 获取队列状态');
    
    client.getQueueStatus({}, (err, response) => {
      if (err) {
        console.error('❌ 获取队列状态失败:', err.message);
        reject(err);
      } else {
        console.log('✅ 获取队列状态成功');
        console.log('   Total Size:', response.totalSize);
        console.log('   By Priority:', JSON.stringify(response.byPriority));
        console.log('   Waiting Sessions:', response.waitingSessions);
        resolve();
      }
    });
  });
}

// 测试 3: 获取 Worker 状态
function testGetWorkerStatus() {
  return new Promise((resolve, reject) => {
    console.log('\n测试 3: 获取 Worker 状态');
    
    client.getWorkerStatus({}, (err, response) => {
      if (err) {
        console.error('❌ 获取 Worker 状态失败:', err.message);
        reject(err);
      } else {
        console.log('✅ 获取 Worker 状态成功');
        console.log('   Max Workers:', response.maxWorkers);
        console.log('   Active Workers:', response.activeWorkers);
        console.log('   Available Slots:', response.availableSlots);
        resolve();
      }
    });
  });
}

// 运行所有测试
async function runTests() {
  try {
    // 等待服务器启动
    console.log('⏳ 等待服务器启动...');
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    const requestId = await testSubmitRequest();
    await testGetQueueStatus();
    await testGetWorkerStatus();
    
    console.log('\n✅ 所有测试通过！\n');
    process.exit(0);
  } catch (error) {
    console.error('\n❌ 测试失败:', error.message);
    process.exit(1);
  }
}

runTests();