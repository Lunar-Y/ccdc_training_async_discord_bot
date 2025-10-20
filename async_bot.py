import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from typing import Optional, Dict, List, Set
from datetime import datetime, timedelta

import sys
import pathlib

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

class TeamSettings:
    def __init__(self):
        self.max_team_size = 0
        self.max_teams = 0
        self.duration_minutes = 0
        self.ip_base = "10.10.x.10"
        self.start_vmid = 0
        self.number_of_machines = 0
    
    def get_ip(self, team_num: int) -> str:
        return self.ip_base.replace("x", str(team_num))

class Team:
    def __init__(self, team_num: int, captain_id: int, settings: TeamSettings):
        self.team_num = team_num
        self.captain_id = captain_id
        self.members: Dict[int, str] = {captain_id: ""}
        self.settings = settings
        self.created_at = datetime.now()
        self.end_time = self.created_at + timedelta(minutes=settings.duration_minutes)
        self.is_active = True
        self.timer_message_ids: Dict[int, tuple] = {}
        self.halfway_notified = False

class TeamManager:
    def __init__(self):
        self.settings = TeamSettings()
        self.teams: Dict[int, Team] = {}
        self.user_teams: Dict[int, int] = {}
        self.available_team_nums: Set[int] = set(range(1, self.settings.max_teams + 1))
        self.admins: Set[int] = set()
        self.admin_guild_id: Optional[int] = None
        self.closed_teams: Set[int] = set()
    
    def update_max_teams(self, new_max: int):
        old_max = self.settings.max_teams
        self.settings.max_teams = new_max


        
        if new_max > old_max:
            for team_num in range(old_max + 1, new_max + 1):
                self.available_team_nums.add(team_num)

manager = TeamManager()

async def send_dm(user_id: int, content: str = None, embed: discord.Embed = None, view: discord.ui.View = None) -> tuple:
    try:
        user = await bot.fetch_user(user_id)
        msg = await user.send(content=content, embed=embed, view=view)
        return True, msg.channel.id, msg.id
    except discord.Forbidden:
        return False, None, None

async def create_timer_embed(team: Team):
    embed = discord.Embed(
        title=f"Team {team.team_num} - Timer",
        description=f"**Ends at:** <t:{int(team.end_time.timestamp())}:R>",
        color=discord.Color.blue()
    )
    embed.add_field(name="Team Members", value=", ".join(team.members.values()), inline=False)
    embed.add_field(name="IP Range", value=team.settings.get_ip(team.team_num), inline=False)
    
    return embed

