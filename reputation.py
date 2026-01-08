from typing import Dict

def calculate_reputation(data: Dict) -> int:
    """Calculate reputation score based on GitHub activity."""
    score = 0
    
    # PRs scoring
    score += data['merged_prs'] * 20
    score += data['open_prs'] * 3
    score -= data['closed_prs'] * 10
    
    # Issues (comments don't add to score, just displayed)
    score += data['issues'] * 5
    
    # Core team reactions
    score += data['core_thumbs_up'] * 15
    score -= data['core_thumbs_down'] * 50
    
    return score  # Allow negative scores

def format_reputation_line(score: int, data: Dict) -> str:
    """Format the reputation data into a compact single line."""
    pr_str = f"{data['merged_prs']}✅/{data['open_prs']}🔄/{data['closed_prs']}❌"
    activity_str = f"{data['issues']} issues, {data['comments']} comments"
    
    # Format core team reactions
    core_str = ""
    if data['core_thumbs_up'] > 0:
        core_str += f"+{data['core_thumbs_up']}👍"
    if data['core_thumbs_down'] > 0:
        if core_str:
            core_str += " "
        core_str += f"-{data['core_thumbs_down']}👎"
    
    if not core_str:
        core_str = "No reactions"
    
    return f"⚡ Rep: {score} | PRs: {pr_str} | Activity: {activity_str} | Core: {core_str}"