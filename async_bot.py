import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from datetime import datetime, timedelta
import json
import os

# Configuration
CONFIG_FILE = "team_config.json"
TEAMS_FILE = "teams_data.json"

# Bot setup
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Load/Save configuration
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"max_team_size": 5, "admin_ids": [], "guild_id": None}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def load_teams():
    if os.path.exists(TEAMS_FILE):
        with open(TEAMS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_teams(teams):
    with open(TEAMS_FILE, 'w') as f:
        json.dump(teams, f, indent=2)

config = load_config()
teams = load_teams()

# Store pending join requests
pending_requests = {}

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    await bot.tree.sync()
    check_team_timers.start()

@tasks.loop(seconds=30)
async def check_team_timers():
    """Check team timers and send notifications"""
    current_teams = load_teams()
    now = datetime.now().isoformat()
    
    for team_name, team_data in current_teams.items():
        if "start_time" not in team_data:
            continue
        
        start_time = datetime.fromisoformat(team_data["start_time"])
        elapsed = datetime.now() - start_time
        
        # 12 hour mark
        if elapsed.total_seconds() >= 43200 and not team_data.get("notified_12h"):
            await notify_team_members(team_data, "12h")
            team_data["notified_12h"] = True
            save_teams(current_teams)
        
        # 24 hour mark
        if elapsed.total_seconds() >= 86400 and not team_data.get("notified_24h"):
            await notify_team_members(team_data, "24h")
            team_data["notified_24h"] = True
            save_teams(current_teams)

async def notify_team_members(team_data, stage):
    """Send DM notifications to team members"""
    guild = bot.get_guild(config["guild_id"])
    
    if stage == "12h":
        message = "⏰ Your team has 12 hours remaining!"
    else:  # 24h
        message = "⏰ Time's up! Your team registration period has ended!"
    
    # Notify team members
    for member_id in team_data.get("members", []):
        try:
            user = await bot.fetch_user(int(member_id))
            await user.send(f"**Team: {team_data['name']}**\n{message}")
        except:
            pass
    
    # Notify admins at 24h mark
    if stage == "24h":
        for admin_id in config["admin_ids"]:
            try:
                user = await bot.fetch_user(int(admin_id))
                await user.send(f"**Team '{team_data['name']}' registration has ended!**\nFinal members: {len(team_data.get('members', []))}")
            except:
                pass

@bot.tree.command(name="setup_bot", description="Setup bot configuration (Admin only)")
@app_commands.describe(
    max_team_size="Maximum number of members per team",
    admin_ids="Comma-separated list of admin user IDs"
)
async def setup_bot(interaction: discord.Interaction, max_team_size: int, admin_ids: str):
    # Check if user is server owner
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Only the server owner can use this command!", ephemeral=True)
        return
    
    config["max_team_size"] = max_team_size
    config["admin_ids"] = [id.strip() for id in admin_ids.split(",")]
    config["guild_id"] = interaction.guild_id
    save_config(config)
    
    await interaction.response.send_message(
        f"✅ Bot configured!\nMax team size: {max_team_size}\nAdmins: {', '.join(config['admin_ids'])}",
        ephemeral=True
    )

@bot.tree.command(name="create_team", description="Create a new team")
@app_commands.describe(team_name="Name for your team")
async def create_team(interaction: discord.Interaction, team_name: str):
    current_teams = load_teams()
    
    if team_name in current_teams:
        await interaction.response.send_message("❌ Team name already exists!", ephemeral=True)
        return
    
    # Check if user is already in a team
    for team in current_teams.values():
        if str(interaction.user.id) in team.get("members", []):
            await interaction.response.send_message("❌ You're already in a team!", ephemeral=True)
            return
    
    current_teams[team_name] = {
        "name": team_name,
        "captain_id": str(interaction.user.id),
        "captain_name": interaction.user.name,
        "members": [str(interaction.user.id)],
        "start_time": datetime.now().isoformat(),
        "notified_12h": False,
        "notified_24h": False
    }
    save_teams(current_teams)
    
    await interaction.response.send_message(
        f"✅ Team **{team_name}** created!\n"
        f"Team captain: {interaction.user.mention}\n"
        f"24-hour countdown started!",
        ephemeral=True
    )

@bot.tree.command(name="join_team", description="Request to join a team")
@app_commands.describe(team_name="Name of the team to join")
async def join_team(interaction: discord.Interaction, team_name: str):
    current_teams = load_teams()
    
    if team_name not in current_teams:
        await interaction.response.send_message("❌ Team not found!", ephemeral=True)
        return
    
    team = current_teams[team_name]
    user_id = str(interaction.user.id)
    
    # Check if already in a team
    for t in current_teams.values():
        if user_id in t.get("members", []):
            await interaction.response.send_message("❌ You're already in a team!", ephemeral=True)
            return
    
    # Check if team is full
    if len(team["members"]) >= config["max_team_size"]:
        await interaction.response.send_message("❌ Team is full!", ephemeral=True)
        return
    
    # Create join request
    request_key = f"{team_name}_{user_id}"
    pending_requests[request_key] = {
        "team": team_name,
        "user_id": user_id,
        "user_name": interaction.user.name
    }
    
    # Notify team captain
    try:
        captain = await bot.fetch_user(int(team["captain_id"]))
        embed = discord.Embed(
            title=f"Team Join Request",
            description=f"{interaction.user.mention} wants to join **{team_name}**",
            color=discord.Color.blue()
        )
        
        view = JoinRequestView(request_key)
        await captain.send(embed=embed, view=view)
    except:
        await interaction.response.send_message("❌ Failed to notify team captain!", ephemeral=True)
        return
    
    await interaction.response.send_message(
        f"✅ Join request sent to {team['captain_name']}!",
        ephemeral=True
    )

@bot.tree.command(name="list_teams", description="List all active teams")
async def list_teams(interaction: discord.Interaction):
    current_teams = load_teams()
    
    if not current_teams:
        await interaction.response.send_message("❌ No teams found!", ephemeral=True)
        return
    
    embed = discord.Embed(title="Active Teams", color=discord.Color.green())
    
    for team_name, team_data in current_teams.items():
        member_count = len(team_data.get("members", []))
        embed.add_field(
            name=team_name,
            value=f"Captain: {team_data['captain_name']}\nMembers: {member_count}/{config['max_team_size']}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

class JoinRequestView(discord.ui.View):
    def __init__(self, request_key):
        super().__init__()
        self.request_key = request_key
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        current_teams = load_teams()
        request = pending_requests.get(self.request_key)
        
        if not request:
            await interaction.response.send_message("❌ Request not found!", ephemeral=True)
            return
        
        team = current_teams[request["team"]]
        user_id = request["user_id"]
        
        if len(team["members"]) >= config["max_team_size"]:
            await interaction.response.send_message("❌ Team is full!", ephemeral=True)
            return
        
        team["members"].append(user_id)
        save_teams(current_teams)
        del pending_requests[self.request_key]
        
        # Notify the user
        try:
            user = await bot.fetch_user(int(user_id))
            await user.send(f"✅ You've been accepted to team **{request['team']}**!")
        except:
            pass
        
        await interaction.response.send_message(f"✅ {request['user_name']} added to team!", ephemeral=True)
    
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        request = pending_requests.get(self.request_key)
        
        if not request:
            await interaction.response.send_message("❌ Request not found!", ephemeral=True)
            return
        
        # Notify the user
        try:
            user = await bot.fetch_user(int(request["user_id"]))
            await user.send(f"❌ Your request to join **{request['team']}** was denied.")
        except:
            pass
        
        del pending_requests[self.request_key]
        await interaction.response.send_message(f"❌ {request['user_name']}'s request denied!", ephemeral=True)

# Run the bot
bot.run("YOUR_BOT_TOKEN_HERE")