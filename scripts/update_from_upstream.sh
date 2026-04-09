#!/bin/bash

# Script to update the lerobot submodule from upstream
# This pulls the latest changes from https://github.com/huggingface/lerobot.git

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script's directory (parent repo root)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SUBMODULE_DIR="$SCRIPT_DIR/lerobot"

echo -e "${BLUE}=== Update lerobot Submodule from Upstream ===${NC}\n"

# Check if submodule directory exists
if [ ! -d "$SUBMODULE_DIR" ]; then
    echo -e "${RED}Error: lerobot submodule directory not found at $SUBMODULE_DIR${NC}"
    exit 1
fi

# Check if it's a git repository (handles both .git as file and directory)
if ! git -C "$SUBMODULE_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    echo -e "${RED}Error: $SUBMODULE_DIR is not a git repository${NC}"
    exit 1
fi

# Check what commit the parent repo is tracking
cd "$SCRIPT_DIR"
PARENT_TRACKED_COMMIT=$(git ls-tree HEAD lerobot 2>/dev/null | awk '{print $3}' || echo "")
if [ -n "$PARENT_TRACKED_COMMIT" ]; then
    PARENT_TRACKED_SHORT=$(git -C "$SUBMODULE_DIR" rev-parse --short "$PARENT_TRACKED_COMMIT" 2>/dev/null || echo "$PARENT_TRACKED_COMMIT")
    echo -e "${YELLOW}Parent repo tracks:${NC} $PARENT_TRACKED_SHORT"
fi

# Store current commit before update
cd "$SUBMODULE_DIR"
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
CURRENT_COMMIT=$(git rev-parse HEAD)
CURRENT_COMMIT_SHORT=$(git rev-parse --short HEAD)

echo -e "${YELLOW}Current submodule state:${NC}"
echo -e "  Branch: ${CURRENT_BRANCH}"
echo -e "  Commit: ${CURRENT_COMMIT_SHORT} (${CURRENT_COMMIT})"
if [ -n "$PARENT_TRACKED_COMMIT" ] && [ "$CURRENT_COMMIT" != "$PARENT_TRACKED_COMMIT" ]; then
    echo -e "  ${YELLOW}Note:${NC} Submodule is ahead of parent repo's tracked commit\n"
fi
echo ""

# Check if there are uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}Warning: You have uncommitted changes in the lerobot submodule${NC}"
    echo -e "${YELLOW}Do you want to stash them and continue? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        git stash
        echo -e "${GREEN}Changes stashed${NC}\n"
    else
        echo -e "${RED}Aborted${NC}"
        exit 1
    fi
fi

# Ensure we're on main branch (handle detached HEAD)
if [ "$CURRENT_BRANCH" = "HEAD" ]; then
    echo -e "${YELLOW}Submodule is in detached HEAD state. Checking out main branch...${NC}"
    if git show-ref --verify --quiet refs/heads/main; then
        git checkout main
    else
        git checkout -b main origin/main
    fi
    CURRENT_BRANCH="main"
fi

# Fetch latest changes
echo -e "${BLUE}Fetching latest changes from upstream...${NC}"
git fetch origin

# Check if we're behind
BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo "0")
AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "0")
UPDATED=false

# Check for divergent branches
if [ "$AHEAD" -gt "0" ] && [ "$BEHIND" -gt "0" ]; then
    echo -e "${YELLOW}Warning: Local branch has diverged from origin/main${NC}"
    echo -e "  Local commits ahead: $AHEAD"
    echo -e "  Upstream commits behind: $BEHIND"
    echo -e "${YELLOW}Resetting to origin/main to track upstream...${NC}"
    git reset --hard origin/main
    BEHIND=0
    AHEAD=0
fi

if [ "$BEHIND" -eq "0" ] && [ "$AHEAD" -eq "0" ]; then
    echo -e "${GREEN}Submodule is already up to date with upstream!${NC}\n"
    NEW_COMMIT="$CURRENT_COMMIT"
    NEW_COMMIT_SHORT="$CURRENT_COMMIT_SHORT"
else
    if [ "$BEHIND" -gt "0" ]; then
        echo -e "${YELLOW}Behind upstream by $BEHIND commit(s)${NC}\n"
        
        # Show what commits will be pulled
        echo -e "${BLUE}Commits to be pulled:${NC}"
        git log --oneline HEAD..origin/main | head -10
        if [ "$BEHIND" -gt 10 ]; then
            echo -e "  ... and $((BEHIND - 10)) more commit(s)"
        fi
        echo ""
        
        # Pull latest changes (fast-forward only to avoid merge conflicts)
        echo -e "${BLUE}Pulling latest changes...${NC}"
        git pull --ff-only origin main || git reset --hard origin/main
        
        # Get new commit
        NEW_COMMIT=$(git rev-parse HEAD)
        NEW_COMMIT_SHORT=$(git rev-parse --short HEAD)
        UPDATED=true
        
        echo -e "\n${GREEN}=== Submodule Update Complete ===${NC}"
        echo -e "${YELLOW}Updated from:${NC} ${CURRENT_COMMIT_SHORT}"
        echo -e "${YELLOW}Updated to:${NC}   ${NEW_COMMIT_SHORT}\n"
    fi
fi

# Go back to parent repo
cd "$SCRIPT_DIR"

# Show parent repo status
echo -e "${BLUE}Parent repository status:${NC}"
git status lerobot --short

# Check if parent repo shows the submodule as modified
if git diff --quiet lerobot; then
    echo -e "${GREEN}Parent repo is already tracking the updated commit${NC}"
else
    echo -e "\n${YELLOW}Note:${NC} The parent repository shows 'lerobot (new commits)'"
    echo -e "${YELLOW}This is normal - your parent repo tracks which commit the submodule points to.${NC}"
    echo -e "${YELLOW}Since lerobot is not your repo, you need to commit this submodule reference update.${NC}\n"
    
    echo -e "${YELLOW}Do you want to commit this submodule update to your parent repo? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Staging submodule update...${NC}"
        git add lerobot
        
        COMMIT_MSG="Update lerobot submodule to $NEW_COMMIT_SHORT"
        echo -e "${BLUE}Committing...${NC}"
        if git commit -m "$COMMIT_MSG"; then
            echo -e "${GREEN}Submodule update committed successfully!${NC}"
            echo -e "${YELLOW}Commit message:${NC} $COMMIT_MSG"
        else
            echo -e "${RED}Commit failed. You may need to commit manually.${NC}"
        fi
    else
        echo -e "${YELLOW}Submodule update not committed.${NC}"
        echo -e "${YELLOW}To commit later, run:${NC}"
        echo -e "  git add lerobot"
        echo -e "  git commit -m \"Update lerobot submodule to $NEW_COMMIT_SHORT\""
    fi
fi

