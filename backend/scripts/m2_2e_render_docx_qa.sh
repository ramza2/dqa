#!/usr/bin/env bash
# Optional visual QA for synthetic DOCX files. No external DB/network calls.
set -euo pipefail
BACKEND_DIR="$(cd "$(dirname "$BASH_SOURCE")/.." && pwd)"
QA_DIR="$BACKEND_DIR/artifacts/m2-2e-docx-qa"
if [ "$#" -gt 0 ]; then QA_DIR="$1"; fi
PYTHON_CMD="python3"
if [ -n "$(printenv PYTHON 2>/dev/null || :)" ]; then PYTHON_CMD="$PYTHON"; fi
cd "$BACKEND_DIR"
"$PYTHON_CMD" -m scripts.m2_2e_docx_layout_qa --out-dir "$QA_DIR"
if ! command -v libreoffice >/dev/null 2>&1; then
  echo "M2_2E_RENDER_SKIPPED: libreoffice unavailable; open DOCX in Word."
  echo "QA files: $QA_DIR"
  exit 0
fi
RENDER_DIR="$QA_DIR/rendered"
mkdir -p "$RENDER_DIR"
PROFILE="$(mktemp -d)"
trap 'rm -rf "$PROFILE"' EXIT
shopt -s nullglob
count=0
for document in "$QA_DIR"/*.docx; do
  count=$((count + 1))
  libreoffice "-env:UserInstallation=file://$PROFILE" \
    --headless --convert-to pdf --outdir "$RENDER_DIR" "$document" >/dev/null
  stem="$(basename "$document" .docx)"
  pdf="$RENDER_DIR/$stem.pdf"
  if [ ! -s "$pdf" ]; then
    echo "M2_2E_RENDER_FAILED: $document" >&2
    exit 1
  fi
  if command -v pdftoppm >/dev/null 2>&1; then
    # All pages, not just first two.
    pdftoppm -r 135 -png "$pdf" "$RENDER_DIR/$stem" >/dev/null 2>&1
  fi
  if command -v pdfinfo >/dev/null 2>&1; then
    pages="$(pdfinfo "$pdf" | awk '/^Pages:/ {print $2}')"
    echo "M2_2E_RENDERED: $stem.pdf pages=$pages"
  else
    echo "M2_2E_RENDERED: $stem.pdf"
  fi
done
if [ "$count" -eq 0 ]; then
  echo "M2_2E_RENDER_FAILED: no DOCX fixtures" >&2
  exit 1
fi
echo "M2_2E_RENDER_GENERATED: $RENDER_DIR"
echo "M2_2E_VISUAL_REVIEW_PENDING: inspect every PDF/PNG page."
