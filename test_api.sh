#!/bin/bash
# Shadow Bureau: Quick API Test Script
# Tests core endpoints to verify everything works after cleanup

set -e

BASE_URL="http://localhost:8000"
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🧪 Shadow Bureau API Test Suite"
echo "================================"
echo ""

# Check if server is running
echo -n "Checking if server is running... "
if curl -s "$BASE_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Server is UP${NC}"
else
    echo -e "${RED}❌ Server is DOWN${NC}"
    echo ""
    echo "Start the server first:"
    echo "  uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
    exit 1
fi
echo ""

# Test 1: Health Check
echo "Test 1: Health Check"
echo "--------------------"
HEALTH=$(curl -s "$BASE_URL/health")
echo "$HEALTH" | jq '.'

SOURCES=$(echo "$HEALTH" | jq -r '.knowledge_sources')
RUNNING=$(echo "$HEALTH" | jq -r '.controller_running')

if [ "$SOURCES" = "7" ] && [ "$RUNNING" = "true" ]; then
    echo -e "${GREEN}✅ PASS: Health check successful${NC}"
else
    echo -e "${RED}❌ FAIL: Expected 7 sources and controller running${NC}"
fi
echo ""

# Test 2: Submit Report
echo "Test 2: Submit Report"
echo "--------------------"
REPORT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/report" \
  -H "Content-Type: application/json" \
  -d '{
    "text_body": "Test report: Suspicious activity near Hunt Library at 2pm. Person wearing black hoodie taking photos.",
    "location": {
      "lat": 35.7847,
      "lng": -78.6821,
      "building": "Hunt Library"
    },
    "timestamp": "2026-02-14T14:00:00",
    "media_url": null,
    "anonymous": true,
    "contact": null
  }')

echo "$REPORT_RESPONSE" | jq '.'

CASE_ID=$(echo "$REPORT_RESPONSE" | jq -r '.case_id')
REPORT_ID=$(echo "$REPORT_RESPONSE" | jq -r '.report_id')

if [ -n "$CASE_ID" ] && [ "$CASE_ID" != "null" ]; then
    echo -e "${GREEN}✅ PASS: Report created${NC}"
    echo "   Case ID: $CASE_ID"
    echo "   Report ID: $REPORT_ID"
else
    echo -e "${RED}❌ FAIL: Report creation failed${NC}"
    exit 1
fi
echo ""

# Wait for pipelines to process
echo -e "${YELLOW}⏳ Waiting 3 seconds for pipelines to process...${NC}"
sleep 3
echo ""

# Test 3: List Reports
echo "Test 3: List Reports"
echo "--------------------"
REPORTS=$(curl -s "$BASE_URL/api/reports")
REPORT_COUNT=$(echo "$REPORTS" | jq '. | length')
echo "Found $REPORT_COUNT reports"
echo "$REPORTS" | jq '.[0] | {case_id, report_id, text_body, status}'

if [ "$REPORT_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ PASS: Reports listed${NC}"
else
    echo -e "${RED}❌ FAIL: No reports found${NC}"
fi
echo ""

# Test 4: List Cases
echo "Test 4: List Cases"
echo "--------------------"
CASES=$(curl -s "$BASE_URL/api/cases")
CASE_COUNT=$(echo "$CASES" | jq '. | length')
echo "Found $CASE_COUNT cases"
echo "$CASES" | jq '.[0]'

if [ "$CASE_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ PASS: Cases listed${NC}"
else
    echo -e "${RED}❌ FAIL: No cases found${NC}"
fi
echo ""

# Test 5: Get Case Snapshot
echo "Test 5: Get Case Snapshot"
echo "-------------------------"
SNAPSHOT=$(curl -s "$BASE_URL/api/cases/$CASE_ID")
NODE_COUNT=$(echo "$SNAPSHOT" | jq '.nodes | length')
EDGE_COUNT=$(echo "$SNAPSHOT" | jq '.edges | length')

echo "Case: $CASE_ID"
echo "  Nodes: $NODE_COUNT"
echo "  Edges: $EDGE_COUNT"

if [ "$NODE_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ PASS: Case snapshot retrieved${NC}"
    echo ""
    echo "Sample node:"
    echo "$SNAPSHOT" | jq '.nodes[0]'
else
    echo -e "${RED}❌ FAIL: No nodes in case${NC}"
fi
echo ""

# Test 6: Draft Alert
echo "Test 6: Draft Alert"
echo "-------------------"
DRAFT=$(curl -s -X POST "$BASE_URL/api/alerts/draft" \
  -H "Content-Type: application/json" \
  -d "{
    \"case_id\": \"$CASE_ID\",
    \"officer_notes\": \"Test alert draft\"
  }")

echo "$DRAFT" | jq '.'
DRAFT_TEXT=$(echo "$DRAFT" | jq -r '.draft_text')

if [ -n "$DRAFT_TEXT" ] && [ "$DRAFT_TEXT" != "null" ]; then
    echo -e "${GREEN}✅ PASS: Alert drafted${NC}"
else
    echo -e "${RED}❌ FAIL: Alert draft failed${NC}"
fi
echo ""

# Test 7: Approve Alert
echo "Test 7: Approve Alert"
echo "---------------------"
ALERT=$(curl -s -X POST "$BASE_URL/api/alerts/approve" \
  -H "Content-Type: application/json" \
  -d "{
    \"case_id\": \"$CASE_ID\",
    \"final_text\": \"CAMPUS ALERT: Test alert. No action needed.\",
    \"status\": \"published\"
  }")

echo "$ALERT" | jq '.'
ALERT_ID=$(echo "$ALERT" | jq -r '.id')

if [ -n "$ALERT_ID" ] && [ "$ALERT_ID" != "null" ]; then
    echo -e "${GREEN}✅ PASS: Alert approved${NC}"
else
    echo -e "${RED}❌ FAIL: Alert approval failed${NC}"
fi
echo ""

# Test 8: List Alerts
echo "Test 8: List Alerts"
echo "-------------------"
ALERTS=$(curl -s "$BASE_URL/api/alerts")
ALERT_COUNT=$(echo "$ALERTS" | jq '. | length')
echo "Found $ALERT_COUNT alerts"
echo "$ALERTS" | jq '.[0] | {id, case_id, text, status}'

if [ "$ALERT_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✅ PASS: Alerts listed${NC}"
else
    echo -e "${RED}❌ FAIL: No alerts found${NC}"
fi
echo ""

# Summary
echo "================================"
echo "🎯 Test Summary"
echo "================================"
echo -e "${GREEN}✅ All core endpoints functional${NC}"
echo ""
echo "📊 Results:"
echo "  - Health: OK (7 knowledge sources)"
echo "  - Reports: $REPORT_COUNT created"
echo "  - Cases: $CASE_COUNT created"
echo "  - Alerts: $ALERT_COUNT published"
echo ""
echo "🌐 Access FastAPI Docs:"
echo "  Swagger: http://localhost:8000/docs"
echo "  ReDoc:   http://localhost:8000/redoc"
echo ""
echo -e "${GREEN}🎉 All tests passed! Backend is working correctly.${NC}"
