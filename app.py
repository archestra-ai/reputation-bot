import os
import json
import hmac
import hashlib
import logging
import sys
from flask import Flask, request, jsonify
from github_client import GithubClient
from reputation import calculate_reputation, format_reputation_line

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
WEBHOOK_SECRET = os.environ.get('GITHUB_WEBHOOK_SECRET')
CORE_TEAM_MEMBERS = os.environ.get('CORE_TEAM_MEMBERS', '').split(',')
REPO_NAME = 'archestra-ai/archestra'

logger.info(f"Starting Reputation Bot")
logger.info(f"GITHUB_TOKEN: {'Set' if GITHUB_TOKEN else 'Not set'}")
logger.info(f"WEBHOOK_SECRET: {'Set' if WEBHOOK_SECRET else 'Not set'}")
logger.info(f"CORE_TEAM_MEMBERS: {CORE_TEAM_MEMBERS}")
logger.info(f"REPO_NAME: {REPO_NAME}")

github_client = GithubClient(GITHUB_TOKEN)

def verify_webhook_signature(payload, signature):
    if not WEBHOOK_SECRET:
        logger.warning("No webhook secret configured, skipping signature verification")
        return True
    
    expected_signature = 'sha256=' + hmac.new(
        WEBHOOK_SECRET.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    is_valid = hmac.compare_digest(expected_signature, signature)
    if not is_valid:
        logger.info(f"Expected signature: {expected_signature[:20]}...")
        logger.info(f"Received signature: {signature[:20]}...")
    logger.info(f"Webhook signature verification: {'Valid' if is_valid else 'Invalid'}")
    return is_valid

@app.route('/webhook', methods=['POST'])
def webhook():
    logger.info("Received webhook request")
    signature = request.headers.get('X-Hub-Signature-256', '')
    logger.info(f"Signature present: {bool(signature)}")
    
    # Get raw data for signature verification
    raw_data = request.get_data()
    
    if not verify_webhook_signature(raw_data, signature):
        logger.error("Invalid webhook signature")
        return jsonify({'error': 'Invalid signature'}), 401
    
    event = request.headers.get('X-GitHub-Event')
    
    # Handle ping event (might have empty body)
    if event == 'ping':
        logger.info("Received ping event")
        return jsonify({'status': 'pong'}), 200
    
    # Parse payload (can be JSON or form-encoded)
    if not raw_data:
        logger.warning(f"Empty payload for event: {event}")
        return jsonify({'status': 'ok'}), 200
    
    payload = None
    content_type = request.headers.get('Content-Type', '').lower()
    
    # Try to parse based on content type
    if 'application/x-www-form-urlencoded' in content_type:
        # GitHub sometimes sends form-encoded webhooks
        try:
            from urllib.parse import parse_qs
            form_data = parse_qs(raw_data.decode('utf-8'))
            if 'payload' in form_data:
                import json as json_module
                payload = json_module.loads(form_data['payload'][0])
                logger.info("Successfully parsed form-encoded webhook payload")
        except Exception as e:
            logger.error(f"Failed to parse form-encoded payload: {e}")
            logger.error(f"Raw data: {raw_data[:200]}")
            return jsonify({'error': 'Invalid form data'}), 400
    else:
        # Try to parse as JSON
        try:
            import json as json_module
            payload = json_module.loads(raw_data)
            logger.info("Successfully parsed JSON webhook payload")
        except json_module.JSONDecodeError as e:
            # Fallback: try form-encoded even without correct content-type
            try:
                from urllib.parse import parse_qs
                form_data = parse_qs(raw_data.decode('utf-8'))
                if 'payload' in form_data:
                    payload = json_module.loads(form_data['payload'][0])
                    logger.info("Successfully parsed form-encoded webhook payload (fallback)")
                else:
                    raise ValueError("No 'payload' field in form data")
            except Exception as e2:
                logger.error(f"Failed to parse JSON payload: {e}")
                logger.error(f"Failed to parse as form data: {e2}")
                logger.error(f"Raw data: {raw_data[:200]}")
                return jsonify({'error': 'Invalid payload format'}), 400
    
    logger.info(f"GitHub Event: {event}")
    logger.info(f"Payload action: {payload.get('action') if payload else 'No payload'}")
    
    try:
        if event == 'pull_request':
            logger.info("Handling pull request event")
            handle_pull_request(payload)
        elif event == 'issues':
            logger.info("Handling issue event")
            handle_issue(payload)
        elif event == 'issue_comment':
            logger.info("Handling issue comment event")
            handle_issue_comment(payload)
        else:
            logger.info(f"Ignoring event type: {event}")
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500
    
    logger.info("Webhook processed successfully")
    return jsonify({'status': 'ok'}), 200

def handle_pull_request(payload):
    action = payload.get('action')
    logger.info(f"PR action: {action}")
    if action not in ['opened', 'reopened']:
        logger.info(f"Ignoring PR action: {action}")
        return
    
    pr = payload.get('pull_request', {})
    pr_number = pr.get('number')
    author = pr.get('user', {}).get('login')
    
    logger.info(f"PR #{pr_number} by @{author}")
    
    if not author or not pr_number:
        logger.error(f"Missing PR data: author={author}, pr_number={pr_number}")
        return
    
    logger.info(f"Fetching reputation for @{author}")
    reputation_data = github_client.get_user_reputation(REPO_NAME, author, CORE_TEAM_MEMBERS)
    reputation_score = calculate_reputation(reputation_data)
    reputation_line = format_reputation_line(reputation_score, reputation_data)
    
    logger.info(f"Reputation calculated: {reputation_score} points")
    
    comment_body = f"{reputation_line}\n\n_Generated by Reputation Bot_"
    logger.info(f"Posting comment to PR #{pr_number}")
    github_client.post_comment(REPO_NAME, pr_number, comment_body)
    logger.info(f"Comment posted successfully to PR #{pr_number}")

def handle_issue(payload):
    action = payload.get('action')
    logger.info(f"Issue action: {action}")
    if action not in ['opened', 'reopened']:
        logger.info(f"Ignoring issue action: {action}")
        return
    
    issue = payload.get('issue', {})
    issue_number = issue.get('number')
    author = issue.get('user', {}).get('login')
    
    logger.info(f"Issue #{issue_number} by @{author}")
    
    if not author or not issue_number:
        logger.error(f"Missing issue data: author={author}, issue_number={issue_number}")
        return
    
    post_or_update_issue_reputation(issue_number)

def handle_issue_comment(payload):
    action = payload.get('action')
    logger.info(f"Issue comment action: {action}")
    if action != 'created':
        logger.info(f"Ignoring comment action: {action}")
        return
    
    issue = payload.get('issue', {})
    issue_number = issue.get('number')
    comment_author = payload.get('comment', {}).get('user', {}).get('login')
    
    logger.info(f"Comment on issue #{issue_number} by @{comment_author}")
    
    if not issue_number:
        logger.error(f"Missing issue number")
        return
    
    post_or_update_issue_reputation(issue_number)

def post_or_update_issue_reputation(issue_number):
    logger.info(f"Getting participants for issue #{issue_number}")
    participants = github_client.get_issue_participants(REPO_NAME, issue_number)
    
    if not participants:
        logger.warning(f"No participants found for issue #{issue_number}")
        return
    
    logger.info(f"Found {len(participants)} participants: {participants}")
    
    # Collect all participant data first
    participant_data = []
    for username in participants:
        logger.info(f"Fetching reputation for @{username}")
        reputation_data = github_client.get_user_reputation(REPO_NAME, username, CORE_TEAM_MEMBERS)
        reputation_score = calculate_reputation(reputation_data)
        participant_data.append({
            'username': username,
            'score': reputation_score,
            'data': reputation_data
        })
        logger.info(f"@{username}: {reputation_score} points")
    
    # Sort by reputation score (highest first)
    participant_data.sort(key=lambda x: x['score'], reverse=True)
    
    comment_body = "## 📊 Reputation Summary\n\n"
    comment_body += "| User | Rep | Pull Requests | Activity | Core Reactions |\n"
    comment_body += "|------|-----|---------------|----------|----------------|\n"
    
    for participant in participant_data:
        reputation_data = participant['data']
        reputation_score = participant['score']
        username = participant['username']
        
        pr_str = f"{reputation_data['merged_prs']}✅ {reputation_data['open_prs']}🔄 {reputation_data['closed_prs']}❌"
        activity_str = f"{reputation_data['issues']} issues, {reputation_data['comments']} comments"
        
        core_str = ""
        if reputation_data['core_thumbs_up'] > 0:
            core_str += f"+{reputation_data['core_thumbs_up']}👍"
        if reputation_data['core_thumbs_down'] > 0:
            if core_str:
                core_str += " "
            core_str += f"-{reputation_data['core_thumbs_down']}👎"
        if not core_str:
            core_str = "—"
        
        comment_body += f"| **@{username}** | ⚡ {reputation_score} | {pr_str} | {activity_str} | {core_str} |\n"
    
    comment_body += "\n---\n"
    comment_body += "_Generated by [Reputation Bot](https://github.com/archestra-ai/reputation-bot)_ 🤖"
    
    # Check for existing comment RIGHT BEFORE posting to avoid race conditions
    logger.info(f"Checking for existing bot comment on issue #{issue_number} (final check)")
    existing_comment = github_client.find_bot_comment(REPO_NAME, issue_number)
    
    if existing_comment:
        logger.info(f"Found existing comment {existing_comment['id']}, updating it")
        github_client.update_comment(REPO_NAME, existing_comment['id'], comment_body)
    else:
        # Double-check one more time to handle race conditions
        logger.info(f"No existing comment found, checking once more before posting")
        existing_comment = github_client.find_bot_comment(REPO_NAME, issue_number)
        if existing_comment:
            logger.info(f"Found existing comment on second check {existing_comment['id']}, updating it")
            github_client.update_comment(REPO_NAME, existing_comment['id'], comment_body)
        else:
            logger.info(f"Posting new comment to issue #{issue_number}")
            github_client.post_comment(REPO_NAME, issue_number, comment_body)
    
    logger.info(f"Issue #{issue_number} reputation updated successfully")

@app.route('/health', methods=['GET'])
def health():
    logger.info("Health check requested")
    return jsonify({'status': 'healthy'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"Starting Flask app on port {port}")
    app.run(host='0.0.0.0', port=port)