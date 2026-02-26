#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/../failsafe/dashboard/frontend"
echo "Installing dependencies..."
npm install
echo "Building dashboard..."
npm run build
echo "✅ Dashboard built successfully. Assets in failsafe/dashboard/frontend/dist/"
