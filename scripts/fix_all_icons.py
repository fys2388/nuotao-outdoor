"""Fix invalid icon imports - remove lines with invalid icons"""
import re
import os

# Invalid icons that don't exist in @ant-design/icons
invalid_icons = [
    "TargetOutlined", "ContractOutlined", "PackageOutlined", "LanguageOutlined",
    "RowHeightOutlined", "UnlinkOutlined", "TelegramOutlined", "EbayOutlined",
    "ShopifyOutlined", "WordpressOutlined", "Css3Outlined", "JavascriptOutlined",
    "ReactOutlined", "VueOutlined", "AngularOutlined", "ShieldOutlined",
    "MedalOutlined", "AwardOutlined", "UnfoldOutlined", "FoldOutlined",
    "AlipaySquareOutlined", "TaobaoSquareOutlined", "MediumMarkOutlined",
    "GooglePlusCircleOutlined", "GooglePlusSquareOutlined", "RedditCircleOutlined",
    "RedditSquareOutlined", "WhatsAppSquareOutlined", "TwitterSquareOutlined",
    "TwitterCircleOutlined",
]

# Files to fix
files = [
    "frontend/src/pages/ListingLocalization.tsx",
    "frontend/src/pages/Influencer.tsx",
    "frontend/src/pages/FinanceReport.tsx",
]

for filepath in files:
    if not os.path.exists(filepath):
        print(f"SKIP: {filepath} not found")
        continue
    
    print(f"FIXING: {filepath}")
    
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    new_lines = []
    in_icons_import = False
    seen_thunderbolt = False
    
    for line in lines:
        stripped = line.strip()
        
        # Detect @ant-design/icons import start
        if stripped == "import {":
            # Check if this is the icons import
            for i in range(len(lines)):
                if "@ant-design/icons'" in lines[i] and lines[i].strip() == "} from '@ant-design/icons'":
                    in_icons_import = True
                    new_lines.append(line)
                    break
            continue
        
        if in_icons_import:
            if stripped == "} from '@ant-design/icons'":
                in_icons_import = False
                new_lines.append(line)
                continue
            
            # Skip empty lines and lines with only commas
            if stripped == '' or stripped == ',':
                continue
            
            # Check if this line contains invalid icons
            has_invalid = False
            for icon in invalid_icons:
                if icon in line:
                    has_invalid = True
                    break
            
            if has_invalid:
                # Remove this line entirely
                continue
            
            # Handle duplicate ThunderboltOutlined
            if "ThunderboltOutlined" in line:
                if seen_thunderbolt:
                    # Remove duplicate
                    continue
                else:
                    seen_thunderbolt = True
            
            # Fix JavascriptOutlined -> JavaScriptOutlined
            if "JavascriptOutlined" in line:
                line = line.replace("JavascriptOutlined", "JavaScriptOutlined")
            
            new_lines.append(line)
        else:
            new_lines.append(line)
    
    content = ''.join(new_lines)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"  Fixed: {filepath}")

print("\nDone!")