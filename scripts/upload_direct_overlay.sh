#!/bin/bash
set -e
echo Chunk 1...
scp -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa -P 14149 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500053.mp4 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500054.mp4 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500055.mp4 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500060.mp4 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500062.mp4 root@103.196.86.195:/root/nba_videos/
echo Chunk 2...
scp -o StrictHostKeyChecking=no -i ~/.ssh/id_rsa -P 14149 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500063.mp4 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500064.mp4 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500065.mp4 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500066.mp4 /c/Users/neelj/nba-ai-system/data/videos/full_games/0022500067.mp4 root@103.196.86.195:/root/nba_videos/
echo done