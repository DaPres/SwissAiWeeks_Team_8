#!/usr/bin/env bash
# One-time (re-runnable) provisioning for the triage app on Azure Container Apps.
#
#   ACR (aiweeksteam8)  <- GitHub Actions pushes images on version tags (v*)
#   Container Apps env + app "triage" pulls from ACR with its managed identity
#   App identity gets "Azure AI User" on the Foundry account -> no Foundry key needed
#   SPN "gh-swissaiweeks-team8-deploy" with a GitHub OIDC federated credential
#   (environment "production") -> AcrPush on ACR + Contributor on the resource group
#
# Usage: infra/setup-azure.sh            (reads OPENAI_API_KEY / APERTUS_API_KEY from backend/.env if present)
set -euo pipefail

SUBSCRIPTION=${SUBSCRIPTION:-a7d6755d-dc5c-45f6-a8d0-8b8e5554198f}
RG=${RG:-ai-weeks}
LOCATION=${LOCATION:-swedencentral}
ACR=${ACR:-aiweeksteam8}
ENV_NAME=${ENV_NAME:-ai-weeks-env}
APP=${APP:-triage}
FOUNDRY=${FOUNDRY:-ai-weeks}
GH_REPO=${GH_REPO:-DaPres/SwissAiWeeks_Team_8}
GH_ENVIRONMENT=${GH_ENVIRONMENT:-production}
SPN_NAME=${SPN_NAME:-gh-swissaiweeks-team8-deploy}
IMAGE=${IMAGE:-$ACR.azurecr.io/$APP:bootstrap}

cd "$(dirname "$0")/.."
az account set --subscription "$SUBSCRIPTION"
TENANT=$(az account show --query tenantId -o tsv)
RG_ID=$(az group show -n "$RG" --query id -o tsv)

echo "==> ACR $ACR"
az acr show -n "$ACR" -g "$RG" -o none 2>/dev/null ||
  az acr create -n "$ACR" -g "$RG" -l "$LOCATION" --sku Basic --admin-enabled false -o none
ACR_ID=$(az acr show -n "$ACR" -g "$RG" --query id -o tsv)

echo "==> bootstrap image $IMAGE (built in ACR)"
az acr repository show -n "$ACR" --image "${IMAGE#*/}" -o none 2>/dev/null ||
  az acr build -r "$ACR" -t "${IMAGE#*/}" --build-arg VERSION=bootstrap . -o none

echo "==> Container Apps environment $ENV_NAME"
az containerapp env show -n "$ENV_NAME" -g "$RG" -o none 2>/dev/null ||
  az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOCATION" -o none

# Optional provider keys, kept as Container App secrets (Foundry uses the managed identity instead).
SECRETS=() ENVS=(
  "AZURE_FOUNDRY_ENDPOINT=https://$FOUNDRY.services.ai.azure.com/openai/v1/"
  "CHAT_DEPLOYMENT=gpt-5.6-terra" "VISION_DEPLOYMENT=gpt-5.6-terra" "EMBEDDING_DEPLOYMENT=text-embedding-3-small"
)
for key in OPENAI_API_KEY APERTUS_API_KEY; do
  value=$(grep -E "^$key=" backend/.env 2>/dev/null | head -1 | cut -d= -f2- | sed -E 's/[[:space:]]+#.*$//; s/^"//; s/"$//' || true)
  if [[ -n "$value" ]]; then
    secret=$(echo "$key" | tr 'A-Z_' 'a-z-')
    SECRETS+=("$secret=$value")
    ENVS+=("$key=secretref:$secret")
  fi
done

echo "==> Container App $APP"
if ! az containerapp show -n "$APP" -g "$RG" -o none 2>/dev/null; then
  az containerapp create -n "$APP" -g "$RG" --environment "$ENV_NAME" \
    --image "$IMAGE" --registry-server "$ACR.azurecr.io" --registry-identity system \
    --system-assigned --target-port 8000 --ingress external \
    --cpu 1 --memory 2Gi --min-replicas 1 --max-replicas 1 -o none
fi
[[ ${#SECRETS[@]} -gt 0 ]] && az containerapp secret set -n "$APP" -g "$RG" --secrets "${SECRETS[@]}" -o none
az containerapp update -n "$APP" -g "$RG" --set-env-vars "${ENVS[@]}" -o none

echo "==> Foundry access for the app identity"
APP_PRINCIPAL=$(az containerapp show -n "$APP" -g "$RG" --query identity.principalId -o tsv)
FOUNDRY_ID=$(az cognitiveservices account show -n "$FOUNDRY" -g "$RG" --query id -o tsv)
az role assignment create --assignee-object-id "$APP_PRINCIPAL" --assignee-principal-type ServicePrincipal \
  --role "Azure AI User" --scope "$FOUNDRY_ID" -o none

echo "==> Deploy SPN $SPN_NAME (GitHub OIDC)"
CLIENT_ID=$(az ad app list --display-name "$SPN_NAME" --query "[0].appId" -o tsv)
if [[ -z "$CLIENT_ID" ]]; then
  CLIENT_ID=$(az ad app create --display-name "$SPN_NAME" --query appId -o tsv)
fi
az ad sp show --id "$CLIENT_ID" -o none 2>/dev/null || az ad sp create --id "$CLIENT_ID" -o none
SPN_OBJECT=$(az ad sp show --id "$CLIENT_ID" --query id -o tsv)
SUBJECT="repo:$GH_REPO:environment:$GH_ENVIRONMENT"
if [[ -z $(az ad app federated-credential list --id "$CLIENT_ID" --query "[?subject=='$SUBJECT'].name" -o tsv) ]]; then
  az ad app federated-credential create --id "$CLIENT_ID" --parameters "{
    \"name\": \"github-$GH_ENVIRONMENT\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"$SUBJECT\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" -o none
fi
az role assignment create --assignee-object-id "$SPN_OBJECT" --assignee-principal-type ServicePrincipal \
  --role AcrPush --scope "$ACR_ID" -o none
az role assignment create --assignee-object-id "$SPN_OBJECT" --assignee-principal-type ServicePrincipal \
  --role Contributor --scope "$RG_ID" -o none

FQDN=$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
cat <<EOF

Done. App: https://$FQDN

GitHub repo secrets ($GH_REPO):
  AZURE_CLIENT_ID=$CLIENT_ID
  AZURE_TENANT_ID=$TENANT
  AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION
EOF
