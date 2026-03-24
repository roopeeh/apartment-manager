# Run database migrations against RDS
$DB_HOST = "apartment-manager-public-dev.c8jm4a2as20x.us-east-1.rds.amazonaws.com"
$DB_NAME = "apartment_manager"
$DB_USER = "appadmin"

$SecurePassword = Read-Host "Enter DB password" -AsSecureString
$DB_PASSWORD = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
)

$env:DATABASE_URL = "postgresql+asyncpg://$DB_USER`:$DB_PASSWORD@$DB_HOST`:5432/$DB_NAME"

Write-Host "Running migrations..." -ForegroundColor Cyan
& .\venv\Scripts\alembic.exe upgrade head