async def end_team(team_num: int, auto_end: bool = False):
    if team_num not in manager.teams:
        return
    
    team = manager.teams[team_num]
    team.is_active = False
    manager.closed_teams.add(team_num)
    
    reason = "Time limit reached" if auto_end else "Captain ended the team"
    embed = discord.Embed(
        title=f"Team {team.team_num} - Ended",
        description=f"**Reason:** {reason}",
        color=discord.Color.red()
    )
    embed.add_field(name="Team Members", value=", ".join(team.members.values()), inline=False)
    
    for member_id in list(team.members.keys()):
        await send_dm(member_id, embed=embed)
        if member_id in manager.user_teams:
            del manager.user_teams[member_id]
    
    for admin_id in manager.admins:
        await send_dm(admin_id, embed=embed)

    # --- START: Moved Subprocess Logic ---
    try:
        current_dir = pathlib.Path(__file__).parent.resolve()
    except NameError:
        current_dir = pathlib.Path.cwd()
    
    script_path = current_dir / "SPAM" / "status.py"
    start_vmid_reset = manager.settings.start_vmid + (team_num - 1) * (manager.settings.number_of_machines - 1)
    end_vmid_reset = start_vmid_reset + manager.settings.number_of_machines
    
    # Subprocess 1: --revert
    try:

        process = await asyncio.create_subprocess_exec(
            sys.executable, str(script_path),
            "--revert", "-r", 
            str(start_vmid_reset), str(end_vmid_reset),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            print(f"Error (revert) status.py for team {team_num}: {stderr.decode()}")
            # You could notify admins of the script failure here
    except Exception as e:
        print(f"Failed to start subprocess (revert) for team {team_num}: {e}")

    # Subprocess 2: -s
    try:

        process = await asyncio.create_subprocess_exec(
            sys.executable, str(script_path),
            "-s", "-r", 
            str(start_vmid_reset), str(end_vmid_reset),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            print(f"Error (-s) status.py for team {team_num}: {stderr.decode()}")
    except Exception as e:
        print(f"Failed to start subprocess (-s) for team {team_num}: {e}")
    # --- END: Moved Subprocess Logic ---

    manager.closed_teams.remove(team_num)
    del manager.teams[team_num]


@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)
    
    start_timer_updates.start()

@tasks.loop(seconds=10)
async def start_timer_updates():
    for team_num, team in list(manager.teams.items()):
        if not team.is_active:
            continue
        
        time_left = team.end_time - datetime.now()
        
        if time_left.total_seconds() <= 0:
            await end_team(team_num, auto_end=True)
            continue
        
        total_seconds = team.settings.duration_minutes * 60
        if not team.halfway_notified and time_left.total_seconds() <= total_seconds / 2:
            team.halfway_notified = True
            halfway_embed = discord.Embed(
                title=f"Team {team.team_num} - Halfway Point Reached!",
                description="Your team has reached the halfway mark.",
                color=discord.Color.orange()
            )
            for member_id in team.members.keys():
                await send_dm(member_id, embed=halfway_embed)
            
            for admin_id in manager.admins:
                await send_dm(admin_id, embed=halfway_embed)

@bot.tree.command(name="admin_add", description="Administrator command to add new admins (Admin only)")
@app_commands.describe(user="The user to make an admin")
async def admin_add(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in manager.admins and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    manager.admins.add(user.id)
    await interaction.response.send_message(f"Added {user.mention} as an admin.", ephemeral=True)

@bot.tree.command(name="admin_remove", description="Administrator command to remove admins (Admin only)")
@app_commands.describe(user="The user to remove as an admin")
async def admin_remove(interaction: discord.Interaction, user: discord.User):
    if interaction.user.id not in manager.admins and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    if user.id not in manager.admins:
        await interaction.response.send_message(f"{user.mention} is not an admin.", ephemeral=True)
        return
    
    manager.admins.remove(user.id)
    await interaction.response.send_message(f"Removed {user.mention} as an admin.", ephemeral=True)

@bot.tree.command(name="admin_settings", description="Configure team settings (Admin only)")
@app_commands.describe(max_size="Max team size", max_teams="Max number of teams", duration="Duration in minutes", ip_base="IP range base (e.g., 10.10.x.10)", start_vmid="VMID of first machine cloned", number_of_machines="Number of machines per network")
async def admin_settings(interaction: discord.Interaction, max_size: int = None, max_teams: int = None, duration: int = None, ip_base: str = None, start_vmid: int = None, number_of_machines: int = None):
    if interaction.user.id not in manager.admins and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    if max_size:
        manager.settings.max_team_size = max_size
    if max_teams:
        manager.update_max_teams(max_teams)
    if duration:
        manager.settings.duration_minutes = duration
    if ip_base:
        manager.settings.ip_base = ip_base
    if start_vmid:
        manager.settings.start_vmid = start_vmid
    if number_of_machines:
        manager.settings.number_of_machines = number_of_machines
    
    manager.admin_guild_id = interaction.guild_id
    
    await interaction.response.send_message(
        f"Settings updated:\n- Max Team Size: {manager.settings.max_team_size}\n- Max Teams: {manager.settings.max_teams}\n- Duration: {manager.settings.duration_minutes} minutes\n- IP Base: {manager.settings.ip_base}\n- VMID of First Machine: {manager.settings.start_vmid}\n- Number of Machines per Network: {manager.settings.number_of_machines}",
        ephemeral=True
    )

@bot.tree.command(name="view_settings", description="View current team settings (Admin only)")
async def view_settings(interaction: discord.Interaction):
    if interaction.user.id not in manager.admins and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    embed = discord.Embed(title="Current Team Settings", color=discord.Color.green())
    embed.add_field(name="Max Team Size", value=str(manager.settings.max_team_size), inline=False)
    embed.add_field(name="Max Teams", value=str(manager.settings.max_teams), inline=False)
    embed.add_field(name="Duration", value=f"{manager.settings.duration_minutes} minutes", inline=False)
    embed.add_field(name="IP Base", value=manager.settings.ip_base, inline=False)
    embed.add_field(name="Active Teams", value=str(len(manager.teams)), inline=False)
    embed.add_field(name="Available Team Numbers", value=str(len(manager.available_team_nums)), inline=False)
    embed.add_field(name="Closed Teams", value=str(sorted(manager.closed_teams)), inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

class RequestMoreTeamsView(discord.ui.View):
    def __init__(self, user_id: int, username: str):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.username = username
    
    @discord.ui.button(label="Request More Teams", style=discord.ButtonStyle.danger)
    async def request_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Team Creation Request",
            description=f"{self.username} has requested more teams to be created.",
            color=discord.Color.orange()
        )
        embed.add_field(name="User ID", value=str(self.user_id), inline=False)
        embed.add_field(name="Reason", value="All teams are currently full", inline=False)
        
        for admin_id in manager.admins:
            await send_dm(admin_id, embed=embed)
        
        await interaction.response.send_message("Request sent to admins!", ephemeral=True)

@bot.tree.command(name="create_team", description="Create a new team")
async def create_team(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    user_id = interaction.user.id
    
    if user_id in manager.user_teams:
        await interaction.followup.send("You're already in a team! Leave your current team first.", ephemeral=True)
        return
    
    if not manager.available_team_nums:
        view = RequestMoreTeamsView(user_id, interaction.user.name)
        await interaction.followup.send("All teams are currently full! Would you like to request more teams?", view=view, ephemeral=True)
        return
    
    if len(manager.teams) >= manager.settings.max_teams:
        view = RequestMoreTeamsView(user_id, interaction.user.name)
        await interaction.followup.send("All teams are currently full! Would you like to request more teams?", view=view, ephemeral=True)
        return
    
    team_num = min(manager.available_team_nums)
    manager.available_team_nums.remove(team_num)
    
    team = Team(team_num, user_id, manager.settings)
    manager.teams[team_num] = team
    manager.user_teams[user_id] = team_num
    
    team.members[user_id] = interaction.user.name
    
    timer_embed = await create_timer_embed(team)
    dm_sent, channel_id, msg_id = await send_dm(user_id, embed=timer_embed)
    
    if not dm_sent:
        await interaction.followup.send("I couldn't DM you! Please enable DMs from server members and try again.", ephemeral=True)
        del manager.teams[team_num]
        del manager.user_teams[user_id]
        manager.available_team_nums.add(team_num)
        return
    
    if channel_id and msg_id:
        team.timer_message_ids[user_id] = (channel_id, msg_id)
    
    await interaction.followup.send(f"Team {team_num} created! Check your DMs for details.", ephemeral=True)

class JoinRequestView(discord.ui.View):
    def __init__(self, user_id: int, username: str, team_num: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.username = username
        self.team_num = team_num
    
    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != manager.teams[self.team_num].captain_id:
            await interaction.response.send_message("Only the team captain can approve join requests.", ephemeral=True)
            return
        
        team = manager.teams[self.team_num]
        if len(team.members) >= manager.settings.max_team_size:
            await interaction.response.send_message("That team is now full!", ephemeral=True)
            return
        
        team.members[self.user_id] = self.username
        manager.user_teams[self.user_id] = self.team_num
        
        timer_embed = await create_timer_embed(team)
        dm_sent, channel_id, msg_id = await send_dm(self.user_id, embed=timer_embed)
        
        if not dm_sent:
            await interaction.response.send_message("Couldn't send DM to user. They may have DMs disabled.", ephemeral=True)
            del team.members[self.user_id]
            del manager.user_teams[self.user_id]
            return
        
        if channel_id and msg_id:
            team.timer_message_ids[self.user_id] = (channel_id, msg_id)
        
        approved_embed = discord.Embed(
            title=f"Approved to Join Team {self.team_num}!",
            description="The team captain has approved your join request.",
            color=discord.Color.green()
        )
        await send_dm(self.user_id, embed=approved_embed)
        
        await interaction.response.send_message(f"Approved {self.username} to join Team {self.team_num}!", ephemeral=True)
    
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != manager.teams[self.team_num].captain_id:
            await interaction.response.send_message("Only the team captain can deny join requests.", ephemeral=True)
            return
        
        denied_embed = discord.Embed(
            title=f"Join Request Denied for Team {self.team_num}",
            description="The team captain has denied your join request.",
            color=discord.Color.red()
        )
        await send_dm(self.user_id, embed=denied_embed)
        
        await interaction.response.send_message(f"Denied {self.username}'s join request.", ephemeral=True)

class JoinTeamButtonView(discord.ui.View):
    def __init__(self, user_id: int, username: str):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.username = username
    
    async def create_team_buttons(self):
        for team_num, team in sorted(manager.teams.items()):
            if len(team.members) < manager.settings.max_team_size and team.is_active:
                button = discord.ui.Button(
                    label=f"Team {team_num} ({len(team.members)}/{manager.settings.max_team_size})",
                    style=discord.ButtonStyle.primary
                )
                button.callback = lambda i, tn=team_num: self.join_callback(i, tn)
                self.add_item(button)
    
    async def join_callback(self, interaction: discord.Interaction, team_num: int):
        if team_num not in manager.teams:
            await interaction.response.send_message("That team no longer exists.", ephemeral=True)
            return
        
        team = manager.teams[team_num]
        if len(team.members) >= manager.settings.max_team_size:
            await interaction.response.send_message("That team is now full!", ephemeral=True)
            return
        
        request_view = JoinRequestView(self.user_id, self.username, team_num)
        
        request_embed = discord.Embed(
            title=f"Join Request for Team {team_num}",
            description=f"{self.username} has requested to join your team.",
            color=discord.Color.yellow()
        )
        request_embed.add_field(name="Requested User ID", value=str(self.user_id), inline=False)
        
        captain_dm_sent, _, _ = await send_dm(team.captain_id, embed=request_embed, view=request_view)
        
        if not captain_dm_sent:
            await interaction.response.send_message("Couldn't send join request to captain. Captain may have DMs disabled.", ephemeral=True)
            return
        
        await interaction.response.send_message(f"Join request sent to Team {team_num} captain! They will review your request.", ephemeral=True)

@bot.tree.command(name="reset", description="Reset all teams (Admin only)")
async def reset_teams(interaction: discord.Interaction):
    if interaction.user.id not in manager.admins and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    # Notify all team members that their teams are being reset
    for team_num, team in list(manager.teams.items()):
        reset_embed = discord.Embed(
            title=f"Team {team_num} - Reset",
            description="All teams have been reset by an administrator.",
            color=discord.Color.red()
        )
        for member_id in team.members.keys():
            await send_dm(member_id, embed=reset_embed)
            if member_id in manager.user_teams:
                del manager.user_teams[member_id]
    
    # Clear all teams and reopen them
    manager.teams.clear()
    manager.closed_teams.clear()
    manager.available_team_nums = set(range(1, manager.settings.max_teams + 1))
    
    await interaction.followup.send("All teams have been reset and reopened!", ephemeral=True)

@bot.tree.command(name="join_team", description="Join an existing team")
async def join_team(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    user_id = interaction.user.id
    
    if user_id in manager.user_teams:
        await interaction.followup.send("You're already in a team! Leave first using `/leave_team`.", ephemeral=True)
        return
    
    if not manager.teams:
        await interaction.followup.send("No teams available. Try creating one with `/create_team`!", ephemeral=True)
        return
    
    view = JoinTeamButtonView(user_id, interaction.user.name)
    await view.create_team_buttons()
    
    if not view.children:
        await interaction.followup.send("No teams available to join at this moment. Try creating one with `/create_team`!", ephemeral=True)
        return
    
    info_embed = discord.Embed(title="Available Teams", color=discord.Color.blue())
    for team_num, team in sorted(manager.teams.items()):
        if len(team.members) < manager.settings.max_team_size and team.is_active:
            time_left = team.end_time - datetime.now()
            mins, secs = divmod(int(time_left.total_seconds()), 60)
            info_embed.add_field(
                name=f"Team {team_num}",
                value=f"**Members:** {len(team.members)}/{manager.settings.max_team_size}\n**Time Left:** {mins}m {secs}s\n**Members:** {', '.join(list(team.members.values())[:3])}{'...' if len(team.members) > 3 else ''}",
                inline=False
            )
    
    await interaction.followup.send(embed=info_embed, view=view, ephemeral=True)

@bot.tree.command(name="leave_team", description="Leave your current team")
async def leave_team(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    user_id = interaction.user.id
    
    if user_id not in manager.user_teams:
        await interaction.followup.send("You're not in a team!", ephemeral=True)
        return
    
    team_num = manager.user_teams[user_id]
    team = manager.teams[team_num]
    username = interaction.user.name
    
    del team.members[user_id]
    del manager.user_teams[user_id]
    
    leave_embed = discord.Embed(
        title=f"Left Team {team_num}",
        description="You have left the team.",
        color=discord.Color.gold()
    )
    await send_dm(user_id, embed=leave_embed)
    
    if not team.members:
        await end_team(team_num)
    else:
        if user_id == team.captain_id:
            team.captain_id = list(team.members.keys())[0]
            new_captain_embed = discord.Embed(
                title=f"You are now captain of Team {team_num}",
                description="The previous captain has left the team.",
                color=discord.Color.blue()
            )
            await send_dm(team.captain_id, embed=new_captain_embed)
        
        for member_id in team.members.keys():
            member_left_embed = discord.Embed(
                title=f"Member Left Team {team_num}",
                description=f"{username} has left the team.",
                color=discord.Color.gold()
            )
            await send_dm(member_id, embed=member_left_embed)
    
    await interaction.followup.send(f"Left Team {team_num}.", ephemeral=True)

@bot.tree.command(name="end_team", description="End your team as captain")
async def end_team_command(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    user_id = interaction.user.id
    
    if user_id not in manager.user_teams:
        await interaction.followup.send("You're not in a team!", ephemeral=True)
        return
    
    team_num = manager.user_teams[user_id]
    team = manager.teams[team_num]
    
    if user_id != team.captain_id:
        await interaction.followup.send("Only the team captain can end the team!", ephemeral=True)
        return
    
    await end_team(team_num)
    await interaction.followup.send(f"Team {team_num} has been ended.", ephemeral=True)

@bot.tree.command(name="reopen_team", description="Reopen a closed team (Admin only)")
@app_commands.describe(team_num="The team number to reopen")
async def reopen_team(interaction: discord.Interaction, team_num: int):
    if interaction.user.id not in manager.admins and interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)
        return
    
    if team_num not in manager.closed_teams:
        await interaction.response.send_message("That team is not closed or doesn't exist.", ephemeral=True)
        return
    
    manager.closed_teams.remove(team_num)
    manager.available_team_nums.add(team_num)
    await interaction.response.send_message(f"Team {team_num} has been reopened.", ephemeral=True)


# Run the bot
bot.run("MTQyOTUxMDg0ODQwNTMwNzYwNA.Gx4DoP.Vwy2YsoASOANbMhr9T27wj8A-C0JiPwB6PCUlo")