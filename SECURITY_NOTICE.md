# ⚠️ SECURITY NOTICE: API Keys in Git History

## Immediate Action Required

**API keys were found in git history and have been removed from the current codebase.**

### What Was Found

1. **Hardcoded API keys in code:**
   - `backend/app/services/developer/sandbox_runner.py` - Had hardcoded OpenAI and Mistral API keys
   - **FIXED:** Removed hardcoded keys, now uses environment variables only

2. **`.env` files tracked in git:**
   - `.env` and `backend/.env` were committed to git with API keys
   - **FIXED:** Removed from git tracking (files still exist locally but are now gitignored)

3. **API keys in git history:**
   - The following API keys were found in git commit history:
     - OpenAI API key (starts with `sk-svcacct-...`)
     - Google/Gemini API key (starts with `AIza...`)
     - Mistral API key
     - Anthropic API key (starts with `sk-ant-api03-...`)

### Actions Taken

✅ Removed hardcoded API keys from `sandbox_runner.py`  
✅ Removed `.env` files from git tracking  
✅ Updated `.gitignore` to ensure `.env` files are ignored  
✅ All API keys now use environment variables only  

### ⚠️ CRITICAL: Rotate All Exposed API Keys

**You MUST rotate/regenerate ALL API keys that were in git history:**

1. **OpenAI API Key** - Generate new key at https://platform.openai.com/api-keys
2. **Google/Gemini API Key** - Generate new key at https://aistudio.google.com/app/apikey
3. **Mistral API Key** - Generate new key at https://console.mistral.ai/
4. **Anthropic API Key** - Generate new key at https://console.anthropic.com/

### Removing Keys from Git History (Optional but Recommended)

The keys are still visible in git history. To completely remove them, you would need to:

1. Use `git filter-branch` or `git filter-repo` to rewrite history
2. Force push to remote (⚠️ This rewrites history and affects all collaborators)

**Warning:** Rewriting git history is destructive. Only do this if:
- You understand the implications
- All collaborators are aware
- You have backups
- The repository is not widely shared

### Current Security Status

✅ No API keys in current codebase  
✅ `.env` files are gitignored  
✅ All code uses environment variables  
⚠️ API keys still visible in git history (requires rotation)  

### Best Practices Going Forward

1. **Never commit API keys** - Always use environment variables
2. **Use `.env` files** - Keep them in `.gitignore` (already configured)
3. **Use secret management** - Consider using services like AWS Secrets Manager, HashiCorp Vault, or GitHub Secrets for production
4. **Regular audits** - Periodically check git history for accidentally committed secrets
5. **Use pre-commit hooks** - Consider tools like `git-secrets` or `truffleHog` to prevent committing secrets

### Verification

To verify no API keys are currently in the codebase:

```bash
# Search for common API key patterns
grep -r "sk-[a-zA-Z0-9]\{32,\}" --exclude-dir=node_modules --exclude-dir=venv .
grep -r "AIza[0-9A-Za-z_-]\{35\}" --exclude-dir=node_modules --exclude-dir=venv .
grep -r "xai-[a-zA-Z0-9-]\{32,\}" --exclude-dir=node_modules --exclude-dir=venv .
```

