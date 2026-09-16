"""JobAgent Discord bot: multi-user. DM it your resume once, connect your Gmail once,
then DM it a job posting (text or link) any time and it auto-drafts + saves to Gmail.

Each Discord user gets their own isolated row in the shared backend DB (backend/db.py),
keyed "discord:<user_id>" - their resume, Gmail token, and history never mix with anyone
else's. Gmail auth uses the same web OAuth flow as the public web app (backend/gmail_oauth.py),
so each user authorizes their own Google account via a link they open in their own browser -
this bot process never sees anyone's Google password, and the callback is handled by the
publicly deployed backend (see backend/routers/gmail.py), not this process.
"""
from __future__ import annotations

import asyncio
import logging

import discord

from backend import db, gmail_oauth
from backend.job_fetcher import fetch_job_text, looks_like_url
from backend.pdf_extract import extract_text
from src.config import DISCORD_ALLOWED_USER_ID, MAX_UPLOAD_BYTES, RESUMES_DIR, require_discord_token
from src.drafter import EmailDraft, draft_email
from src.matcher import MatchResult, evaluate_match
from src.parser import ParsedJob, parse_job_description

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jobagent.discord")

intents = discord.Intents.default()
intents.message_content = True
intents.dm_messages = True

client = discord.Client(intents=intents)

_GMAIL_COMMANDS = {"connect", "connect gmail", "gmail", "authorize", "auth"}


def _uid(author: discord.abc.User) -> str:
    return f"discord:{author.id}"


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
        embed.set_footer(text=f"Already processed on {duplicate.get('created_at')} (status: {duplicate.get('draft_status')})")
    return embed


async def _handle_resume_upload(message: discord.Message, uid: str) -> None:
    attachment = message.attachments[0]
    if attachment.size > MAX_UPLOAD_BYTES:
        await message.channel.send("That file is too large (max 5 MB).")
        return

    content = await attachment.read()
    try:
        profile_text = await asyncio.to_thread(extract_text, attachment.filename, content)
    except ValueError as e:
        await message.channel.send(str(e))
        return

    if len(profile_text) < 50:
        await message.channel.send("Extracted resume text looks too short - try a different file.")
        return

    RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    ext = attachment.filename.rsplit(".", 1)[-1].lower() if "." in attachment.filename else "txt"
    resume_path = RESUMES_DIR / f"{uid.replace(':', '_')}.{ext}"
    resume_path.write_bytes(content)

    await asyncio.to_thread(
        db.update_session, uid, profile_text=profile_text, resume_file_path=str(resume_path)
    )

    session = await asyncio.to_thread(db.get_session, uid)
    if session and session.get("gmail_token"):
        await message.channel.send("Resume saved. You're all set - send me a job posting (text or a link) any time.")
    else:
        auth_url = gmail_oauth.get_authorization_url(state=uid)
        await message.channel.send(
            f"Resume saved. Now connect your Gmail so I can save drafts there: {auth_url}\n"
            "(Opens Google's consent screen - approve it, then come back and send me a job.)"
        )


async def _handle_gmail_connect(message: discord.Message, uid: str) -> None:
    auth_url = gmail_oauth.get_authorization_url(state=uid)
    await message.channel.send(f"Connect your Gmail here: {auth_url}")


async def _process_draft(channel: discord.abc.Messageable, uid: str, job: ParsedJob, match: MatchResult, profile_text: str) -> None:
    await channel.send("Drafting email...")
    try:
        email: EmailDraft = await asyncio.to_thread(draft_email, job, match, profile_text)
    except Exception as e:
        await channel.send(f"Failed to draft email: {e}")
        return

    session = await asyncio.to_thread(db.get_session, uid)
    token_data = session.get("gmail_token") if session else None
    resume_path = session.get("resume_file_path") if session else None

    if not token_data:
        await channel.send("Gmail isn't connected. Send 'connect' to get a link.")
        return

    try:
        token_data, changed = await asyncio.to_thread(gmail_oauth.refresh_if_needed, token_data)
        if changed:
            await asyncio.to_thread(db.update_session, uid, gmail_token=token_data)
    except RuntimeError as e:
        await channel.send(str(e))
        return

    try:
        draft_id = await asyncio.to_thread(gmail_oauth.create_draft, token_data, email, resume_path)
        status = "draft_created"
    except RuntimeError as e:
        draft_id = None
        status = "draft_failed"
        await channel.send(f"Drafted the email but failed to save it to Gmail: {e}")

    await asyncio.to_thread(
        db.add_history_entry,
        session_id=uid,
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
        await channel.send(embed=embed)


class MismatchView(discord.ui.View):
    def __init__(self, uid: str, job: ParsedJob, match: MatchResult, profile_text: str):
        super().__init__(timeout=600)
        self.uid = uid
        self.job = job
        self.match = match
        self.profile_text = profile_text

    @discord.ui.button(label="Generate anyway", style=discord.ButtonStyle.primary)
    async def generate_anyway(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await _process_draft(interaction.channel, self.uid, self.job, self.match, self.profile_text)
        self.stop()

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        await asyncio.to_thread(
            db.add_history_entry,
            session_id=self.uid,
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

    uid = _uid(message.author)
    await asyncio.to_thread(db.ensure_session, uid)

    if message.attachments:
        await _handle_resume_upload(message, uid)
        return

    content = message.content.strip()
    if not content:
        return

    if content.lower() in _GMAIL_COMMANDS:
        await _handle_gmail_connect(message, uid)
        return

    session = await asyncio.to_thread(db.get_session, uid)
    profile_text = session.get("profile_text") if session else None
    if not profile_text:
        await message.channel.send(
            "Send me your resume first - upload a PDF, or paste the text directly."
        )
        return

    async with message.channel.typing():
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
            match: MatchResult = await asyncio.to_thread(evaluate_match, job, profile_text)
        except Exception as e:
            await message.channel.send(f"Failed to analyze job: {e}")
            return

    duplicate = await asyncio.to_thread(db.find_history_entry, uid, job.company_name, job.job_title)
    embed = _match_embed(job, match, duplicate)

    if not session.get("gmail_token"):
        auth_url = gmail_oauth.get_authorization_url(state=uid)
        await message.channel.send(embed=embed)
        await message.channel.send(f"Connect your Gmail to save this as a draft: {auth_url}")
        return

    if match.is_aligned:
        await message.channel.send(embed=embed)
        await _process_draft(message.channel, uid, job, match, profile_text)
    else:
        await message.channel.send(
            content="Role mismatch detected. Generate an application anyway?",
            embed=embed,
            view=MismatchView(uid, job, match, profile_text),
        )


def main() -> None:
    client.run(require_discord_token())


if __name__ == "__main__":
    main()
