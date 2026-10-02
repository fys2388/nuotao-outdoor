#!/usr/bin/env python3
"""Dependency vulnerability scanner.

Scans backend Python dependencies for known vulnerabilities using pip-audit.
Also checks npm packages for the frontend.
"""

import subprocess
import sys
from pathlib import Path
from typing import Any


def scan_python_dependencies(backend_dir: Path) -> dict[str, Any]:
    """Scan Python dependencies for vulnerabilities."""
    print("=" * 60)
    print("Scanning Python dependencies...")
    print("=" * 60)
    
    result = {
        "language": "python",
        "directory": str(backend_dir),
        "total_vulnerabilities": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "vulnerabilities": [],
    }
    
    try:
        # Run pip-audit
        print("\nRunning pip-audit...")
        output = subprocess.run(
            [sys.executable, "-m", "pip_audit", "--format", "json", "-r", "requirements.txt"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        if output.returncode != 0 and output.returncode != 1:  # 1 = vulnerabilities found
            print(f"pip-audit error: {output.stderr}")
            result["error"] = output.stderr
            return result
        
        if output.stdout:
            import json
            data = json.loads(output.stdout)
            
            # Count vulnerabilities by severity
            for vuln in data.get("vulnerabilities", []):
                severity = vuln.get("severity", "unknown").lower()
                result["total_vulnerabilities"] += 1
                
                if severity == "critical":
                    result["critical"] += 1
                elif severity == "high":
                    result["high"] += 1
                elif severity == "medium":
                    result["medium"] += 1
                elif severity == "low":
                    result["low"] += 1
                
                result["vulnerabilities"].append({
                    "package": vuln.get("package", {}).get("name", "unknown"),
                    "version": vuln.get("package", {}).get("version", "unknown"),
                    "severity": vuln.get("severity", "unknown"),
                    "id": vuln.get("id", "unknown"),
                    "description": vuln.get("description", "")[:200],
                    "fix_version": vuln.get("fix_versions", []),
                })
        
        print(f"\nTotal vulnerabilities: {result['total_vulnerabilities']}")
        print(f"  Critical: {result['critical']}")
        print(f"  High: {result['high']}")
        print(f"  Medium: {result['medium']}")
        print(f"  Low: {result['low']}")
        
    except Exception as e:
        result["error"] = str(e)
        print(f"Error: {e}")
    
    return result


def scan_npm_dependencies(frontend_dir: Path) -> dict[str, Any]:
    """Scan npm dependencies for vulnerabilities."""
    print("\n" + "=" * 60)
    print("Scanning npm dependencies...")
    print("=" * 60)
    
    result = {
        "language": "javascript",
        "directory": str(frontend_dir),
        "total_vulnerabilities": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
        "vulnerabilities": [],
    }
    
    try:
        # Run npm audit
        print("\nRunning npm audit...")
        output = subprocess.run(
            ["npm", "audit", "--json"],
            cwd=frontend_dir,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        if output.returncode != 0 and output.returncode != 1:
            print(f"npm audit error: {output.stderr}")
            result["error"] = output.stderr
            return result
        
        if output.stdout:
            import json
            data = json.loads(output.stdout)
            
            metadata = data.get("metadata", {}).get("vulnerabilities", {})
            result["total_vulnerabilities"] = sum(metadata.values())
            result["critical"] = metadata.get("critical", 0)
            result["high"] = metadata.get("high", 0)
            result["medium"] = metadata.get("medium", 0)
            result["low"] = metadata.get("low", 0)
            
            # Parse vulnerabilities
            for pkg, info in data.get("dependencies", {}).items():
                if "vulnerabilities" in info:
                    for vuln_id, vuln in info["vulnerabilities"].items():
                        result["vulnerabilities"].append({
                            "package": pkg,
                            "severity": vuln.get("severity", "unknown"),
                            "id": vuln_id,
                            "description": vuln.get("description", "")[:200],
                            "fix_version": vuln.get("fixAvailable", ""),
                        })
        
        print(f"\nTotal vulnerabilities: {result['total_vulnerabilities']}")
        print(f"  Critical: {result['critical']}")
        print(f"  High: {result['high']}")
        print(f"  Medium: {result['medium']}")
        print(f"  Low: {result['low']}")
        
    except Exception as e:
        result["error"] = str(e)
        print(f"Error: {e}")
    
    return result


def main():
    """Run dependency vulnerability scan."""
    print("Nuotao AI OS - Dependency Vulnerability Scanner")
    print("=" * 60)
    print(f"Date: {__import__('datetime').datetime.utcnow().isoformat()}")
    print()
    
    project_root = Path(__file__).parent.parent
    
    # Scan Python dependencies
    backend_dir = project_root / "backend"
    if backend_dir.exists() and (backend_dir / "requirements.txt").exists():
        python_result = scan_python_dependencies(backend_dir)
    else:
        print("Backend directory or requirements.txt not found, skipping Python scan.")
        python_result = {"error": "Backend not found"}
    
    # Scan npm dependencies
    frontend_dir = project_root / "frontend"
    if frontend_dir.exists() and (frontend_dir / "package-lock.json").exists():
        npm_result = scan_npm_dependencies(frontend_dir)
    else:
        print("Frontend directory or package-lock.json not found, skipping npm scan.")
        npm_result = {"error": "Frontend not found"}
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_vulns = 0
    
    if "total_vulnerabilities" in python_result:
        total_vulns += python_result["total_vulnerabilities"]
        print(f"Python: {python_result['total_vulnerabilities']} vulnerabilities")
        if python_result["total_vulnerabilities"] > 0:
            print(f"  Critical: {python_result['critical']}")
            print(f"  High: {python_result['high']}")
            print(f"  Medium: {python_result['medium']}")
            print(f"  Low: {python_result['low']}")
    
    if "total_vulnerabilities" in npm_result:
        total_vulns += npm_result["total_vulnerabilities"]
        print(f"npm: {npm_result['total_vulnerabilities']} vulnerabilities")
        if npm_result["total_vulnerabilities"] > 0:
            print(f"  Critical: {npm_result['critical']}")
            print(f"  High: {npm_result['high']}")
            print(f"  Medium: {npm_result['medium']}")
            print(f"  Low: {npm_result['low']}")
    
    print(f"\nTotal: {total_vulns} vulnerabilities")
    
    if total_vulns == 0:
        print("\n✅ No vulnerabilities found!")
    else:
        print(f"\n⚠️  {total_vulns} vulnerabilities found. Please review and fix.")
        print("\nDetails:")
        for vuln in python_result.get("vulnerabilities", [])[:5]:
            print(f"  [Python] {vuln['package']}@{vuln['version']} - {vuln['severity']}")
        for vuln in npm_result.get("vulnerabilities", [])[:5]:
            print(f"  [npm] {vuln['package']} - {vuln['severity']}")
    
    return 0 if total_vulns == 0 else 1


if __name__ == "__main__":
    sys.exit(main())