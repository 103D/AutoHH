# Hermes Agent Integration

This document describes how Hermes Agent is configured to work with the AutoHH project.

## Project Setup

Hermes is configured to work with AutoHH as a project:

```bash
# Create project (already done)
hermes project create AutoHH /home/user/Projects/AtoHH --slug autohh --use

# Set working directory
hermes config set terminal.cwd /home/user/Projects/AtoHH
```

## Available Tools

### File Operations
- Read, write, and edit source code files
- Navigate project structure
- Search code patterns

### Terminal Access
- Execute shell commands
- Run npm/poetry/docker commands
- Execute project scripts

### Docker Integration
- Check container status: `docker ps`
- View logs: `docker compose logs`
- Restart services: `docker compose restart`

### Development Tools
- **Ruff**: Linting and formatting (Python)
- **Pytest**: Test execution
- **Poetry**: Dependency management
- **npm**: Frontend package management

### Project Scripts
- `scripts/backup_db.sh` - Database backup
- `scripts/tunnelmole-webhook.sh` - Telegram webhook setup
- `backend/scripts/init_job_sources.py` - Initialize job sources
- `backend/scripts/init_candidate.py` - Initialize candidate profile

## Quick Commands

### Check Project Status
```bash
hermes --in /home/user/Projects/AtoHH -z "Run: docker ps" --cli
```

### Run Linting
```bash
hermes --in /home/user/Projects/AtoHH/backend -z "Run: ruff check app/" --cli
```

### View Logs
```bash
hermes --in /home/user/Projects/AtoHH -z "Run: docker compose logs --tail=50" --cli
```

### Read Source Code
```bash
hermes --in /home/user/Projects/AtoHH -z "Read backend/app/main.py" --cli
```

## Security

- Secrets in `.env` files are automatically redacted
- Hermes cannot access SSH keys or credentials
- Database passwords are not exposed
- API tokens are masked in output

## Workflow Examples

### 1. Code Review
```bash
hermes --in /home/user/Projects/AtoHH -z "Review recent changes in backend/" --cli
```

### 2. Debug Issue
```bash
hermes --in /home/user/Projects/AtoHH -z "Check backend logs for errors" --cli
```

### 3. Run Tests
```bash
hermes --in /home/user/Projects/AtoHH/backend -z "Run: poetry run pytest tests/unit/test_scoring.py -v" --cli
```

### 4. Update Dependencies
```bash
hermes --in /home/user/Projects/AtoHH/backend -z "Run: poetry update" --cli
```

## Configuration Files

- `.hermes/project.yaml` - Project configuration (tools, scripts, services)
- `.gitignore` - Updated to exclude Hermes cache/sessions
- `hermes config` - Global Hermes configuration

## Troubleshooting

### Timeout Issues
If commands timeout, increase the timeout:
```bash
hermes config set terminal.timeout 120
```

### Permission Issues
Ensure scripts are executable:
```bash
chmod +x scripts/*.sh
```

### Docker Access
Verify Docker is running:
```bash
docker ps
```

## See Also

- Main README: `README.md`
- Hermes docs: `hermes --help`
- Project config: `.hermes/project.yaml`
