import os
import re
import asyncio
from bs4 import BeautifulSoup
import discord
from discord import Embed
from discord.ext import commands
from dotenv import load_dotenv
from playwright.async_api import async_playwright

def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s

async def fetch_market_html(url: str) -> str:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector("table.market-trends tbody tr", timeout=10000)
        html = await page.content()
        await browser.close()
        return html

async def fetch_player_html(url: str) -> str:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_selector('text="Best Buy"', timeout=10000)
        html = await page.content()
        await browser.close()
        return html

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"We are ready to go, {bot.user.name}")

@bot.command(
    name="liveprices",
    help=(
        "Get Buy/Sell Now prices for Live Series players.\n"
        "• `!liveprices` → top 10 commons\n"
        "• `!liveprices silvers` → top 10 silvers\n"
        "• `!liveprices golds <player>` → that player’s golds\n"
        "• `!liveprices <player>` → that player across all rarities\n"
        "• `!liveprices 25-<overall> <player>` → direct player page (MLB The Show 25)"
    )
)
async def liveprices(ctx, *, query: str = None):
    async with ctx.typing():
        # 1) Direct-link branch if "25-<overall>"
        if query:
            parts = query.split()
            if re.fullmatch(r"25-\d{1,2}", parts[0]):
                overall_tag = parts[0]  # e.g. "25-75"
                if len(parts) < 2:
                    return await ctx.send(
                        "❌ Please provide a player name after the rating."
                    )
                player_name = " ".join(parts[1:])
                slug = slugify(player_name)
                url = (
                    f"https://showzone.gg/players/{overall_tag}-live-{slug}#market"
                )
                try:
                    html = await fetch_player_html(url)
                except Exception as e:
                    return await ctx.send(f"⚠️ Error loading player page: {e}")

                soup = BeautifulSoup(html, "html.parser")
                buy_lbl = soup.find(string="Best Buy")
                sell_lbl = soup.find(string="Best Sell")
                if not buy_lbl or not sell_lbl:
                    return await ctx.send(
                        "❌ Could not find market data on that player’s page."
                    )

                buy = buy_lbl.find_next("h3").get_text(strip=True)
                sell = sell_lbl.find_next("h3").get_text(strip=True)

                embed = Embed(
                    title=f"📊 {player_name.title()} ({overall_tag}) Prices"
                )
                # Flip: show Sell under Buy Now, Buy under Sell Now
                embed.add_field(name="Buy Now", value=sell, inline=True)
                embed.add_field(name="Sell Now", value=buy, inline=True)
                return await ctx.send(embed=embed)

        # 2) Fallback: market-movers branch
        valid = ["commons", "silvers", "golds", "diamonds"]
        rarities = []
        player = None

        if query:
            parts = query.split()
            first = parts[0].lower()
            if first in valid:
                rarities = [first]
                player = " ".join(parts[1:]) if len(parts) > 1 else None
            else:
                player = query
                rarities = valid.copy()
        else:
            rarities = ["commons"]

        embed = Embed(
            title="📊 Live Series Prices"
            + (f" for “{player}”" if player else "")
        )
        count = 0

        for rarity in rarities:
            url = f"https://showzone.gg/market/market-movers/live-series-{rarity}"
            try:
                html = await fetch_market_html(url)
            except:
                continue

            soup = BeautifulSoup(html, "html.parser")
            rows = soup.select("table.market-trends tbody tr")
            if not rows:
                continue

            if player:
                for r in rows:
                    cols = r.find_all("td")
                    name = cols[0].get_text(strip=True)
                    if player.lower() in name.lower():
                        buy = cols[1].get_text(strip=True)
                        sell = cols[2].get_text(strip=True)
                        embed.add_field(
                            name=f"{rarity.title()} – {name}",
                            value=f"Buy Now: {sell}\nSell Now: {buy}",
                            inline=False,
                        )
                        count += 1
                        break
            else:
                for r in rows[:10]:
                    cols = r.find_all("td")
                    name = cols[0].get_text(strip=True)
                    buy = cols[1].get_text(strip=True)
                    sell = cols[2].get_text(strip=True)
                    embed.add_field(
                        name=f"{rarity.title()} – {name}",
                        value=f"Buy Now: {sell}\nSell Now: {buy}",
                        inline=False,
                    )
                    count += 1

        if count == 0:
            await ctx.send(f"❌ No results found for “{player}.”")
        else:
            embed.set_footer(
                text=f"Showing {count} result{'s' if count != 1 else ''}"
            )
            await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(TOKEN)
