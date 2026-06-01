#!/usr/bin/env python3
"""
Basic test to verify core dependencies and imports work correctly.
This test is designed to run in CI/CD to verify the setuptools fix.
"""

def test_pkg_resources_import():
    """Test that pkg_resources can be imported (fixes the original pytest issue)"""
    try:
        import pkg_resources
        print("✓ pkg_resources import successful")
        return True
    except ImportError as e:
        print(f"✗ pkg_resources import failed: {e}")
        return False

def test_apscheduler_import():
    """Test that apscheduler can be imported (the original failing dependency)"""
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        print("✓ APScheduler import successful")
        return True
    except ImportError as e:
        print(f"✗ APScheduler import failed: {e}")
        return False

def test_core_dependencies():
    """Test that core dependencies can be imported"""
    dependencies = [
        ("fastapi", "from fastapi import FastAPI"),
        ("pydantic", "from pydantic import BaseModel"),
        ("sqlalchemy", "from sqlalchemy import create_engine"),
        ("httpx", "import httpx"),
        ("python_dotenv", "from dotenv import load_dotenv"),
    ]
    
    results = []
    for name, import_stmt in dependencies:
        try:
            exec(import_stmt)
            print(f"✓ {name} import successful")
            results.append(True)
        except ImportError as e:
            print(f"✗ {name} import failed: {e}")
            results.append(False)
    
    return all(results)

def main():
    """Run all basic tests"""
    print("Running basic dependency tests...")
    print("=" * 50)
    
    tests = [
        test_pkg_resources_import,
        test_apscheduler_import,
        test_core_dependencies,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test {test.__name__} failed with exception: {e}")
            results.append(False)
        print("-" * 30)
    
    success_count = sum(results)
    total_count = len(results)
    
    print(f"Test Results: {success_count}/{total_count} passed")
    
    if all(results):
        print("🎉 All basic tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1

if __name__ == "__main__":
    exit(main())