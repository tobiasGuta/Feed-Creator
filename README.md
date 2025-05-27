📰 Feedgen - Custom Feed Monitor with Discord Alerts
----------------------------------------------------

**Feedgen** is a Flask-based web app that lets you **generate custom RSS-like feeds from any website using CSS selectors** then sends you updates directly via **Discord** when new posts drop. Think of it as your personal web content sentinel.

### 🔥 Features

-   🧠 **Smart Selector Detection** -- Auto-detects blog/article containers when CSS is a mess.

-   🛠️ **Fully Customizable** -- Define your own CSS selectors for title, description, URL, date, and images.

-   🔔 **Instant Discord Notifications** -- Get pinged on new content with rich message previews.

-   🧩 **Preview Before You Save** -- Test and visualize what's getting picked up before activating.

-   💾 **SQLite-powered Config Persistence** -- Stores multiple feed configurations with update tracking.

-   🌐 **Minimal UI** -- Clean web interface to manage and test feeds.

-   🕵️ **Duplicate Filtering** -- Only notifies you when something actually changes.

### 🧠 Use Cases

-   Monitor tech blogs, changelogs, or hacker news clones that don't offer proper RSS.

-   Create a stealth recon tool for tracking content updates on target assets.

-   Run your own lightweight content aggregator with Discord webhook alerts.

### 🚀 How It Works

1.  Paste a website URL into the dashboard.

2.  Define CSS selectors manually or let Feedgen try to auto-detect them.

3.  Save the config and optionally hook up a Discord webhook.

4.  Feedgen checks the site every 5 minutes and pings you when something new shows up.

* * * * *

### 💻 Built With

-   **Flask** -- Backend & routing

-   **BeautifulSoup** -- HTML parsing

-   **SQLite** -- Local DB for config storage

-   **Discord Webhooks** -- Notification system

* * * * *

### ⚠️ Heads Up

-   This tool isn't scraping-proof it's meant for public, scrape-friendly blogs and changelogs.

-   Some sites might require tweaking due to dynamic content loading (JS-heavy sites aren't ideal).

-   Rate limits? Built-in cooldown helps avoid spamming Discord webhooks.

* * * * *

### 📸 Sneak Peek
