"""Fix invalid icon imports in CustomerTemplates.tsx - preserve proper syntax"""
import re

# Invalid icons that don't exist in @ant-design/icons
invalid_icons = {
    "TargetOutlined", "ContractOutlined", "PackageOutlined", "LanguageOutlined",
    "RowHeightOutlined", "UnlinkOutlined", "TelegramOutlined", "EbayOutlined",
    "ShopifyOutlined", "WordpressOutlined", "Css3Outlined", "JavascriptOutlined",
    "ReactOutlined", "VueOutlined", "AngularOutlined", "ShieldOutlined",
    "MedalOutlined", "AwardOutlined", "UnfoldOutlined", "FoldOutlined",
    "AlipaySquareOutlined", "TaobaoSquareOutlined", "MediumMarkOutlined",
    "GooglePlusCircleOutlined", "GooglePlusSquareOutlined", "RedditCircleOutlined",
    "RedditSquareOutlined", "WhatsAppSquareOutlined", "TwitterSquareOutlined",
    "TwitterCircleOutlined", "QqFilled", "DribbbleFilled", "BehanceFilled",
    "MediumFilled", "GooglePlusFilled", "RedditFilled", "WhatsAppFilled",
}

with open("frontend/src/pages/CustomerTemplates.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Track if we're in the @ant-design/icons import block
in_icons_import = False
new_lines = []
prev_line_ends_with_comma = True

for i, line in enumerate(lines):
    stripped = line.strip()
    
    # Detect @ant-design/icons import block
    if stripped == "import {":
        # Check if next non-empty line contains '@ant-design/icons'
        for j in range(i, min(i+250, len(lines))):
            if "@ant-design/icons'" in lines[j]:
                in_icons_import = True
                new_lines.append(line)
                break
        else:
            new_lines.append(line)
        continue
    
    if in_icons_import:
        if stripped == "} from '@ant-design/icons'":
            in_icons_import = False
            new_lines.append(line)
            continue
        
        # Remove lines containing invalid icons
        has_invalid = False
        for icon in invalid_icons:
            # Check if icon appears in this line (with optional "as Alias")
            if re.search(rf'\b{icon}\b(?:\s+as\s+\w+)?', line):
                has_invalid = True
                break
        
        if has_invalid:
            # Skip this line entirely
            continue
        
        # Handle duplicate ThunderboltOutlined
        if "ThunderboltOutlined" in line and "ThunderboltOutlined" in ''.join(new_lines[-5:]):
            continue
        
        # Handle JavaScriptOutlined fix
        if "JavascriptOutlined" in line:
            line = line.replace("JavascriptOutlined", "JavaScriptOutlined")
        
        new_lines.append(line)
    else:
        new_lines.append(line)

content = ''.join(new_lines)

# Clean up any double commas or trailing commas at start of line
content = re.sub(r',\s*,', ',', content)
content = re.sub(r'^\s*,\s*', '', content, flags=re.MULTILINE)

with open("frontend/src/pages/CustomerTemplates.tsx", "w", encoding="utf-8") as f:
    f.write(content)

print("Fixed CustomerTemplates.tsx imports")