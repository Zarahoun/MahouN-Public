#!/bin/bash
# Test script for optimized Dockerfile build
# Date: 2026-07-02

set -e

echo "🔧 MAHOUN Backend - Optimized Docker Build Test"
echo "================================================"
echo ""

# Note: BuildKit cache mounts removed for compatibility
# Build will work with standard Docker

# Build info
BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
VCS_REF=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")

echo "📊 Build Configuration:"
echo "  - Docker: Standard build mode"
echo "  - Target: production"
echo "  - Build Date: $BUILD_DATE"
echo "  - VCS Ref: $VCS_REF"
echo ""

# Start build
echo "🏗️  Building optimized production image..."
echo ""

time docker build \
  -f Dockerfile.backend.optimized \
  --target production \
  --build-arg BUILD_ENV=production \
  --build-arg BUILD_DATE="$BUILD_DATE" \
  --build-arg VCS_REF="$VCS_REF" \
  --build-arg ENABLE_GPU=false \
  -t mahoun/backend:optimized \
  .

echo ""
echo "✅ Build completed successfully!"
echo ""

# Get image size
SIZE=$(docker images mahoun/backend:optimized --format "{{.Size}}")
echo "📦 Image Size: $SIZE"
echo ""

# Test import
echo "🧪 Testing Python imports..."
docker run --rm mahoun/backend:optimized python -c "
import sys
print(f'Python {sys.version}')
import api.main
print('✅ api.main imports OK')
import mahoun.core
print('✅ mahoun.core imports OK')
import mahoun.reasoning
print('✅ mahoun.reasoning imports OK')
"

echo ""
echo "🎉 All tests passed!"
echo ""
echo "📋 Next Steps:"
echo "  1. Run: docker run -d --name test-backend -p 8000:8000 mahoun/backend:optimized"
echo "  2. Wait 10s and check health: docker inspect test-backend --format='{{.State.Health.Status}}'"
echo "  3. Cleanup: docker rm -f test-backend"
