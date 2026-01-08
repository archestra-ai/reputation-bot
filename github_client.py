import requests
import logging
from github import Github
from typing import List, Dict, Optional, Set

logger = logging.getLogger(__name__)

class GithubClient:
    def __init__(self, token: str):
        self.token = token
        self.github = Github(token)
        self.headers = {
            'Authorization': f'token {token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        logger.info(f"GitHub client initialized with token: {'***' + token[-4:] if token else 'None'}")
    
    def get_user_reputation(self, repo_name: str, username: str, core_team: List[str]) -> Dict:
        """Get reputation data for a user in a specific repository."""
        logger.info(f"Getting reputation for user @{username} in {repo_name}")
        logger.info(f"Core team members: {core_team}")
        
        try:
            repo = self.github.get_repo(repo_name)
        except Exception as e:
            logger.error(f"Failed to get repo {repo_name}: {str(e)}")
            raise
        
        merged_prs = 0
        open_prs = 0
        closed_prs = 0
        issues_created = 0
        comments_count = 0
        thumbs_up_from_core = 0
        thumbs_down_from_core = 0
        
        # Try GitHub Search API first (faster)
        logger.info(f"Searching for PRs by @{username} using search API")
        pr_fetch_success = False
        try:
            # Search for all PRs by this user in this repo
            pr_query = f"repo:{repo_name} author:{username} is:pr"
            pr_results = self.github.search_issues(query=pr_query)
            
            pr_count = 0
            # Limit to first 100 PRs for performance
            for pr_data in pr_results[:100]:
                pr_count += 1
                pr = repo.get_pull(pr_data.number)
                if pr.merged:
                    merged_prs += 1
                elif pr.state == 'open':
                    open_prs += 1
                elif pr.state == 'closed':
                    closed_prs += 1
            
            logger.info(f"Found {pr_count} PRs for @{username}: {merged_prs} merged, {open_prs} open, {closed_prs} closed")
            pr_fetch_success = True
        except Exception as e:
            logger.warning(f"Search API failed for @{username}: {str(e)}")
            logger.info(f"Falling back to direct PR fetch for @{username}")
            
        # Fallback to direct PR fetching if search fails
        if not pr_fetch_success:
            try:
                # Fetch recent PRs and filter by username
                pr_count = 0
                checked_prs = 0
                max_to_check = 300  # Limit to prevent timeout
                
                # PyGithub uses automatic pagination
                prs = repo.get_pulls(state='all')
                for pr in prs:
                    checked_prs += 1
                    if checked_prs > max_to_check:
                        logger.info(f"Reached PR check limit of {max_to_check}")
                        break
                        
                    if pr.user.login == username:
                        pr_count += 1
                        if pr.merged:
                            merged_prs += 1
                        elif pr.state == 'open':
                            open_prs += 1
                        elif pr.state == 'closed':
                            closed_prs += 1
                
                logger.info(f"Fallback: Checked {checked_prs} PRs, found {pr_count} for @{username}: {merged_prs} merged, {open_prs} open, {closed_prs} closed")
            except Exception as e:
                logger.error(f"Fallback PR fetch also failed: {str(e)}")
                # Leave counts at 0 instead of using fake data
        
        # Try GitHub Search API for issues
        logger.info(f"Searching for issues by @{username} using search API")
        issue_fetch_success = False
        try:
            # Search for issues (not PRs) created by this user
            issue_query = f"repo:{repo_name} author:{username} is:issue"
            issue_results = self.github.search_issues(query=issue_query)
            
            # Count up to 100 issues
            issues_created = min(issue_results.totalCount, 100)
            logger.info(f"Found {issues_created} issues created by @{username}")
            issue_fetch_success = True
        except Exception as e:
            logger.warning(f"Search API failed for issues: {str(e)}")
            logger.info(f"Falling back to direct issue fetch for @{username}")
        
        # Fallback to direct issue fetching if search fails
        if not issue_fetch_success:
            try:
                # Use creator parameter in get_issues
                issues = repo.get_issues(state='all', creator=username)
                for issue in issues[:100]:  # Limit to 100 issues
                    if not issue.pull_request:
                        issues_created += 1
                logger.info(f"Fallback: Found {issues_created} issues created by @{username}")
            except Exception as e:
                logger.error(f"Fallback issue fetch also failed: {str(e)}")
                # Leave count at 0
        
        # Try to count comments
        logger.info(f"Counting comments by @{username}")
        try:
            query = f"repo:{repo_name} commenter:{username}"
            search_results = self.github.search_issues(query=query)
            
            # Just use the count from search results
            comments_count = min(search_results.totalCount, 50)  # Cap at 50 for performance
            logger.info(f"Found approximately {comments_count} issues/PRs with comments from @{username}")
            
            # For reactions, just check a few recent items
            logger.info(f"Checking reactions on recent items (limited for performance)")
            for item in list(search_results)[:5]:  # Only check 5 items
                try:
                    issue = repo.get_issue(item.number)
                    # Check reactions on the issue itself if author matches
                    if issue.user.login == username:
                        reactions = issue.get_reactions()
                        for reaction in reactions:
                            if reaction.user.login in core_team:
                                if reaction.content == '+1':
                                    thumbs_up_from_core += 1
                                elif reaction.content == '-1':
                                    thumbs_down_from_core += 1
                except Exception as e:
                    logger.warning(f"Error checking reactions on item {item.number}: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.warning(f"Error searching comments: {str(e)}")
            # Comments count stays at 0, which is more accurate than fake data
            logger.info(f"Comments count will remain at 0 for @{username}")
        
        # Skip additional reaction checking for performance
        logger.info(f"Skipping additional reaction checks for performance")
        
        result = {
            'merged_prs': merged_prs,
            'open_prs': open_prs,
            'closed_prs': closed_prs,
            'issues': issues_created,
            'comments': comments_count,
            'core_thumbs_up': thumbs_up_from_core,
            'core_thumbs_down': thumbs_down_from_core
        }
        
        logger.info(f"Reputation data for @{username}: {result}")
        return result
    
    def get_issue_participants(self, repo_name: str, issue_number: int) -> Set[str]:
        """Get all participants (author + commenters) in an issue."""
        logger.info(f"Getting participants for issue #{issue_number} in {repo_name}")
        
        try:
            repo = self.github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)
        except Exception as e:
            logger.error(f"Failed to get issue #{issue_number}: {str(e)}")
            raise
        
        participants = {issue.user.login}
        logger.info(f"Issue author: @{issue.user.login}")
        
        comment_count = 0
        # Limit to first 30 comments for performance
        for comment in list(issue.get_comments())[:30]:
            # Skip London-Cat bot
            if comment.user.login == 'London-Cat':
                logger.info(f"Skipping comment from London-Cat bot")
                continue
            participants.add(comment.user.login)
            comment_count += 1
            if len(participants) >= 10:  # Limit to 10 participants max
                logger.info(f"Reached participant limit of 10, stopping")
                break
        
        logger.info(f"Processed {comment_count} comments")
        
        # Filter out bot accounts and London-Cat
        before_filter = len(participants)
        participants = {p for p in participants if not p.endswith('[bot]') and p != 'London-Cat'}
        logger.info(f"Participants after filtering bots: {len(participants)} (filtered {before_filter - len(participants)} bots)")
        logger.info(f"Participants: {list(participants)}")
        
        return participants
    
    def post_comment(self, repo_name: str, issue_number: int, body: str):
        """Post a comment to an issue or PR."""
        logger.info(f"Posting comment to issue #{issue_number} in {repo_name}")
        logger.debug(f"Comment body length: {len(body)} chars")
        
        try:
            repo = self.github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)
            comment = issue.create_comment(body)
            logger.info(f"Comment posted successfully with ID: {comment.id}")
        except Exception as e:
            logger.error(f"Failed to post comment: {str(e)}")
            raise
    
    def find_bot_comment(self, repo_name: str, issue_number: int) -> Optional[Dict]:
        """Find an existing bot comment on an issue."""
        logger.info(f"Searching for existing bot comment on issue #{issue_number}")
        
        try:
            repo = self.github.get_repo(repo_name)
            issue = repo.get_issue(issue_number)
            
            # Get the authenticated user (the bot itself)
            bot_user = self.github.get_user()
            bot_username = bot_user.login
            logger.info(f"Bot username: {bot_username}")
            
            for comment in issue.get_comments():
                # Check if comment is from our bot AND contains our signature
                # Check multiple possible signatures for robustness
                is_bot_comment = (
                    comment.user.login == bot_username or
                    'Generated by Reputation Bot' in comment.body or
                    'Generated by [Reputation Bot]' in comment.body or
                    '📊 Reputation Summary' in comment.body
                )
                
                if is_bot_comment:
                    logger.info(f"Found existing bot comment with ID: {comment.id} from user: {comment.user.login}")
                    return {
                        'id': comment.id,
                        'body': comment.body
                    }
            
            logger.info(f"No existing bot comment found (checked comments from users)")
            return None
        except Exception as e:
            logger.error(f"Error searching for bot comment: {str(e)}")
            raise
    
    def update_comment(self, repo_name: str, comment_id: int, body: str):
        """Update an existing comment."""
        logger.info(f"Updating comment {comment_id} in {repo_name}")
        logger.debug(f"New comment body length: {len(body)} chars")
        
        url = f"https://api.github.com/repos/{repo_name}/issues/comments/{comment_id}"
        try:
            response = requests.patch(url, headers=self.headers, json={'body': body})
            response.raise_for_status()
            logger.info(f"Comment {comment_id} updated successfully")
        except Exception as e:
            logger.error(f"Failed to update comment: {str(e)}")
            raise