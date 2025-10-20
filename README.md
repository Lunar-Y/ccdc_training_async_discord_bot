# Team Management Bot

A Discord bot for managing team-based events. It's specifically used for Cyber@UCI to manage asynchronous training drills.

## Features

- **Team Creation & Management**: Users can create teams or join existing ones
- **Team Captains**: Team creators become captains with authority to approve join requests
- **Automated Timers**: Each team has a configurable time limit with automatic end notifications
- **Join Requests**: Prospective members send requests that captains must approve
- **Admin Controls**: Full administrative suite for managing settings and teams
- **VM Integration**: Automated subprocess calls to manage virtual machines via SPAM
- **DM Notifications**: Real-time updates sent to team members via direct messages

## Installation

### Prerequisites

- Python 3.8+
- `discord.py` library with slash command support
- A Discord bot token
- Access to a Discord server where you can manage the bot

### Setup

1. **Install dependencies**:
   ```bash
   pip install discord.py
   ```

2. **Configure the bot**:
   - Replace the bot token at the bottom of the script with your own:
   ```python
   bot.run("YOUR_BOT_TOKEN_HERE")
   ```

3. **Run the bot**:
   ```bash
   python bot_script.py
   ```

## Commands

### User Commands

- `/create_team` - Create a new team (you become captain)
- `/join_team` - View and request to join available teams
- `/leave_team` - Leave your current team (allows you to then join another team)
- `/end_team` - End your team (captain only)

### Admin Commands

- `/admin_add <user>` - Make a user an admin
- `/admin_remove <user>` - Remove admin privileges from a user
- `/admin_settings` - Configure team settings:
  - `max_size`: Maximum players per team
  - `max_teams`: Maximum number of teams
  - `duration`: Team duration in minutes
  - `ip_base`: IP range template (e.g., `10.10.x.10`)
  - `start_vmid`: Starting VMID for VM management
  - `number_of_machines`: Number of machines per team network
- `/view_settings` - Display current team settings
- `/reset` - End all teams and clear the system
- `/reopen_team <team_num>` - Reopen a previously closed team

## Configuration

### Team Settings

Administrators can customize the following via `/admin_settings`:

| Setting | Purpose |
|---------|---------|
| Max Team Size | Limits players per team |
| Max Teams | Controls total number of active teams |
| Duration | Sets time limit for each team in minutes |
| IP Base | Template for team IP ranges (uses `x` as placeholder) |
| Start VMID | Initial VM ID for first team |
| Number of Machines | VMs allocated per team |

## Workflow

1. **Setup**: Admin configures settings using `/admin_settings`
2. **Team Creation**: Users create teams with `/create_team` or join with `/join_team`
3. **Join Requests**: Prospective members send requests; captain approves/denies
4. **Timer Starts**: Once a member creates a team, their team's countdown begins
5. **Notifications**: 
   - Halfway point alert sent at 50% time remaining
   - Automatic end notification when time expires
6. **VM Cleanup**: When a team ends, SPAM subprocess handles VM state changes

## VM Integration

The bot automatically manages virtual machines by executing `status.py` in a `SPAM` subdirectory with these arguments:

- `--revert`: Revert VM state for the team
- `-s`: Shutdown/shutdown-related command
- `-r`: Range specifier (start and end VMID)

Ensure `status.py` exists and is properly configured for your infrastructure.

## Notes

- Teams automatically end when time expires or all members leave
- If a captain leaves, the next member becomes captain

## Support

Ensure your `status.py` script can handle the VMID ranges passed during team operations. Check console logs for any subprocess failures or permission issues.
