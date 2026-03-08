#!/bin/bash
# Pre-Deployment Checklist
# Run this before deploying to AWS to ensure everything is ready

echo "============================================================"
echo "PRE-DEPLOYMENT CHECKLIST"
echo "============================================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

# Check 1: .env file exists
echo "1. Checking .env file..."
if [ -f ".env" ]; then
    echo -e "   ${GREEN}✅ .env file found${NC}"
    
    # Check required variables
    REQUIRED_VARS=("KITE_USER_ID" "KITE_PASSWORD" "KITE_TOTP_KEY" "TELEGRAM_BOT_TOKEN" "TELEGRAM_CHAT_ID")
    
    for VAR in "${REQUIRED_VARS[@]}"; do
        if grep -q "^${VAR}=" .env; then
            VALUE=$(grep "^${VAR}=" .env | cut -d'=' -f2)
            if [ -z "$VALUE" ]; then
                echo -e "   ${RED}❌ $VAR is empty${NC}"
                ERRORS=$((ERRORS + 1))
            else
                echo -e "   ${GREEN}✅ $VAR is set${NC}"
            fi
        else
            echo -e "   ${RED}❌ $VAR not found in .env${NC}"
            ERRORS=$((ERRORS + 1))
        fi
    done
else
    echo -e "   ${RED}❌ .env file not found${NC}"
    echo "   Create .env file with your credentials"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# Check 2: Required Python files
echo "2. Checking required Python files..."
REQUIRED_FILES=(
    "start_bot_with_monitor.py"
    "telegram_bot.py"
    "advanced_killswitch.py"
    "segment_automation.py"
    "auto_login.py"
    "config.py"
    "notifier.py"
)

for FILE in "${REQUIRED_FILES[@]}"; do
    if [ -f "$FILE" ]; then
        echo -e "   ${GREEN}✅ $FILE${NC}"
    else
        echo -e "   ${RED}❌ $FILE missing${NC}"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""

# Check 3: Deployment scripts
echo "3. Checking deployment scripts..."
DEPLOY_FILES=(
    "aws_deploy.sh"
    "kite-trading-bot.service"
    "check_monitor_status.sh"
)

for FILE in "${DEPLOY_FILES[@]}"; do
    if [ -f "$FILE" ]; then
        echo -e "   ${GREEN}✅ $FILE${NC}"
    else
        echo -e "   ${YELLOW}⚠️  $FILE missing${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
done

echo ""

# Check 4: requirements.txt
echo "4. Checking requirements.txt..."
if [ -f "requirements.txt" ]; then
    echo -e "   ${GREEN}✅ requirements.txt found${NC}"
    
    # Check for key dependencies
    KEY_DEPS=("selenium" "pyotp" "pyTelegramBotAPI" "kiteconnect")
    for DEP in "${KEY_DEPS[@]}"; do
        if grep -q "$DEP" requirements.txt; then
            echo -e "   ${GREEN}✅ $DEP listed${NC}"
        else
            echo -e "   ${YELLOW}⚠️  $DEP not in requirements.txt${NC}"
            WARNINGS=$((WARNINGS + 1))
        fi
    done
else
    echo -e "   ${RED}❌ requirements.txt not found${NC}"
    ERRORS=$((ERRORS + 1))
fi

echo ""

# Check 5: Documentation
echo "5. Checking documentation..."
DOC_FILES=(
    "AWS_DEPLOYMENT_COMPLETE.md"
    "AWS_QUICK_REFERENCE.md"
    "DEPLOYMENT_SUMMARY.md"
)

for FILE in "${DOC_FILES[@]}"; do
    if [ -f "$FILE" ]; then
        echo -e "   ${GREEN}✅ $FILE${NC}"
    else
        echo -e "   ${YELLOW}⚠️  $FILE missing${NC}"
        WARNINGS=$((WARNINGS + 1))
    fi
done

echo ""

# Check 6: TOTP Key Format
echo "6. Validating TOTP key format..."
if [ -f ".env" ]; then
    TOTP_KEY=$(grep "^KITE_TOTP_KEY=" .env | cut -d'=' -f2)
    if [ -n "$TOTP_KEY" ]; then
        # TOTP key should be base32 (A-Z, 2-7)
        if [[ "$TOTP_KEY" =~ ^[A-Z2-7]+$ ]]; then
            echo -e "   ${GREEN}✅ TOTP key format looks valid${NC}"
        else
            echo -e "   ${YELLOW}⚠️  TOTP key format may be invalid${NC}"
            echo "   Expected: Base32 format (A-Z, 2-7)"
            WARNINGS=$((WARNINGS + 1))
        fi
    fi
fi

echo ""

# Check 7: File permissions
echo "7. Checking file permissions..."
if [ -f ".env" ]; then
    PERMS=$(stat -c "%a" .env 2>/dev/null || stat -f "%A" .env 2>/dev/null)
    if [ "$PERMS" = "600" ] || [ "$PERMS" = "0600" ]; then
        echo -e "   ${GREEN}✅ .env permissions are secure (600)${NC}"
    else
        echo -e "   ${YELLOW}⚠️  .env permissions: $PERMS (should be 600)${NC}"
        echo "   Run: chmod 600 .env"
        WARNINGS=$((WARNINGS + 1))
    fi
fi

echo ""

# Summary
echo "============================================================"
echo "SUMMARY"
echo "============================================================"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED!${NC}"
    echo ""
    echo "You're ready to deploy to AWS!"
    echo ""
    echo "Next steps:"
    echo "1. Upload files to AWS: scp -i key.pem -r kite-algo ubuntu@ip:~/"
    echo "2. SSH to AWS: ssh -i key.pem ubuntu@ip"
    echo "3. Run deployment: cd ~/kite-algo && ./aws_deploy.sh"
    echo ""
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠️  $WARNINGS WARNING(S) FOUND${NC}"
    echo ""
    echo "You can proceed with deployment, but review warnings above."
    echo ""
else
    echo -e "${RED}❌ $ERRORS ERROR(S) FOUND${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠️  $WARNINGS WARNING(S) FOUND${NC}"
    fi
    echo ""
    echo "Please fix errors before deploying."
    echo ""
    exit 1
fi

echo "============================================================"
