"""
Cog Blindtest — /blindtest lancer / stop / skip
Joue de la musique depuis YouTube en vocal, les joueurs devinent l'artiste et le titre.
Nécessite : yt-dlp, PyNaCl, FFmpeg installé sur le système.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
import unicodedata

import discord
from discord import app_commands
from discord.ext import commands

from utils import db
from utils.embeds import error_embed, success_embed

# FFmpeg embarqué via imageio-ffmpeg (pas besoin d'installation système)
try:
    import imageio_ffmpeg
    FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
    logger_tmp = logging.getLogger("goblin_bot.blindtest")
    logger_tmp.info(f"FFmpeg trouvé via imageio-ffmpeg: {FFMPEG_EXE}")
except ImportError:
    FFMPEG_EXE = "ffmpeg"  # Fallback sur ffmpeg système

logger = logging.getLogger("goblin_bot.blindtest")

# Sessions actives par guild_id → dict d'infos
_active_sessions: dict[int, dict] = {}

# Options yt-dlp
YTDLP_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
}

# Options FFmpeg : commence 30 secondes après le début pour éviter les intros
FFMPEG_OPTS = {
    "before_options": (
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss 30"
    ),
    "options": "-vn",
}

THEME_NAMES = {
    "80s": "🕺 Années 80",
    "90s": "💿 Années 90",
    "2000s": "🎵 Années 2000",
    "2010s": "🔥 Années 2010",
    "2020s": "✨ Années 2020",
    "rap_fr": "🎤 Rap FR",
    "rap_us": "🎙️ Rap US",
    "rock": "🎸 Rock",
    "pop": "🎹 Pop",
    "gaming": "🎮 Gaming OST",
    "anime": "🌸 Anime",
    "mix": "🎲 Mix (tout)",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Normalise le texte pour une comparaison souple (minuscules, sans accents)."""
    text = text.lower().strip()
    # Enlève les accents
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Enlève les articles et ponctuation
    for ch in ["'", "'", "-", "!", "?", ".", ",", "(", ")", "feat.", "ft."]:
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _check_guess(guess: str, answer: str) -> bool:
    """
    Vérifie si `guess` correspond à `answer`.
    Accepte si l'answer est contenue dans le guess OU si 60 %+ des mots matchent.
    """
    guess_n = _normalize(guess)
    answer_n = _normalize(answer)
    if not answer_n:
        return False
    if answer_n in guess_n or guess_n in answer_n:
        return True
    # Comparaison mot-à-mot
    words = [w for w in answer_n.split() if len(w) > 2]
    if not words:
        return answer_n in guess_n
    matched = sum(1 for w in words if w in guess_n)
    return matched >= max(1, len(words) * 0.6)


async def _get_audio_url(artist: str, title: str) -> tuple[str, str] | None:
    """
    Cherche la chanson sur YouTube avec yt-dlp.
    Retourne (url, ffmpeg_headers) ou None.
    Les headers sont nécessaires pour éviter les 403 de YouTube côté FFmpeg.
    """
    try:
        import yt_dlp
    except ImportError:
        return None

    queries = [
        f"ytsearch1:{artist} - {title}",
        f"ytsearch1:{artist} {title} audio",
        f"ytsearch1:{artist} {title} lyrics",
    ]

    def _try_extract(q: str) -> tuple[str, str] | None:
        try:
            with yt_dlp.YoutubeDL(YTDLP_OPTS) as ydl:
                info = ydl.extract_info(q, download=False)
                entry = None
                if info and "entries" in info and info["entries"]:
                    entry = info["entries"][0]
                elif info and "url" in info:
                    entry = info
                if not entry:
                    return None
                url = entry.get("url")
                if not url:
                    return None
                # Formate les headers pour FFmpeg : "Key: Value\r\n..."
                raw_headers = entry.get("http_headers", {})
                headers_str = "".join(
                    f"{k}: {v}\r\n" for k, v in raw_headers.items()
                )
                return url, headers_str
        except Exception:
            pass
        return None

    def _extract() -> tuple[str, str] | None:
        for q in queries:
            result = _try_extract(q)
            if result:
                return result
        logger.warning(f"yt-dlp: aucun format disponible pour '{artist} - {title}'")
        return None

    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _extract), timeout=20.0
        )
    except asyncio.TimeoutError:
        logger.warning(f"yt-dlp timeout pour '{artist} - {title}'")
        return None


