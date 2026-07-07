# =============================================================================
# PowerShell script to push code to EC2 and deploy
# Run from the kite-algo root directory
# =============================================================================

$PEM_KEY = "C:\Coding\AWS-Project-Rx\goroomz\LightsailDefaultKey-ap-south-1.pem"
$SERVER = "ubuntu@13.233.14.215"
$REMOTE_DIR = "/var/www/kite-algo"

Write-Host "===== Step 1: Create remote directory =====" -ForegroundColor Green
ssh -i $PEM_KEY -o StrictHostKeyChecking=no $SERVER "sudo mkdir -p $REMOTE_DIR && sudo chown ubuntu:ubuntu $REMOTE_DIR && sudo mkdir -p /var/log/kite-algo && sudo chown ubuntu:ubuntu /var/log/kite-algo"

Write-Host "===== Step 2: Upload project files via rsync =====" -ForegroundColor Green
# Using scp since rsync may not be available on Windows
# Exclude large/unnecessary directories
$EXCLUDE_DIRS = @(".venv", "node_modules", ".git", "__pycache__", ".hypothesis", "*.pyc", ".coverage")

# Create a tar archive excluding unnecessary files, then upload
Write-Host "Creating archive..." -ForegroundColor Yellow
tar --exclude=".venv" --exclude="node_modules" --exclude=".git" --exclude="__pycache__" --exclude=".hypothesis" --exclude="*.pyc" --exclude=".coverage" -czf deploy_package.tar.gz -C . .

Write-Host "Uploading archive to server..." -ForegroundColor Yellow
scp -i $PEM_KEY -o StrictHostKeyChecking=no deploy_package.tar.gz "${SERVER}:/tmp/deploy_package.tar.gz"

Write-Host "Extracting on server..." -ForegroundColor Yellow
ssh -i $PEM_KEY -o StrictHostKeyChecking=no $SERVER "cd $REMOTE_DIR && tar -xzf /tmp/deploy_package.tar.gz && rm /tmp/deploy_package.tar.gz"

# Clean up local archive
Remove-Item -Force deploy_package.tar.gz -ErrorAction SilentlyContinue

Write-Host "===== Step 3: Run deployment script on server =====" -ForegroundColor Green
ssh -i $PEM_KEY -o StrictHostKeyChecking=no $SERVER "chmod +x $REMOTE_DIR/deploy/deploy.sh && bash $REMOTE_DIR/deploy/deploy.sh"

Write-Host ""
Write-Host "===== DONE =====" -ForegroundColor Green
Write-Host "App URL: http://13.233.14.215" -ForegroundColor Cyan
Write-Host "API Docs: http://13.233.14.215/docs" -ForegroundColor Cyan
Write-Host "Kite Callback URL (update in Zerodha console): http://13.233.14.215/callback" -ForegroundColor Yellow
Write-Host "Kite Postback URL (update in Zerodha console): http://13.233.14.215/postback" -ForegroundColor Yellow
