$PROJECT = "jobassist-469114"
$ANTHROPIC_KEY = (Get-Content openaiapikey.env | Select-String "ANTHROPIC_API_KEY").ToString().Split("=")[1].Trim()

if (-not $ANTHROPIC_KEY) {
    Write-Error "ANTHROPIC_API_KEY not found in openaiapikey.env"
    exit 1
}

# inject key into cloudbuild.yaml on the fly — no permanent edit needed
$config = Get-Content cloudbuild.yaml -Raw
$config = $config -replace "your_key_here", $ANTHROPIC_KEY
$config | Out-File -Encoding utf8 _cloudbuild_temp.yaml

Write-Host "Deploying to Google Cloud Run (project: $PROJECT)..."
gcloud config set project $PROJECT
gcloud builds submit --config _cloudbuild_temp.yaml .

Remove-Item _cloudbuild_temp.yaml
Write-Host ""
Write-Host "Done. App live at:"
Write-Host "  https://jobassist-ui-ua6pbx6pna-uc.a.run.app"
