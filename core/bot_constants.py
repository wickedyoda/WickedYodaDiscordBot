import re

SHORT_CODE_REGEX = re.compile(r"Link saved:\s*([0-9]{4,})")
STATUS_PAGE_PATH_REGEX = re.compile(r"^/status/([^/]+)/?$")
YOUTUBE_CHANNEL_ID_PATTERN = re.compile(r"(UC[a-zA-Z0-9_-]{22})")
YOUTUBE_CHANNEL_ID_META_PATTERNS = (
    re.compile(r'"channelId":"(UC[a-zA-Z0-9_-]{22})"'),
    re.compile(r'itemprop="channelId"\s+content="(UC[a-zA-Z0-9_-]{22})"'),
    re.compile(r'"externalId":"(UC[a-zA-Z0-9_-]{22})"'),
)
USER_ID_INPUT_PATTERN = re.compile(r"^\d{17,20}$")
YOUTUBE_POST_ID_PATTERN = re.compile(r'"postId":"([^"]+)"')
YOUTUBE_TEXT_PATTERN = re.compile(r'"text":"([^"]+)"')
LINKEDIN_ACTIVITY_URN_PATTERN = re.compile(r"urn:li:activity:(\d{8,})")
LINKEDIN_POST_URL_PATTERN = re.compile(r"https://www\.linkedin\.com/(?:feed/update/urn:li:activity:\d+|posts/[^\"'<>\s]+)")
LINKEDIN_TEXT_PATTERN = re.compile(r'"text":"([^"]+)"')
LINKEDIN_OG_TITLE_PATTERN = re.compile(r'<meta\s+property="og:title"\s+content="([^"]+)"', re.IGNORECASE)

SPICY_PROMPT_ALLOWED_TYPES = {"prompt", "truth", "dare", "would_you_rather", "icebreaker", "quiz"}
SPICY_PROMPT_BLOCKED_TAGS = {
    "minor",
    "minors",
    "underage",
    "teen",
    "incest",
    "coercion",
    "non-consensual",
    "nonconsensual",
    "sexual-violence",
    "assault",
    "bestiality",
    "trafficking",
    "exploitation",
}
SPICY_PROMPT_BLOCKED_CATEGORIES = {
    "minor",
    "minors",
    "underage",
    "incest",
    "coercion",
    "non-consensual",
    "nonconsensual",
    "sexual-violence",
    "assault",
    "bestiality",
    "trafficking",
    "exploitation",
}

COMMAND_PERMISSION_MODE_DEFAULT = "default"
COMMAND_PERMISSION_MODE_PUBLIC = "public"
COMMAND_PERMISSION_MODE_CUSTOM_ROLES = "custom_roles"
COMMAND_PERMISSION_MODE_DISABLED = "disabled"
COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC = "public"
COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR = "moderator"
COMMAND_PERMISSION_POLICY_LABELS = {
    COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC: "Public (all members)",
    COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR: "Moderator (ban/kick/manage roles/messages/moderate)",
}
COMMAND_PERMISSION_METADATA: dict[str, dict[str, str]] = {
    "ping": {"label": "/ping", "description": "Health check", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "sayhi": {"label": "/sayhi", "description": "Bot introduction", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "happy": {"label": "/happy", "description": "Random puppy image", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "cat": {"label": "/cat", "description": "Random cat image", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "meme": {"label": "/meme", "description": "Random meme", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "dadjoke": {"label": "/dadjoke", "description": "Random dad joke", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "eightball": {"label": "/eightball", "description": "Magic eight-ball", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "coinflip": {"label": "/coinflip", "description": "Flip a coin", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "roll": {"label": "/roll", "description": "Roll dice", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "choose": {"label": "/choose", "description": "Pick an option", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "roastme": {"label": "/roastme", "description": "Playful roast", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "compliment": {
        "label": "/compliment",
        "description": "Friendly compliment",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "wisdom": {"label": "/wisdom", "description": "Yoda-style wisdom", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "gif": {"label": "/gif", "description": "Reaction GIF", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "poll": {"label": "/poll", "description": "Quick poll", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "questionoftheday": {
        "label": "/questionoftheday",
        "description": "Conversation starter",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "spicy": {"label": "/spicy", "description": "Random spicy prompt", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "ollama": {"label": "/ollama", "description": "Ask the Ollama model", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "randomuser": {
        "label": "/randomuser",
        "description": "Pick a random user (30-day cooldown)",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "translate": {"label": "/translate", "description": "Translate text", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "wikihelp": {
        "label": "/wikihelp",
        "description": "Search the game help wiki",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "color": {"label": "/color", "description": "Pick a name color role", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "countdown": {"label": "/countdown", "description": "Countdown to a date", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "leaderboard": {
        "label": "/leaderboard",
        "description": "Activity leaderboard",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "trivia": {"label": "/trivia", "description": "Trivia question", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "wouldyourather": {
        "label": "/wouldyourather",
        "description": "Would you rather prompt",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "rps": {"label": "/rps", "description": "Rock paper scissors", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "guess": {"label": "/guess", "description": "Guessing game", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "birthday_set": {"label": "/birthday set", "description": "Set a birthday", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "birthday_view": {
        "label": "/birthday view",
        "description": "View a birthday",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "birthday_upcoming": {
        "label": "/birthday upcoming",
        "description": "List upcoming birthdays",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "birthday_remove": {
        "label": "/birthday remove",
        "description": "Remove a birthday",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "shorten": {"label": "/shorten", "description": "Create short URL", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "expand": {"label": "/expand", "description": "Expand short URL", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "uptime": {"label": "/uptime", "description": "Uptime monitor summary", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "monitor": {"label": "/monitor", "description": "Service monitor status", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "logs": {"label": "/logs", "description": "Read recent error logs", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "stats": {
        "label": "/stats",
        "description": "Your private activity summary",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC,
    },
    "help": {"label": "/help", "description": "Command overview", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "tags": {"label": "/tags", "description": "List configured tags", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "tag": {"label": "/tag", "description": "Post a configured tag", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_PUBLIC},
    "kick": {"label": "/kick", "description": "Kick member", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "ban": {"label": "/ban", "description": "Ban member", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "timeout": {"label": "/timeout", "description": "Timeout member", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "untimeout": {"label": "/untimeout", "description": "Remove timeout", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "purge": {"label": "/purge", "description": "Purge messages", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "unban": {"label": "/unban", "description": "Unban by user ID", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "addrole": {"label": "/addrole", "description": "Add role to member", "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR},
    "removerole": {
        "label": "/removerole",
        "description": "Remove role from member",
        "default_policy": COMMAND_PERMISSION_DEFAULT_POLICY_MODERATOR,
    },
}

DEFAULT_TAG_RESPONSES = {
    "!rules": "Please review the server rules and pinned messages before posting.",
    "!support": "Need help? Open a support thread with details and device/version info.",
}
