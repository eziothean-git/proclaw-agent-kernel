const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const path = require('path');

const PROTO_PATH = path.join(__dirname, '../src/proto/request-manager.proto');

// 加载 proto
const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: false,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

const proto = grpc.loadPackageDefinition(packageDefinition);
const RequestManager = proto.requestmanager.RequestManager;

const client = new RequestManager('localhost:50052', grpc.credentials.createInsecure());

console.log('测试字段名映射...\n');

const testRequest = {
  requestId: 'debug-' + Date.now(),
  sessionId: 'debug-session',
  userId: 'debug-user',
  priority: 3,
  body: 'Debug message',
  metadata: { test: 'true' },
  // receivedAt 是 google.protobuf.Timestamp 类型，需要特殊格式
  // 暂时不发送此字段，使用默认值
};

console.log('发送的请求:', JSON.stringify(testRequest, null, 2));
console.log('\n字段列表:');
console.log('  requestId:', testRequest.requestId);
console.log('  sessionId:', testRequest.sessionId);
console.log('  userId:', testRequest.userId);

client.submitRequest(testRequest, (err, response) => {
  if (err) {
    console.error('\n❌ 错误:', err.message);
    console.error('错误详情:', err);
  } else {
    console.log('\n✅ 响应:', JSON.stringify(response, null, 2));
  }
  client.close();
});