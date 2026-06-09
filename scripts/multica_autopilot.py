"""Multica Autopilot Management CLI.

Provides commands to create, list, and delete scheduled agent runs
(autopilots) on the AutoGPT platform.

Usage:
    python scripts/multica_autopilot.py list
    python scripts/multica_autopilot.py create --name "Daily Lead Scrape" --agent vancouver_outreach/lead-scout --cron "0 8 * * *"
    python scripts/multica_autopilot.py delete --schedule-id <id>
"""
import argparse
import json
import sys
import urllib.request
import urllib.parse


AUTOPILOT_API_BASE = "http://10.128.0.3:8006/api/v1"


def api_request(method: str, path: str, data: dict | None = None, api_key: str | None = None) -> dict:
    url = f"{AUTOPILOT_API_BASE}{path}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        raise Exception(f"API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Connection error: {e}")


def list_autopilots(api_key: str) -> list[dict]:
    result = api_request("GET", "/tools/list-schedules", api_key=api_key)
    return result.get("schedules", [])


def create_autopilot(
    name: str,
    agent_slug: str,
    cron: str,
    inputs: dict,
    timezone: str,
    api_key: str,
) -> dict:
    data = {
        "username_agent_slug": agent_slug,
        "schedule_name": name,
        "cron": cron,
        "timezone": timezone,
        "inputs": inputs,
    }
    result = api_request("POST", "/tools/run-agent", data, api_key=api_key)
    return result


def delete_autopilot(schedule_id: str, api_key: str) -> dict:
    data = {"schedule_id": schedule_id}
    result = api_request("POST", "/tools/delete-schedule", data, api_key=api_key)
    return result


def main():
    parser = argparse.ArgumentParser(description="Multica Autopilot Management")
    sub = parser.add_subparsers(dest="command")

    list_cmd = sub.add_parser("list", help="List all scheduled autopilots")

    create_cmd = sub.add_parser("create", help="Create a new autopilot")
    create_cmd.add_argument("--name", required=True, help="Autopilot name")
    create_cmd.add_argument("--agent", required=True, help="Agent slug (e.g., vancouver_outreach/lead-scout)")
    create_cmd.add_argument("--cron", required=True, help="Cron expression (5-field)")
    create_cmd.add_argument("--timezone", default="America/Vancouver", help="IANA timezone")
    create_cmd.add_argument("--inputs", default="{}", help="JSON inputs for the agent")

    delete_cmd = sub.add_parser("delete", help="Delete an autopilot")
    delete_cmd.add_argument("--schedule-id", required=True, help="Schedule ID to delete")

    args = parser.parse_args()

    api_key = "YOUR_API_KEY"

    if args.command == "list":
        try:
            schedules = list_autopilots(api_key)
            if not schedules:
                print("No autopilots configured.")
            else:
                print(f"\n{'Name':<30} {'Agent':<35} {'Cron':<15} {'Next Run':<25}")
                print("-" * 105)
                for s in schedules:
                    print(f"{s.get('name', ''):<30} {s.get('graph_id', ''):<35} {s.get('cron', ''):<15} {s.get('next_run_time', ''):<25}")
        except Exception as e:
            print(f"Error: {e}")

    elif args.command == "create":
        try:
            inputs = json.loads(args.inputs)
            result = create_autopilot(
                name=args.name,
                agent_slug=args.agent,
                cron=args.cron,
                inputs=inputs,
                timezone=args.timezone,
                api_key=api_key,
            )
            print(f"Autopilot '{args.name}' created successfully!")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error: {e}")

    elif args.command == "delete":
        try:
            result = delete_autopilot(args.schedule_id, api_key)
            print(f"Autopilot '{args.schedule_id}' deleted.")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"Error: {e}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()