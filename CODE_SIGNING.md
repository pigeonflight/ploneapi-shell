# Code Signing Guide for Plone API Shell

This guide explains how to code sign the macOS app bundle to avoid Gatekeeper security warnings.

## Prerequisites

1. **Apple Developer Account**: You need an active Apple Developer account ($99/year)
2. **Code Signing Certificate**: Install a "Developer ID Application" certificate in your Keychain

## Setting Up Code Signing

### Step 1: Get Your Code Signing Identity

**Important**: For distribution outside the Mac App Store, you need a **"Developer ID Application"** certificate, not an "Apple Development" certificate.

1. Open **Keychain Access** on your Mac
2. Look for a certificate named "Developer ID Application: Your Name (TEAM_ID)"
3. If you don't have one:
   - Go to [Apple Developer Portal](https://developer.apple.com/account/resources/certificates/list)
   - Click the "+" button to create a new certificate
   - Select **"Developer ID Application"** (not "Apple Development")
   - Follow the instructions to create a Certificate Signing Request (CSR)
   - Download and install the certificate in Keychain Access

**Note**: "Apple Development" certificates are for development/testing only. "Developer ID Application" certificates are required for distribution.

### Step 2: Find Your Identity Name

Run this command to list available code signing identities:

```bash
security find-identity -v -p codesigning
```

Look for a line like:
```
1) ABC1234567890ABCDEF1234567890ABCDEF1234 "Developer ID Application: Your Name (TEAM_ID)"
```

The full identity string is: `Developer ID Application: Your Name (TEAM_ID)`

### Step 3: Build with Code Signing

#### Option 1: Set Environment Variable

```bash
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAM_ID)"
./build_app.sh
```

#### Option 2: Pass as Argument

```bash
./build_app.sh "Developer ID Application: Your Name (TEAM_ID)"
```

#### Option 3: Export and Run

```bash
export CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAM_ID)"
export ENTITLEMENTS_FILE="/path/to/entitlements.plist"  # Optional
./build_app.sh
```

## Optional: Notarization

For distribution outside the Mac App Store, you should also notarize your app. This requires:

1. **App-specific password** for your Apple ID
2. **Notarization script** (can be added to build process)

### Notarization Process

After building and code signing:

```bash
# Create a zip for notarization
ditto -c -k --keepParent "dist/PloneAPIShell.app" "dist/PloneAPIShell.zip"

# Submit for notarization
xcrun notarytool submit "dist/PloneAPIShell.zip" \
    --apple-id "your@email.com" \
    --team-id "YOUR_TEAM_ID" \
    --password "app-specific-password" \
    --wait

# Staple the notarization ticket
xcrun stapler staple "dist/PloneAPIShell.app"
```

## Verification

After building, verify the code signature:

```bash
codesign --verify --verbose dist/PloneAPIShell.app
spctl --assess --verbose dist/PloneAPIShell.app
```

## Troubleshooting

### "No identity found"
- Make sure the certificate is installed in Keychain Access
- Use the exact identity string from `security find-identity -v -p codesigning`
- The identity must be a "Developer ID Application" certificate (not "Apple Development")

### "Resource fork, Finder information, or similar detritus not allowed"
- This can happen with nested app bundles
- Try: `codesign --force --deep --sign "$CODESIGN_IDENTITY" "$APP_PATH"`

### Gatekeeper still shows warning
- The app may need notarization for distribution
- For personal use, users can right-click and select "Open" to bypass Gatekeeper once

## References

- [Apple Code Signing Guide](https://developer.apple.com/library/archive/documentation/Security/Conceptual/CodeSigningGuide/)
- [Notarization Guide](https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution)

