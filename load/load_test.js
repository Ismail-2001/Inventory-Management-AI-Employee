/**
 * k6 Load Test — Inventory Agent API
 *
 * Run locally:
 *   k6 run load/load_test.js
 *
 * Run in CI with thresholds:
 *   k6 run --out json=load/results.json load/load_test.js
 */
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8002';
const API_KEY = __ENV.API_KEY || 'demo-key-2024';

const errorRate = new Rate('errors');
const requestDuration = new Trend('request_duration', true);
const throughput = new Counter('total_requests');

export const options = {
  scenarios: {
    health_check: {
      executor: 'constant-vus',
      vus: 5,
      duration: '30s',
      exec: 'healthCheck',
    },
    analyze_endpoint: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '30s', target: 10 },
        { duration: '1m', target: 20 },
        { duration: '30s', target: 0 },
      ],
      exec: 'analyzeInventory',
    },
    read_endpoints: {
      executor: 'constant-vus',
      vus: 10,
      duration: '2m',
      exec: 'readEndpoints',
    },
  },
  thresholds: {
    http_req_duration: [{ threshold: 'p(95)<3000', abortOnFail: false }],
    errors: [{ threshold: 'rate<0.1', abortOnFail: false }],
    http_req_failed: [{ threshold: 'rate<0.05', abortOnFail: false }],
  },
};

export function healthCheck() {
  const res = http.get(`${BASE_URL}/health`, {
    headers: { 'X-API-Key': API_KEY },
    timeout: '5s',
  });
  throughput.add(1);
  requestDuration.add(res.timings.duration);
  check(res, {
    'health: status 200': (r) => r.status === 200,
    'health: has status field': (r) => JSON.parse(r.body).status !== undefined,
  });
  errorRate.add(res.status !== 200);
}

export function analyzeInventory() {
  const payload = JSON.stringify({
    product_id: `LOAD-${Math.floor(Math.random() * 10000)}`,
    name: `Load Test Product ${Math.floor(Math.random() * 10000)}`,
    current_stock: Math.floor(Math.random() * 500),
    daily_sales: Math.round(Math.random() * 20 * 10) / 10,
    lead_time_days: Math.floor(Math.random() * 30) + 3,
    unit_cost: Math.round(Math.random() * 100 * 100) / 100,
    unit_price: Math.round(Math.random() * 200 * 100) / 100,
    category: 'electronics',
  });

  const res = http.post(`${BASE_URL}/api/v1/analyze`, payload, {
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
    },
    timeout: '10s',
  });
  throughput.add(1);
  requestDuration.add(res.timings.duration);
  check(res, {
    'analyze: status 200': (r) => r.status === 200,
    'analyze: has recommendation': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.recommendation !== undefined || body.action !== undefined;
      } catch {
        return false;
      }
    },
  });
  errorRate.add(res.status !== 200);
}

export function readEndpoints() {
  const endpoints = [
    '/api/v1/po?limit=10&offset=0',
    '/api/v1/skus',
    '/api/v1/usage/summary',
    '/api/v1/usage/daily',
    '/health',
  ];
  const endpoint = endpoints[Math.floor(Math.random() * endpoints.length)];

  const res = http.get(`${BASE_URL}${endpoint}`, {
    headers: { 'X-API-Key': API_KEY },
    timeout: '5s',
  });
  throughput.add(1);
  requestDuration.add(res.timings.duration);
  check(res, {
    [`read ${endpoint}: status 200`]: (r) => r.status === 200,
  });
  errorRate.add(res.status !== 200);
  sleep(Math.random() * 0.5 + 0.1);
}

export function handleSummary(data) {
  return {
    stdout: JSON.stringify({
      total_requests: data.metrics.total_requests?.values?.count || 0,
      error_rate: data.metrics.errors?.values?.rate || 0,
      p95_duration_ms: data.metrics.http_req_duration?.values?.['p(95)'] || 0,
      p99_duration_ms: data.metrics.http_req_duration?.values?.['p(99)'] || 0,
      avg_duration_ms: data.metrics.http_req_duration?.values?.avg || 0,
    }, null, 2),
    'load/summary.json': JSON.stringify(data, null, 2),
  };
}
