#!/bin/bash
# Build script for creating a standalone macOS app and DMG

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

APP_NAME="PloneAPIShell"
VERSION="0.1.9"
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
BUILD_DIR="build"
DIST_DIR="dist"
DMG_DIR="${BUILD_DIR}/dmg"

# Code signing configuration
# Set CODESIGN_IDENTITY environment variable to enable code signing
# Example: export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAM_ID)"
# Or pass it as an argument: ./build_app.sh "Developer ID Application: Your Name (TEAM_ID)"
CODESIGN_IDENTITY="${1:-${CODESIGN_IDENTITY:-}}"
ENTITLEMENTS_FILE="${ENTITLEMENTS_FILE:-}"

echo "Building ${APP_NAME}..."

if [ -n "$CODESIGN_IDENTITY" ]; then
    echo "Code signing enabled with identity: $CODESIGN_IDENTITY"
    export CODESIGN_IDENTITY
    if [ -n "$ENTITLEMENTS_FILE" ]; then
        export ENTITLEMENTS_FILE
        echo "Using entitlements file: $ENTITLEMENTS_FILE"
    fi
else
    echo "Code signing disabled (set CODESIGN_IDENTITY to enable)"
    echo "  Example: export CODESIGN_IDENTITY=\"Developer ID Application: Your Name (TEAM_ID)\""
    echo "  Or: ./build_app.sh \"Developer ID Application: Your Name (TEAM_ID)\""
fi

# Clean previous builds
echo "Cleaning previous builds..."
rm -rf "${BUILD_DIR}" "${DIST_DIR}/${APP_NAME}.app" "${DIST_DIR}/${DMG_NAME}"

# Check if PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: PyInstaller is not installed."
    echo "Install it with: pip install -r requirements-packaging.txt"
    exit 1
fi

# Convert PNG logo to ICNS for macOS (if needed)
ICON_PATH="${SCRIPT_DIR}/media/plone-logo.png"
ICNS_PATH="${SCRIPT_DIR}/media/plone-logo.icns"

if [ ! -f "$ICNS_PATH" ] && [ -f "$ICON_PATH" ]; then
    echo "Converting logo to ICNS format..."
    # Create iconset directory
    ICONSET_DIR="${SCRIPT_DIR}/media/plone-logo.iconset"
    mkdir -p "$ICONSET_DIR"
    
    # Create different sizes (macOS requires multiple sizes)
    sips -z 16 16 "$ICON_PATH" --out "${ICONSET_DIR}/icon_16x16.png" 2>/dev/null || convert "$ICON_PATH" -resize 16x16 "${ICONSET_DIR}/icon_16x16.png"
    sips -z 32 32 "$ICON_PATH" --out "${ICONSET_DIR}/icon_16x16@2x.png" 2>/dev/null || convert "$ICON_PATH" -resize 32x32 "${ICONSET_DIR}/icon_16x16@2x.png"
    sips -z 32 32 "$ICON_PATH" --out "${ICONSET_DIR}/icon_32x32.png" 2>/dev/null || convert "$ICON_PATH" -resize 32x32 "${ICONSET_DIR}/icon_32x32.png"
    sips -z 64 64 "$ICON_PATH" --out "${ICONSET_DIR}/icon_32x32@2x.png" 2>/dev/null || convert "$ICON_PATH" -resize 64x64 "${ICONSET_DIR}/icon_32x32@2x.png"
    sips -z 128 128 "$ICON_PATH" --out "${ICONSET_DIR}/icon_128x128.png" 2>/dev/null || convert "$ICON_PATH" -resize 128x128 "${ICONSET_DIR}/icon_128x128.png"
    sips -z 256 256 "$ICON_PATH" --out "${ICONSET_DIR}/icon_128x128@2x.png" 2>/dev/null || convert "$ICON_PATH" -resize 256x256 "${ICONSET_DIR}/icon_128x128@2x.png"
    sips -z 256 256 "$ICON_PATH" --out "${ICONSET_DIR}/icon_256x256.png" 2>/dev/null || convert "$ICON_PATH" -resize 256x256 "${ICONSET_DIR}/icon_256x256.png"
    sips -z 512 512 "$ICON_PATH" --out "${ICONSET_DIR}/icon_256x256@2x.png" 2>/dev/null || convert "$ICON_PATH" -resize 512x512 "${ICONSET_DIR}/icon_256x256@2x.png"
    sips -z 512 512 "$ICON_PATH" --out "${ICONSET_DIR}/icon_512x512.png" 2>/dev/null || convert "$ICON_PATH" -resize 512x512 "${ICONSET_DIR}/icon_512x512.png"
    sips -z 1024 1024 "$ICON_PATH" --out "${ICONSET_DIR}/icon_512x512@2x.png" 2>/dev/null || convert "$ICON_PATH" -resize 1024x1024 "${ICONSET_DIR}/icon_512x512@2x.png"
    
    # Convert iconset to icns
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"
    rm -rf "$ICONSET_DIR"
    
    echo "Icon created: $ICNS_PATH"
