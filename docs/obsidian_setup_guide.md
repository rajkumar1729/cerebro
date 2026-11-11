# Obsidian + GitHub Git sync guide

## Desktop setup

- Run these commands inside your local vault folder on your computer to link it to your private GitHub repository:

cd /path/to/your/ObsidianVault

### Initialize repository
git init
git checkout -b main
git remote add origin https://github.com/rajkumar1729/ObsidianVault.git

### Create a .gitignore file
echo ".obsidian/workspace.json" >> .gitignore
echo ".obsidian/workspace-mobile.json" >> .gitignore
echo ".obsidian/plugins/obsidian-local-rest-api/cache/" >> .gitignore
echo ".DS_Store" >> .gitignore

### Commit and push baseline
git add .
git commit -m "Initial desktop commit"
git push -u origin main

## Mobile Setup

cd /path/to/your/ObsidianVault

### Initialize repository
git init
git checkout -b main
git remote add origin https://github.com/rajkumar1729/ObsidianVault.git

### Create a .gitignore file
echo ".obsidian/workspace.json" >> .gitignore
echo ".obsidian/workspace-mobile.json" >> .gitignore
echo ".obsidian/plugins/obsidian-local-rest-api/cache/" >> .gitignore
echo ".DS_Store" >> .gitignore

### Commit and push baseline
git add .
git commit -m "Initial desktop commit"
git push -u origin main

#### automated script to run push and pull with a single click

##### 1. Move to your home directory and create the scripts
cd ~

##### 2. Create the Pull Script
cat << 'EOF' > pull_vault.sh
#!/data/data/com.termux/files/usr/bin/bash
cd ~/storage/shared/Documents/ObsidianVault
echo "📥 Pulling updates from GitHub..."
git pull
echo "Done! Closing in 3 seconds..."
sleep 3
exit 0
EOF

##### 3. Create the Push Script
cat << 'EOF' > push_vault.sh
#!/data/data/com.termux/files/usr/bin/bash
cd ~/storage/shared/Documents/ObsidianVault
echo "🔍 Checking for updates..."
git add .
if git diff-index --quiet HEAD --; then
    echo "✨ No changes detected. Vault is up to date!"
else
    echo "📤 Committing and pushing notes..."
    git commit -m "Android sync: $(date +'%Y-%m-%d %H:%M')"
    git push
fi
echo "Done! Closing in 3 seconds..."
sleep 3
exit 0
EOF

##### 4. Make both scripts executable
chmod +x pull_vault.sh push_vault.sh