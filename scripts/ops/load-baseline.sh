#!/usr/bin/env bash
# k6 Load Test Baseline - Run against local/staging to establish performance baseline
# Usage: ./load-baseline.sh [endpoint] [vus] [duration]

set -euo pipefail

BASE_URL="${API_BASE_URL:-http://localhost:8000}"
VUS="${2:-10}"
DURATION="${3:-30s}"
ENDPOINT="${1:-/health}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS_DIR="${SCRIPT_DIR}/../load/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "${RESULTS_DIR}"

echo "=== k6 Load Test Baseline ==="
echo "Target:    ${BASE_URL}${ENDPOINT}"
echo "VUs:       ${VUS}"
echo "Duration:  ${DURATION}"
echo "Results:   ${RESULTS_DIR}/baseline_${TIMESTAMP}.json"
echo ""

if ! command -v k6 &> /dev/null; then
    echo "Installing k6..."
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo gpg -k 2>/dev/null || true
        sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
            --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D68
        echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" | \
            sudo tee /etc/apt/sources.list.d/k6.list > /dev/null
        sudo apt-get update && sudo apt-get install k6
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install k6
    else
        echo "Please install k6 manually: https://k6.io/docs/get-started/installation/"
        exit 1
    fi
fi

cat > /tmp/k6_baseline.js << 'EOF'
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const ENDPOINT = __ENV.ENDPOINT || '/health';

export const options = {
    vus: parseInt(__ENV.VUS || '10'),
    duration: __ENV.DURATION || '30s',
    thresholds: {
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        http_req_failed: ['rate<0.01'],
        http_reqs: ['rate>10'],
    },
};

export default function () {
    const res = http.get(`${BASE_URL}${ENDPOINT}`);
    check(res, {
        'status is 200': (r) => r.status === 200,
        'response time < 500ms': (r) => r.timings.duration < 500,
        'response time < 1000ms': (r) => r.timings.duration < 1000,
    });
    sleep(1);
}
EOF

k6 run \
    --summary-export="${RESULTS_DIR}/baseline_${TIMESTAMP}.json" \
    /tmp/k6_baseline.js

echo ""
echo "=== Baseline Results ==="
echo "View JSON: ${RESULTS_DIR}/baseline_${TIMESTAMP}.json"
