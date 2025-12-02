#!/usr/bin/env python3
import requests
import time
import sys
from datetime import datetime

RUN_ID = "f7509714-3516-49df-b632-493bd0694fb0"
API_URL = f"http://localhost:8000/api/pipeline/{RUN_ID}/status"

def monitor():
    while True:
        try:
            response = requests.get(API_URL, timeout=10)
            if response.status_code != 200:
                print(f"Error: {response.status_code}")
                time.sleep(10)
                continue

            data = response.json()

            print("\n" + "="*80)
            print(f"PREVENTION PIPELINE STATUS - {datetime.now().strftime('%H:%M:%S')}")
            print("="*80)
            print(f"\nRun ID: {data['run_id']}")
            print(f"Assessment: {data['assessment_name']}")
            print(f"Status: {data['status'].upper()}")
            print(f"Mode: {data['pipeline_config']['mode']}")
            print(f"Current Stage: {data['current_stage']}")
            print("\nStages:")

            for stage in data['stages']:
                icon = "✓" if stage['status'] == 'completed' else "⟳" if stage['status'] == 'running' else "○"
                duration = f"{stage['duration_ms']/1000:.1f}s" if stage['duration_ms'] else "running..."
                print(f"  {icon} {stage['name']:25s} {stage['status']:10s} {duration:>12s}")

            if data['status'] in ['completed', 'failed']:
                print("\n" + "="*80)
                print(f"Pipeline {data['status'].upper()}!")
                print("="*80)
                break

            print("\nRefreshing in 10 seconds...")
            time.sleep(10)

        except KeyboardInterrupt:
            print("\nMonitoring stopped.")
            sys.exit(0)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    monitor()
