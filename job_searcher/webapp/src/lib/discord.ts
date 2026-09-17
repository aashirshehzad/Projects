type DiscordEvent =
  | "user_registered"
  | "cv_uploaded"
  | "application_submitted"
  | "api_error";

export async function sendDiscordAlert(
  event: DiscordEvent,
  fields: Record<string, string>
) {
  const webhookUrl = process.env.DISCORD_WEBHOOK_URL;
  if (!webhookUrl) return;

  const description = Object.entries(fields)
    .map(([key, value]) => `**${key}**: ${value}`)
    .join("\n");

  try {
    await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        embeds: [
          {
            title: event,
            description,
            color: 0x064033,
            timestamp: new Date().toISOString(),
          },
        ],
      }),
    });
  } catch {
    // Discord alerts are best-effort; never block the request on failure.
  }
}
