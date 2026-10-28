#!/usr/bin/env bash
# M3-C1 read-only frontend review only. Never open DQA/DEMIS database.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"
npm ci --no-audit --no-fund
npm run test -- --run \
  src/test/TemplateReviewPortal.test.tsx \
  src/test/WorkflowDashboard.test.tsx \
  src/test/QueryAssistant.test.tsx \
  src/test/CatalogGraphicalBuilder.test.tsx
npm run build
npm run lint
cd "$ROOT"
git diff --check cff09c9 HEAD
echo "M3C1_FRONTEND_REVIEW_PASS"
