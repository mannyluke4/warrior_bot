#!/usr/bin/env node
/**
 * scanner_monitor.js
 * Connects to Chrome via CDP and monitors Warrior Trading scanner WebSocket traffic.
 * Run this first to observe raw Socket.IO event names and payload structure.
 * 
 * Usage: node scanner_monitor.js
 * Prerequisites: npm install playwright
 */

const { chromium } = require('playwright');

const CDP_HOST = process.env.CDP_HOST || '192.168.5.2';
const CDP_PORT = process.env.CDP_PORT || '9222';

async function monitorScanner() {
  console.log(`[scanner_monitor] Connecting to Chrome at ${CDP_HOST}:${CDP_PORT}...`);
  
  let browser;
  try {
    browser = await chromium.connectOverCDP(`http://${CDP_HOST}:${CDP_PORT}`);
  } catch (err) {
    console.error(`[scanner_monitor] Failed to connect to Chrome CDP: ${err.message}`);
    console.error('Make sure Chrome is running with --remote-debugging-port=9222');
    process.exit(1);
  }

  const contexts = browser.contexts();
  if (!contexts.length) {
    console.error('[scanner_monitor] No browser contexts found');
    process.exit(1);
  }

  const pages = contexts[0].pages();
  console.log(`[scanner_monitor] Found ${pages.length} open tabs:`);
  pages.forEach((p, i) => console.log(`  [${i}] ${p.url()}`));

  const scannerPage = pages.find(p => p.url().includes('warriortrading'));
  if (!scannerPage) {
    console.error('[scanner_monitor] Scanner tab not found. Is the scanner open in Chrome?');
    console.error('Available URLs:', pages.map(p => p.url()));
    process.exit(1);
  }

  console.log(`[scanner_monitor] Connected to scanner tab: ${scannerPage.url()}`);

  // Create CDP session for raw protocol access
  const client = await scannerPage.context().newCDPSession(scannerPage);

  // Enable network domain
  await client.send('Network.enable');

  console.log('[scanner_monitor] Monitoring WebSocket frames... (Ctrl+C to stop)\n');

  let frameCount = 0;
  let alertCount = 0;

  // Listen for WebSocket frames
  client.on('Network.webSocketFrameReceived', (params) => {
    const data = params.response.payloadData;
    frameCount++;

    // Socket.IO messages: "42" prefix = event, "2" = ping, "3" = pong
    if (data.startsWith('42')) {
      try {
        const parsed = JSON.parse(data.substring(2));
        const eventName = parsed[0];
        const payload = parsed[1];

        // Log ALL events first pass to discover event names
        const payloadStr = JSON.stringify(payload);
        const preview = payloadStr.length > 300 ? payloadStr.substring(0, 300) + '...' : payloadStr;
        
        console.log(`[${new Date().toISOString()}] EVENT: ${eventName}`);
        console.log(`  Payload: ${preview}`);
        console.log('');

        alertCount++;

        // Save to file for analysis
        const fs = require('fs');
        const logLine = JSON.stringify({ 
          ts: new Date().toISOString(), 
          event: eventName, 
          payload 
        }) + '\n';
        fs.appendFileSync('/tmp/scanner_events.jsonl', logLine);

      } catch (e) {
        // Not all frames are parseable JSON — ignore
      }
    }
  });

  client.on('Network.webSocketFrameSent', (params) => {
    const data = params.response.payloadData;
    if (data.startsWith('42')) {
      try {
        const parsed = JSON.parse(data.substring(2));
        console.log(`[${new Date().toISOString()}] SENT: ${parsed[0]}`, JSON.stringify(parsed[1]).substring(0, 200));
      } catch (e) {}
    }
  });

  // Status report every 30 seconds
  setInterval(() => {
    console.log(`[scanner_monitor] Status: ${frameCount} total frames, ${alertCount} events captured`);
  }, 30000);

  // Keep running
  await new Promise(() => {});
}

monitorScanner().catch(err => {
  console.error('[scanner_monitor] Fatal error:', err);
  process.exit(1);
});
