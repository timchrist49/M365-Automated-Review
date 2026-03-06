#!/bin/bash
# Generate a self-signed certificate for Monkey365 App Registration
# Usage: ./scripts/generate_cert.sh [password]
# Outputs:
#   certs/monkey365.pfx  — certificate + private key for Monkey365 (keep secret)
#   certs/monkey365.cer  — public key only, upload this to Azure App Registration

set -e

CERT_DIR="$(dirname "$0")/../certs"
mkdir -p "$CERT_DIR"

PASSWORD="${1:-changeme}"
DAYS=730  # 2 years

echo "[1/4] Generating private key..."
openssl genrsa -out "$CERT_DIR/monkey365.key" 4096

echo "[2/4] Generating self-signed certificate..."
openssl req -new -x509 \
  -key "$CERT_DIR/monkey365.key" \
  -out "$CERT_DIR/monkey365.crt" \
  -days $DAYS \
  -subj "/CN=Monkey365-M365-Audit/O=SecurityAssessment/C=US"

echo "[3/4] Exporting PFX (private key + cert for Monkey365)..."
openssl pkcs12 -export \
  -out "$CERT_DIR/monkey365.pfx" \
  -inkey "$CERT_DIR/monkey365.key" \
  -in "$CERT_DIR/monkey365.crt" \
  -passout "pass:$PASSWORD"

echo "[4/4] Exporting public key CER (upload this to Azure App Registration)..."
openssl x509 -in "$CERT_DIR/monkey365.crt" -out "$CERT_DIR/monkey365.cer" -outform DER

# Secure permissions
chmod 600 "$CERT_DIR/monkey365.key" "$CERT_DIR/monkey365.pfx"
chmod 644 "$CERT_DIR/monkey365.cer"

# Clean up intermediate files
rm "$CERT_DIR/monkey365.key" "$CERT_DIR/monkey365.crt"

echo ""
echo "Done!"
echo "  PFX (for .env CERT_PATH):  $CERT_DIR/monkey365.pfx"
echo "  CER (upload to Azure):     $CERT_DIR/monkey365.cer"
echo "  Password used: $PASSWORD"
echo ""
echo "Next: Upload monkey365.cer to your Azure App Registration"
echo "      > Certificates & secrets > Certificates > Upload certificate"
