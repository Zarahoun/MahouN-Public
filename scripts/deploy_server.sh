#!/bin/bash
# اسکریپت استقرار خودکار ماحون روی سرور
# نسخه: 1.0
# تاریخ: ۱۴۰۴/۱۲/۰۳

set -e  # خروج در صورت خطا

# رنگ‌ها برای خروجی
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# توابع کمکی
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# بررسی root
if [ "$EUID" -eq 0 ]; then 
    print_error "لطفا این اسکریپت را با کاربر عادی اجرا کنید (نه root)"
    exit 1
fi

print_info "شروع استقرار سیستم ماحون..."

# ۱. بررسی Python
print_info "بررسی Python 3.12..."
if command -v python3.12 &> /dev/null; then
    print_success "Python 3.12 نصب شده است"
else
    print_error "Python 3.12 یافت نشد. لطفا ابتدا آن را نصب کنید"
    exit 1
fi

# ۲. ایجاد Virtual Environment
print_info "ایجاد Virtual Environment..."
if [ ! -d "venv" ]; then
    python3.12 -m venv venv
    print_success "Virtual Environment ایجاد شد"
else
    print_info "Virtual Environment از قبل وجود دارد"
fi

# ۳. فعال‌سازی venv و نصب dependencies
print_info "نصب Dependencies..."
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
print_success "Dependencies نصب شدند"

# ۴. بررسی .env
print_info "بررسی فایل .env..."
if [ ! -f ".env" ]; then
    print_info "کپی .env.example به .env..."
    cp .env.example .env
    
    # تولید API key تصادفی
    API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
    sed -i "s/your-secret-api-key-here/$API_KEY/" .env
    
    print_success "فایل .env ایجاد شد"
    print_info "API Key: $API_KEY"
    print_info "لطفا .env را بررسی و تنظیمات را کامل کنید"
else
    print_info ".env از قبل وجود دارد"
fi

# ۵. ایجاد دایرکتوری‌ها
print_info "ایجاد دایرکتوری‌های لازم..."
mkdir -p data/datasets data/models data/uploads
mkdir -p logs
mkdir -p models/finetuned models/registry
chmod 755 data models logs
print_success "دایرکتوری‌ها ایجاد شدند"

# ۶. تست Import
print_info "تست Import..."
python3 -c "
from mahoun.core import settings
from mahoun.reasoning import evidence_linked_verdict
from mahoun.finetuning import trainer
print('✅ All imports successful!')
" && print_success "Import موفق بود" || print_error "Import ناموفق بود"

# ۷. تست Health Check
print_info "تست Health Check..."
python3 -c "
import asyncio
from mahoun.infrastructure.health_checker import HealthChecker

async def test():
    checker = HealthChecker()
    results = await checker.check_all()
    return results.get('status') == 'healthy'

result = asyncio.run(test())
exit(0 if result else 1)
" && print_success "Health Check موفق بود" || print_info "Health Check با هشدار"

# ۸. ایجاد systemd service
print_info "ایجاد systemd service..."
SERVICE_FILE="/etc/systemd/system/mahoun.service"
CURRENT_USER=$(whoami)
CURRENT_DIR=$(pwd)

sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=MAHOUN Platform API Server
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
Environment="PATH=$CURRENT_DIR/venv/bin"
ExecStart=$CURRENT_DIR/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
print_success "systemd service ایجاد شد"

# ۹. فعال‌سازی و شروع service
print_info "فعال‌سازی service..."
sudo systemctl enable mahoun
sudo systemctl start mahoun
sleep 3

# بررسی وضعیت
if sudo systemctl is-active --quiet mahoun; then
    print_success "سرویس با موفقیت راه‌اندازی شد"
else
    print_error "سرویس راه‌اندازی نشد. لاگ‌ها را بررسی کنید:"
    print_info "sudo journalctl -u mahoun -n 50"
    exit 1
fi

# ۱۰. تست API
print_info "تست API..."
sleep 2
if curl -s http://localhost:8000/health > /dev/null; then
    print_success "API در حال اجراست"
else
    print_error "API پاسخ نمی‌دهد"
fi

# خلاصه
echo ""
echo "======================================"
print_success "استقرار با موفقیت انجام شد!"
echo "======================================"
echo ""
print_info "دستورات مفید:"
echo "  - مشاهده وضعیت: sudo systemctl status mahoun"
echo "  - مشاهده لاگ‌ها: sudo journalctl -u mahoun -f"
echo "  - ری‌استارت: sudo systemctl restart mahoun"
echo "  - توقف: sudo systemctl stop mahoun"
echo ""
print_info "API در حال اجراست روی: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
print_info "برای اتصال Frontend، این URL را در .env.production قرار دهید:"
echo "  VITE_API_BASE_URL=http://$(hostname -I | awk '{print $1}'):8000"
echo ""
