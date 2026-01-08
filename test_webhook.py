#!/usr/bin/env python3
"""
Script to send test webhook payloads to your locally running bot.
Run this after starting your Docker container.
"""

import requests
import json
import hmac
import hashlib
import sys

# Configuration
WEBHOOK_URL = "http://localhost:8080/webhook"
WEBHOOK_SECRET = "test-secret-123"  # Must match your container's env var

def create_signature(payload_bytes, secret):
    """Create GitHub webhook signature"""
    signature = hmac.new(
        secret.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    return f"sha256={signature}"

def send_issue_comment_event(issue_number=1849):
    """Simulate an issue comment event"""
    payload = {
        "action": "created",
        "issue": {
            "number": issue_number,
            "user": {
                "login": "test-author"
            }
        },
        "comment": {
            "user": {
                "login": "test-commenter"
            }
        },
        "repository": {
            "full_name": "archestra-ai/archestra"
        }
    }
    
    payload_bytes = json.dumps(payload).encode()
    signature = create_signature(payload_bytes, WEBHOOK_SECRET)
    
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "issue_comment",
        "X-Hub-Signature-256": signature
    }
    
    print(f"Sending issue_comment event for issue #{issue_number}...")
    try:
        response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
        print(f"Response: {response.status_code} - {response.text}")
        if response.status_code == 200:
            print("✅ Webhook processed successfully!")
            print("\nCheck container logs: docker logs reputation-bot-test --tail 50")
        else:
            print("❌ Webhook processing failed")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to webhook URL. Is the container running?")
        sys.exit(1)

def send_pr_event(pr_number=100):
    """Simulate a pull request opened event"""
    payload = {
        "action": "opened",
        "pull_request": {
            "number": pr_number,
            "user": {
                "login": "test-pr-author"
            }
        },
        "repository": {
            "full_name": "archestra-ai/archestra"
        }
    }
    
    payload_bytes = json.dumps(payload).encode()
    signature = create_signature(payload_bytes, WEBHOOK_SECRET)
    
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": signature
    }
    
    print(f"Sending pull_request event for PR #{pr_number}...")
    try:
        response = requests.post(WEBHOOK_URL, data=payload_bytes, headers=headers)
        print(f"Response: {response.status_code} - {response.text}")
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to webhook URL. Is the container running?")
        sys.exit(1)

if __name__ == "__main__":
    print("Testing webhook endpoints...")
    print("=" * 60)
    
    # Test health check first
    try:
        health_response = requests.get("http://localhost:8080/health")
        print(f"Health check: {health_response.status_code} - {health_response.text}")
    except:
        print("Error: Container is not running or not accessible on port 8080")
        sys.exit(1)
    
    print("\n1. Testing issue comment webhook:")
    send_issue_comment_event(1849)
    
    print("\n2. Testing pull request webhook:")
    send_pr_event(100)
    
    print("\nCheck your container logs to see the processing details!")