fi

# Update spec file with icon path if ICNS exists
if [ -f "$ICNS_PATH" ]; then
    echo "Using icon: $ICNS_PATH"
    # We'll pass this to PyInstaller via command line
    ICON_ARG="--icon=$ICNS_PATH"
else
    ICON_ARG=""
    echo "Warning: No ICNS icon found, using default icon"
fi

# Run PyInstaller
echo "Running PyInstaller..."
# Note: Icon is already specified in the spec file, so we don't pass --icon here
if [ -n "$CODESIGN_IDENTITY" ]; then
    CODESIGN_IDENTITY="$CODESIGN_IDENTITY" pyinstaller --clean --noconfirm ploneapi_shell.spec
else
    pyinstaller --clean --noconfirm ploneapi_shell.spec
fi

# Check if app was created
APP_PATH="${DIST_DIR}/${APP_NAME}.app"
if [ ! -d "$APP_PATH" ]; then
    echo "Error: App bundle not created at $APP_PATH"
    exit 1
fi

echo "App bundle created: $APP_PATH"

# Code sign the app bundle if identity is provided
if [ -n "$CODESIGN_IDENTITY" ]; then
    echo "Code signing app bundle..."
    codesign --force --deep --sign "$CODESIGN_IDENTITY" --options runtime "$APP_PATH"
    
    # Verify the signature
    echo "Verifying code signature..."
    codesign --verify --verbose "$APP_PATH"
    if [ $? -eq 0 ]; then
        echo "✓ Code signing successful"
    else
        echo "✗ Code signing verification failed"
        exit 1
    fi
    
    # Check Gatekeeper compatibility
    echo "Checking Gatekeeper compatibility..."
    spctl --assess --verbose "$APP_PATH" 2>&1 | head -5 || echo "Note: Gatekeeper check may require notarization for distribution"
fi

# Create DMG
echo "Creating DMG..."

# Check if create-dmg is installed
if ! command -v create-dmg &> /dev/null; then
    echo "Warning: create-dmg is not installed."
    echo "Install it with: brew install create-dmg"
    echo "Creating DMG using hdiutil instead..."
    
    # Create DMG directory
    mkdir -p "$DMG_DIR"
    
    # Copy app to DMG directory
    cp -R "$APP_PATH" "$DMG_DIR/"
    
    # Create a symbolic link to Applications
    ln -s /Applications "$DMG_DIR/Applications"
    
    # Create DMG
    hdiutil create -volname "$APP_NAME" -srcfolder "$DMG_DIR" -ov -format UDZO "${DIST_DIR}/${DMG_NAME}"
    
    # Clean up
    rm -rf "$DMG_DIR"
else
    # Use create-dmg for better results
    create-dmg \
        --volname "$APP_NAME" \
        --volicon "$ICNS_PATH" \
        --window-pos 200 120 \
        --window-size 600 300 \
        --icon-size 100 \
        --icon "$APP_NAME.app" 175 120 \
        --hide-extension "$APP_NAME.app" \
        --app-drop-link 425 120 \
        "${DIST_DIR}/${DMG_NAME}" \
        "${DIST_DIR}/"
fi

if [ -f "${DIST_DIR}/${DMG_NAME}" ]; then
    echo ""
    echo "✓ Build complete!"
    echo "  App bundle: ${APP_PATH}"
    echo "  DMG file: ${DIST_DIR}/${DMG_NAME}"
    echo ""
    echo "The DMG is ready for distribution."
else
    echo "Error: DMG was not created"
    exit 1
fi

