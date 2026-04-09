#!/bin/bash

# Script to update the dev branch with the current branch
# This merges the current branch into dev branch

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script's directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Source and target branches
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
TARGET_BRANCH="dev"

echo -e "${BLUE}=== Update dev Branch with Current Branch ===${NC}\n"

# Check if we're already on dev branch
if [ "$CURRENT_BRANCH" = "$TARGET_BRANCH" ]; then
    echo -e "${YELLOW}You are already on the dev branch${NC}"
    echo -e "${YELLOW}Do you want to pull latest changes from remote instead? (y/n)${NC}"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Pulling latest changes from origin/dev...${NC}"
        git pull origin dev
        echo -e "${GREEN}Done!${NC}"
        exit 0
    else
        echo -e "${RED}Aborted${NC}"
        exit 1
    fi
fi

# Check if target branch exists
if ! git show-ref --verify --quiet refs/heads/"$TARGET_BRANCH"; then
    echo -e "${YELLOW}Target branch '$TARGET_BRANCH' does not exist locally${NC}"
    echo -e "${BLUE}Checking if it exists on remote...${NC}"
    if git ls-remote --heads origin "$TARGET_BRANCH" | grep -q "$TARGET_BRANCH"; then
        echo -e "${YELLOW}Creating local branch from origin/$TARGET_BRANCH...${NC}"
        git checkout -b "$TARGET_BRANCH" "origin/$TARGET_BRANCH"
        CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
    else
        echo -e "${RED}Error: Branch '$TARGET_BRANCH' does not exist locally or remotely${NC}"
        exit 1
    fi
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${YELLOW}Warning: You have uncommitted changes${NC}"
    echo -e "${YELLOW}Current branch: $CURRENT_BRANCH${NC}"
    echo -e "${YELLOW}Target branch: $TARGET_BRANCH${NC}\n"
    echo -e "${YELLOW}Options:${NC}"
    echo -e "  1) Stash changes, update dev, then reapply stashed changes"
    echo -e "  2) Commit changes first (you'll need to do this manually)"
    echo -e "  3) Abort"
    echo -e "${YELLOW}Choose an option (1/2/3):${NC}"
    read -r option
    
    if [ "$option" = "1" ]; then
        echo -e "${BLUE}Stashing changes...${NC}"
        git stash
        STASHED=true
    elif [ "$option" = "2" ]; then
        echo -e "${YELLOW}Please commit your changes first, then run this script again${NC}"
        exit 1
    else
        echo -e "${RED}Aborted${NC}"
        exit 1
    fi
else
    STASHED=false
fi

# Store the original branch
ORIGINAL_BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Get current commit info
CURRENT_COMMIT=$(git rev-parse --short HEAD)
echo -e "${YELLOW}Current branch:${NC} $ORIGINAL_BRANCH (commit: $CURRENT_COMMIT)"
echo -e "${YELLOW}Target branch:${NC} $TARGET_BRANCH\n"

# Checkout target branch
echo -e "${BLUE}Checking out $TARGET_BRANCH branch...${NC}"
git checkout "$TARGET_BRANCH"

# Update target branch from remote if it exists
if git ls-remote --heads origin "$TARGET_BRANCH" | grep -q "$TARGET_BRANCH"; then
    echo -e "${BLUE}Pulling latest changes from origin/$TARGET_BRANCH...${NC}"
    git pull origin "$TARGET_BRANCH" || echo -e "${YELLOW}Note: Could not pull from remote (may be ahead or no remote)${NC}"
fi

TARGET_BEFORE_COMMIT=$(git rev-parse --short HEAD)

# Merge the original branch into target branch
echo -e "\n${BLUE}Merging $ORIGINAL_BRANCH into $TARGET_BRANCH...${NC}"
if git merge "$ORIGINAL_BRANCH" --no-edit; then
    echo -e "${GREEN}Merge successful!${NC}"
    MERGE_SUCCESS=true
else
    echo -e "${RED}Merge conflict detected!${NC}"
    echo -e "${YELLOW}Please resolve conflicts manually and then:${NC}"
    echo -e "  git add ."
    echo -e "  git commit"
    MERGE_SUCCESS=false
fi

TARGET_AFTER_COMMIT=$(git rev-parse --short HEAD)

echo -e "\n${GREEN}=== Update Summary ===${NC}"
echo -e "${YELLOW}Merged:${NC} $ORIGINAL_BRANCH -> $TARGET_BRANCH"
echo -e "${YELLOW}Before:${NC} $TARGET_BEFORE_COMMIT"
echo -e "${YELLOW}After:${NC}  $TARGET_AFTER_COMMIT"

# Ask if user wants to push to remote
if [ "$MERGE_SUCCESS" = true ]; then
    if git ls-remote --heads origin "$TARGET_BRANCH" | grep -q "$TARGET_BRANCH"; then
        echo -e "\n${YELLOW}Do you want to push $TARGET_BRANCH to remote? (y/n)${NC}"
        read -r response
        if [[ "$response" =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}Pushing $TARGET_BRANCH to origin...${NC}"
            git push origin "$TARGET_BRANCH"
            echo -e "${GREEN}Pushed successfully!${NC}"
        fi
    fi
fi

# Return to original branch
echo -e "\n${BLUE}Returning to original branch: $ORIGINAL_BRANCH${NC}"
git checkout "$ORIGINAL_BRANCH"

# Restore stashed changes if any
if [ "$STASHED" = true ]; then
    echo -e "${BLUE}Restoring stashed changes...${NC}"
    git stash pop
    echo -e "${GREEN}Stashed changes restored${NC}"
fi

echo -e "\n${GREEN}Done!${NC}"

