"""JobAgent Discord bot: DM it a job posting (text or link) and it auto-drafts + saves to Gmail.

Personal-use automation - only processes DMs from DISCORD_ALLOWED_USER_ID. Reuses the same
parser/matcher/drafter/gmail_client pipeline as the CLI (main.py), just triggered by a Discord
message instead of typing into a terminal.
"""
from __future__ import annotations

import asyncio
import logging

import discord

from backend.job_fetcher import fetch_job_text, looks_like_url
from src import storage
from src.config import DISCORD_ALLOWED_USER_ID, PROFILE_PATH, require_discord_token
from src.drafter import EmailDraft, draft_email
from src.gmail_client import create_draft
from src.matcher import MatchResult, evaluate_match
from src.parser import ParsedJob, parse_job_description

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jobagent.discord")

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

client = discord.Client(intents=intents)


def _read_profile() -> str:
    if not PROFILE_PATH.exists():
        raise RuntimeError(f"Profile not found at {PROFILE_PATH}")
    return PROFILE_PATH.read_text(encoding="utf-8")


def _is_authorized(author: discord.abc.User) -> bool:
    if not DISCORD_ALLOWED_USER_ID:
        return True
    return str(author.id) == DISCORD_ALLOWED_USER_ID


def _match_embed(job: ParsedJob, match: MatchResult, duplicate: dict | None) -> discord.Embed:
    color = discord.Color.green() if match.is_aligned else discord.Color.orange()
    embed = discord.Embed(
        title=f"{job.job_title} @ {job.company_name}",
        description=match.verdict_summary,
        color=color,
    )
    embed.add_field(name="Match score", value=f"{match.match_score}% ({'Aligned' if match.is_aligned else 'Mismatch'})", inline=False)
    embed.add_field(name="Recruiter", value=f"{job.recruiter_name or 'N/A'} <{job.recruiter_email or 'N/A'}>", inline=False)
    embed.add_field(name="Tech stack", value=", ".join(job.tech_stack) or "N/A", inline=False)
    if match.matching_strengths:
        embed.add_field(name="Strengths", value="\n".join(f"- {s}" for s in match.matching_strengths), inline=False)
    if match.missing_or_gap_skills:
        embed.add_field(name="Gaps", value="\n".join(f"- {s}" for s in match.missing_or_gap_skills), inline=False)
    if duplicate:
        embed.set_footer(text=f"Already processed on {duplicate.get('timestamp')} (status: {duplicate.get('draft_status')})")
    return embed


async def _process_draft(channel: discord.abc.Messageable, job: ParsedJob, match: MatchResult, profile_markdown: str) -> None:
    await channel.send("Drafting email...")
    try:
        email: EmailDraft = await asyncio.to_thread(draft_email, job, match, profile_markdown)
    except Exception as e:
        await channel.send(f"Failed to draft email: {e}")
        return

    try:
        draft_id = await asyncio.to_thread(create_draft, email)
        status = "draft_created"
    except Exception as e:
        draft_id = None
        status = "draft_failed"
        await channel.send(f"Drafted the email but failed to save it to Gmail: {e}")

    await asyncio.to_thread(
        storage.append_entry,
        company=job.company_name,
        title=job.job_title,
        match_score=match.match_score,
        is_aligned=match.is_aligned,
        draft_status=status,
        draft_id=draft_id,
    )

    if status == "draft_created":
        embed = discord.Embed(title="Saved to Gmail drafts", color=discord.Color.green())
        embed.add_field(name="To", value=email.recipient_email, inline=False)
        embed.add_field(name="Subject", value=email.subject_line, inline=False)
        embed.add_field(name="Draft ID", value=draft_id, inline=False)
        await channel.send(embed=embed)


class MismatchView(discord.ui.View):
    def __init__(self, job: ParsedJob, match: MatchResult, profile_markdown: str):
        super().__init__(timeout=600)
        self.job = job
        self.match = match
        self.profile_markdown = profile_markdown

    @discord.ui.button(label="Generate anyway", style=discord.ButtonStyle.primary)
    async def generate_anyway(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await _process_draft(interaction.channel, self.job, self.match, self.profile_markdown)
        self.stop()

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await asyncio.to_thread(
            storage.append_entry,
            company=self.job.company_name,
            title=self.job.job_title,
            match_score=self.match.match_score,
            is_aligned=self.match.is_aligned,
            draft_status="skipped_mismatch",
        )
        await interaction.channel.send("Skipped - logged as not applied.")
        self.stop()


@client.event
async def on_ready():
    log.info("Logged in as %s (id=%s)", client.user, client.user.id if client.user else "?")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if not isinstance(message.channel, discord.DMChannel):
        return
    if not _is_authorized(message.author):
        return

    content = message.content.strip()
    if not content:
        return

    async with message.channel.typing():
        try:
            profile_markdown = await asyncio.to_thread(_read_profile)
        except RuntimeError as e:
            await message.channel.send(str(e))
            return

        try:
            if looks_like_url(content):
                job_text = await asyncio.to_thread(fetch_job_text, content)
            else:
                job_text = content
        except ValueError as e:
            await message.channel.send(str(e))
            return

        try:
            job: ParsedJob = await asyncio.to_thread(parse_job_description, job_text)
            match: MatchResult = await asyncio.to_thread(evaluate_match, job, profile_markdown)
        except Exception as e:
            await message.channel.send(f"Failed to analyze job: {e}")
            return

    duplicate = await asyncio.to_thread(storage.find_existing, job.company_name, job.job_title)
    embed = _match_embed(job, match, duplicate)

    if match.is_aligned:
        await message.channel.send(embed=embed)
        await _process_draft(message.channel, job, match, profile_markdown)
    else:
        await message.channel.send(
            content="Role mismatch detected. Generate an application anyway?",
            embed=embed,
            view=MismatchView(job, match, profile_markdown),
        )


def main() -> None:
    client.run(require_discord_token())


if __name__ == "__main__":
    main()
