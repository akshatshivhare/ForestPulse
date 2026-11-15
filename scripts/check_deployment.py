"""Offline build check. Never creates assets, authenticates or submits jobs."""
import json
from backend.app.deployment import validate_demo_assets

if __name__ == '__main__':
    print(json.dumps({'status': 'ok', **validate_demo_assets()}))