# ---------------------------------------------------------------------------
# Logique principale du blindtest
# ---------------------------------------------------------------------------

async def _run_blindtest(
    bot: commands.Bot,
    text_channel: discord.TextChannel,
    voice_client: discord.VoiceClient,
    songs: list[dict],
    nb_rounds: int,
    guild_id: int,
):
    """Coroutine principale qui gère toute la session de blindtest."""
    scores: dict[str, int] = {}  # user_id → points

    try:
        intro_embed = discord.Embed(
            title="🎵 Blindtest lancé !",
            description=(
                f"**{nb_rounds} manches** • Écrivez dans ce salon !\n\n"
                "🎤 Devinez **l'artiste** (+1 pt)\n"
                "🎵 Devinez **le titre** (+1 pt)\n\n"
                "⚠️ Pas besoin d'être exact, une bonne approximation suffit !"
            ),
            color=0x5865F2,
        )
        intro_embed.set_footer(text="La musique commence dans 3 secondes... 🎧")
        await text_channel.send(embed=intro_embed)
        await asyncio.sleep(3)

        for round_num in range(1, nb_rounds + 1):
            # Vérifie si la session a été stoppée
            if guild_id not in _active_sessions:
                break

            song = songs[round_num - 1]

            # Message de chargement
            loading_embed = discord.Embed(
                title=f"🎵 Manche {round_num}/{nb_rounds}",
                description="⏳ Chargement depuis YouTube...",
                color=0x5865F2,
            )
            round_msg = await text_channel.send(embed=loading_embed)

            # Récupère l'URL audio + headers
            result = await _get_audio_url(song["artist"], song["title"])

            if not result:
                skip_embed = discord.Embed(
                    title=f"⚠️ Manche {round_num}/{nb_rounds} — Skip",
                    description=f"Impossible de charger **{song['artist']} - {song['title']}**.\nPassage à la suite !",
                    color=0xED4245,
                )
                await round_msg.edit(embed=skip_embed)
                await asyncio.sleep(3)
                continue

            url, headers_str = result

            # Met à jour avec l'embed de jeu
            play_embed = discord.Embed(
                title=f"🎵 Manche {round_num}/{nb_rounds}",
                description="🎤 Artiste: ❓\n🎵 Titre: ❓",
                color=0x5865F2,
            )
            play_embed.set_footer(text="⏱️ 30 secondes pour répondre !")
            await round_msg.edit(embed=play_embed)

            # Lance l'audio avec les headers pour éviter le 403 YouTube
            try:
                ffmpeg_opts = {
                    "before_options": (
                        f"-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss 30"
                        + (f" -headers '{headers_str}'" if headers_str else "")
                    ),
                    "options": "-vn",
                }
                source = discord.FFmpegPCMAudio(url, executable=FFMPEG_EXE, **ffmpeg_opts)
                voice_client.play(discord.PCMVolumeTransformer(source, volume=0.6))
            except Exception as e:
                logger.error(f"FFmpeg error: {e}")
                await text_channel.send(
                    "⚠️ Erreur audio, passage à la suite...", delete_after=5
                )
                await asyncio.sleep(3)
                continue

            # Collecte des réponses pendant 30 secondes
            artist_found_by: discord.Member | None = None
            title_found_by: discord.Member | None = None
            end_time = time.monotonic() + 30.0

            while time.monotonic() < end_time:
                remaining = end_time - time.monotonic()
                if remaining <= 0:
                    break
                if guild_id not in _active_sessions:
                    break

                try:
                    msg: discord.Message = await asyncio.wait_for(
                        bot.wait_for(
                            "message",
                            check=lambda m: (
                                m.channel.id == text_channel.id and not m.author.bot
                            ),
                        ),
                        timeout=min(2.0, remaining),
                    )
                except asyncio.TimeoutError:
                    continue

                uid = str(msg.author.id)
                reacted = False

                if not artist_found_by and _check_guess(msg.content, song["artist"]):
                    artist_found_by = msg.author
                    scores[uid] = scores.get(uid, 0) + 1
                    reacted = True

                if not title_found_by and _check_guess(msg.content, song["title"]):
                    title_found_by = msg.author
                    scores[uid] = scores.get(uid, 0) + 1
                    reacted = True

                if reacted:
                    try:
                        await msg.add_reaction("✅")
                    except Exception:
                        pass

                    artist_text = (
                        f"✅ **{song['artist']}** *(par {artist_found_by.display_name})*"
                        if artist_found_by
                        else "❓"
                    )
                    title_text = (
                        f"✅ **{song['title']}** *(par {title_found_by.display_name})*"
                        if title_found_by
                        else "❓"
                    )
                    update_embed = discord.Embed(
                        title=f"🎵 Manche {round_num}/{nb_rounds}",
                        description=f"🎤 Artiste: {artist_text}\n🎵 Titre: {title_text}",
                        color=0x57F287
                        if (artist_found_by and title_found_by)
                        else 0x5865F2,
                    )
                    update_embed.set_footer(
                        text=f"⏱️ {int(end_time - time.monotonic())} secondes restantes"
                    )
                    try:
                        await round_msg.edit(embed=update_embed)
                    except Exception:
                        pass

                    if artist_found_by and title_found_by:
                        break

            # Arrête l'audio
            try:
                if voice_client.is_playing():
                    voice_client.stop()
            except Exception:
                pass

            # Embed de révélation
            reveal_embed = discord.Embed(
                title=f"🎵 Réponse — Manche {round_num}",
                description=(
                    f"🎤 **{song['artist']}**\n"
                    f"🎵 **{song['title']}**\n"
                    f"📅 {song.get('year', '?')}"
                ),
                color=0xFFD700,
            )
            if scores:
                sorted_sc = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                sc_text = "\n".join(
                    f"<@{uid}>: **{sc} pts**" for uid, sc in sorted_sc[:5]
                )
                reveal_embed.add_field(
                    name="📊 Scores actuels", value=sc_text, inline=False
                )
            else:
                reveal_embed.add_field(
                    name="📊 Scores", value="Personne n'a répondu 😅", inline=False
                )

            try:
                await round_msg.edit(embed=reveal_embed)
            except Exception:
                await text_channel.send(embed=reveal_embed)

            await asyncio.sleep(5)

    finally:
        # Nettoyage final — force pour éviter que la session reste "zombie"
        try:
            if voice_client.is_playing():
                voice_client.stop()
        except Exception:
            pass
        try:
            await voice_client.disconnect(force=True)
        except Exception:
            pass

        _active_sessions.pop(guild_id, None)

        # Résultats finaux
        if scores:
            medals = ["🥇", "🥈", "🥉"]
            sorted_sc = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            lines = [
                f"{medals[i] if i < 3 else '🎮'} <@{uid}>: **{sc} pts**"
                for i, (uid, sc) in enumerate(sorted_sc)
            ]
            final_embed = discord.Embed(
                title="🏆 Blindtest terminé ! Résultats finaux",
                description="\n".join(lines),
                color=0xFFD700,
            )
            final_embed.set_footer(text=f"{nb_rounds} manches jouées")
            winner = sorted_sc[0][0]
            final_embed.set_author(name=f"Vainqueur : 🥇 <voir mention>")
        else:
            final_embed = discord.Embed(
                title="🏁 Blindtest terminé !",
                description="Personne n'a marqué de point... 😅",
                color=0xED4245,
            )
            final_embed.set_footer(text=f"{nb_rounds} manches jouées")

        try:
            await text_channel.send(embed=final_embed)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class Blindtest(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    blindtest_group = app_commands.Group(
        name="blindtest",
        description="🎵 Système de blindtest musical en vocal",
    )

    # ------------------------------------------------------------------
    # /blindtest lancer
    # ------------------------------------------------------------------
    @blindtest_group.command(
        name="lancer",
        description="Lance un blindtest musical en vocal 🎵",
    )
    @app_commands.describe(
        theme="Thème musical (défaut: mix)",
        manches="Nombre de manches (1–20, défaut: 10)",
    )
    @app_commands.choices(
        theme=[
            app_commands.Choice(name="🕺 Années 80", value="80s"),
            app_commands.Choice(name="💿 Années 90", value="90s"),
            app_commands.Choice(name="🎵 Années 2000", value="2000s"),
            app_commands.Choice(name="🔥 Années 2010", value="2010s"),
            app_commands.Choice(name="✨ Années 2020", value="2020s"),
            app_commands.Choice(name="🎤 Rap FR", value="rap_fr"),
            app_commands.Choice(name="🎙️ Rap US", value="rap_us"),
            app_commands.Choice(name="🎸 Rock", value="rock"),
            app_commands.Choice(name="🎹 Pop", value="pop"),
            app_commands.Choice(name="🎮 Gaming OST", value="gaming"),
            app_commands.Choice(name="🌸 Anime", value="anime"),
            app_commands.Choice(name="🎲 Mix (tout)", value="mix"),
        ]
    )
    async def lancer(
        self,
        interaction: discord.Interaction,
        theme: str = "mix",
        manches: int = 10,
    ):
        guild_id = interaction.guild_id

        # Vérifie qu'il n'y a pas déjà une session
        if guild_id in _active_sessions:
            await interaction.response.send_message(
                embed=error_embed(
                    "Un blindtest est déjà en cours !",
                    "Utilise `/blindtest stop` pour l'arrêter d'abord.",
                ),
                ephemeral=True,
            )
            return

        # Vérifie que l'utilisateur est dans un vocal
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message(
                embed=error_embed(
                    "Tu n'es pas dans un salon vocal !",
                    "Rejoins un salon vocal avant de lancer le blindtest.",
                ),
                ephemeral=True,
            )
            return

        # Vérifie que yt-dlp est installé
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            await interaction.response.send_message(
                embed=error_embed(
                    "yt-dlp non installé !",
                    "Lance `pip install yt-dlp` puis redémarre le bot.",
                ),
                ephemeral=True,
            )
            return

        # Clampe le nombre de manches
        manches = max(1, min(20, manches))

        # Charge les chansons selon le thème
        if theme == "mix":
            from utils.blindtest_data import ALL_SONGS
            pool = ALL_SONGS.copy()
        else:
            from utils.blindtest_data import SONGS
            pool = SONGS.get(theme, []).copy()

        if not pool:
            await interaction.response.send_message(
                embed=error_embed("Aucune chanson disponible !", f"Thème `{theme}` vide."),
                ephemeral=True,
            )
            return

        # Mélange et sélectionne les chansons
        random.shuffle(pool)
        if len(pool) < manches:
            # On fait tourner en boucle si pas assez
            extended = pool * (manches // len(pool) + 1)
            random.shuffle(extended)
            songs = extended[:manches]
        else:
            songs = pool[:manches]

        # Connecte le bot au vocal — session 100% fraîche (fixe l'erreur 4006)
        voice_channel = interaction.user.voice.channel

        # Defer maintenant : les étapes suivantes (sleep + connect) dépassent les 3s
        await interaction.response.defer(ephemeral=True)

        try:
            # 1. Coupe le voice_client local s'il existe
            if interaction.guild.voice_client:
                try:
                    await interaction.guild.voice_client.disconnect(force=True)
                except Exception:
                    pass

            # 2. Force le gateway principal à dire à Discord "je quitte le vocal"
            #    Cela invalide côté Discord la session zombie, peu importe l'état local
            try:
                await interaction.guild._state.ws.voice_state(
                    interaction.guild.id, None, self_mute=False, self_deaf=True
                )
            except Exception:
                pass

            # 3. Attends que Discord traite la déconnexion
            await asyncio.sleep(2)

            # 4. Connexion fraîche
            voice_client = await voice_channel.connect(self_deaf=True)

        except Exception as e:
            await interaction.followup.send(
                embed=error_embed(
                    "Impossible de rejoindre le vocal !",
                    f"Erreur : {e}",
                ),
                ephemeral=True,
            )
            return

        # Enregistre la session
        _active_sessions[guild_id] = {
            "theme": theme,
            "manches": manches,
            "started_by": interaction.user.id,
            "started_at": time.time(),
        }

        theme_name = THEME_NAMES.get(theme, theme)
        await interaction.followup.send(
            embed=success_embed(
                f"Blindtest {theme_name} lancé !",
                f"**{manches} manches** dans {voice_channel.mention}\n"
                "Écrivez vos réponses dans ce salon !",
            )
        )

        # Lance la session en tâche de fond
        asyncio.create_task(
            _run_blindtest(
                self.bot,
                interaction.channel,
                voice_client,
                songs,
                manches,
                guild_id,
            )
        )

    # ------------------------------------------------------------------
    # /blindtest stop
    # ------------------------------------------------------------------
    @blindtest_group.command(
        name="stop",
        description="Arrête le blindtest en cours",
    )
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id

        if guild_id not in _active_sessions:
            await interaction.response.send_message(
                embed=error_embed("Aucun blindtest en cours !", ""),
                ephemeral=True,
            )
            return

        session = _active_sessions[guild_id]
        is_starter = interaction.user.id == session.get("started_by")
        is_admin = interaction.user.guild_permissions.manage_guild

        if not is_starter and not is_admin:
            await interaction.response.send_message(
                embed=error_embed(
                    "Permission refusée !",
                    "Seul celui qui a lancé le blindtest ou un admin peut l'arrêter.",
                ),
                ephemeral=True,
            )
            return

        # Supprime la session → la coroutine s'arrêtera à la prochaine itération
        _active_sessions.pop(guild_id, None)

        # Coupe l'audio et déconnecte proprement
        try:
            if interaction.guild.voice_client:
                if interaction.guild.voice_client.is_playing():
                    interaction.guild.voice_client.stop()
                await interaction.guild.voice_client.disconnect(force=True)
        except Exception:
            pass

        await interaction.response.send_message(
            embed=success_embed("Blindtest arrêté !", "À bientôt ! 🎵")
        )

    # ------------------------------------------------------------------
    # /blindtest skip
    # ------------------------------------------------------------------
    @blindtest_group.command(
        name="skip",
        description="Passe la manche actuelle",
    )
    async def skip(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id

        if guild_id not in _active_sessions:
            await interaction.response.send_message(
                embed=error_embed("Aucun blindtest en cours !", ""),
                ephemeral=True,
            )
            return

        session = _active_sessions[guild_id]
        is_starter = interaction.user.id == session.get("started_by")
        is_admin = interaction.user.guild_permissions.manage_guild

        if not is_starter and not is_admin:
            await interaction.response.send_message(
                embed=error_embed("Permission refusée !", ""),
                ephemeral=True,
            )
            return

        try:
            if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
                interaction.guild.voice_client.stop()
        except Exception:
            pass

        await interaction.response.send_message(
            embed=success_embed("Manche passée !", "⏭️"),
            ephemeral=True,
        )

    # ------------------------------------------------------------------
    # /blindtest themes
    # ------------------------------------------------------------------
    @blindtest_group.command(
        name="themes",
        description="Affiche tous les thèmes disponibles et leur nombre de chansons",
    )
    async def themes(self, interaction: discord.Interaction):
        from utils.blindtest_data import SONGS, ALL_SONGS

        lines = []
        for key, name in THEME_NAMES.items():
            if key == "mix":
                count = len(ALL_SONGS)
            else:
                count = len(SONGS.get(key, []))
            lines.append(f"{name} — **{count} chansons**")

        embed = discord.Embed(
            title="🎵 Thèmes disponibles",
            description="\n".join(lines),
            color=0x5865F2,
        )
        embed.set_footer(text="Lance /blindtest lancer [thème] [manches]")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Blindtest(bot))
