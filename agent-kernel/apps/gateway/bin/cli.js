#!/usr/bin/env node
/**
 * Gateway CLI Tool
 * 发送请求并等待响应的便捷工具
 */

const readline = require('readline');
const http = require('http');

const GATEWAY_URL = process.env.GATEWAY_URL || 'http://localhost:3000';
const POLL_INTERVAL = parseInt(process.env.POLL_INTERVAL || '500', 10);
const TIMEOUT = parseInt(process.env.TIMEOUT || '60000', 10);

function makeRequest(path, method = 'GET', data = null) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, GATEWAY_URL);
    const options = {
      hostname: url.hostname,
      port: url.port,
      path: url.pathname + url.search,
      method,
      headers: {
        'Content-Type': 'application/json',
      },
    };

    if (data) {
      options.headers['Content-Length'] = Buffer.byteLength(JSON.stringify(data));
    }

    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch {
          resolve(body);
        }
      });
    });

    req.on('error', reject);

    if (data) {
      req.write(JSON.stringify(data));
    }

    req.end();
  });
}

async function sendRequest(message, userId = 'cli-user') {
  console.log('Sending request...');
  
  const response = await makeRequest('/api/v1/chat', 'POST', {
    message,
    user_id: userId,
    platform: 'cli',
  });

  if (!response.requestId) {
    console.error('Error:', response);
    process.exit(1);
  }

  console.log(`Request ID: ${response.requestId}`);
  console.log('Waiting for response...\n');

  return response.requestId;
}

async function waitForResponse(requestId) {
  const startTime = Date.now();

  while (Date.now() - startTime < TIMEOUT) {
    const status = await makeRequest(`/api/v1/requests/${requestId}`);
    
    if (status.status === 'completed' || status.status === 'failed') {
      return status;
    }

    process.stdout.write('.');
    await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL));
  }

  throw new Error('Timeout waiting for response');
}

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    // Interactive mode
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      prompt: 'You: ',
    });

    console.log('Gateway CLI - Interactive Mode');
    console.log('Type your message and press Enter');
    console.log('Press Ctrl+C to exit\n');

    let sessionId = null;

    rl.prompt();

    rl.on('line', async (line) => {
      const message = line.trim();
      if (!message) {
        rl.prompt();
        return;
      }

      try {
        const requestId = await sendRequest(message);
        const response = await waitForResponse(requestId);
        
        console.log(`\nAI: ${response.response?.body || response.response}\n`);
        
        if (response.sessionId) {
          sessionId = response.sessionId;
        }
      } catch (error) {
        console.error('\nError:', error.message);
      }

      rl.prompt();
    });

    rl.on('close', () => {
      console.log('\nGoodbye!');
      process.exit(0);
    });

  } else {
    // Single message mode
    const message = args.join(' ');
    
    try {
      const requestId = await sendRequest(message);
      const response = await waitForResponse(requestId);
      
      console.log('\nResponse:');
      console.log(JSON.stringify(response, null, 2));
    } catch (error) {
      console.error('Error:', error.message);
      process.exit(1);
    }
  }
}

main().catch(console.error);
