import discord
from discord.ext import commands
from discord import app_commands
import datetime
from utils import db, automod
from utils.constants import ALL_GAMES, GAMES_BY_CATEGORY
from utils.embeds import error_embed, success_embed


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ─── Moderation Commands ──────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Avertir un membre")
    @app_commands.describe(member="Le membre à avertir", reason="La raison")
    @app_commands.default_permissions(manage_messages=True)
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Aucune raison fournie",
    ):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ Tu n'as pas la permission.", ephemeral=True
            )
            return

        guild_id = str(interaction.guild_id)
        user_id = str(member.id)
        count = automod.add_warning(guild_id, user_id, reason)

        embed = discord.Embed(
            title="⚠️ Avertissement",
            description=f"{member.mention} a reçu un avertissement.\n**Raison :** {reason}\n**Total avertissements :** {count}",
            color=0xFEE75C,
        )
        await interaction.response.send_message(embed=embed)

        try:
            dm_embed = discord.Embed(
                title=f"⚠️ Avertissement sur {interaction.guild.name}",
                description=f"**Raison :** {reason}\n**Total avertissements :** {count}",
                color=0xFEE75C,
            )
            await member.send(embed=dm_embed)
        except Exception:
            pass

    @app_commands.command(name="mute", description="Mettre en sourdine un membre")
    @app_commands.describe(
        member="Le membre à mute",
        duration="Durée en minutes (défaut: 10)",
        reason="La raison",
    )
    @app_commands.default_permissions(moderate_members=True)
    async def mute(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        duration: int = 10,
        reason: str = "Aucune raison fournie",
    ):
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                "❌ Tu n'as pas la permission.", ephemeral=True
            )
            return

        try:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
            await member.timeout(until, reason=reason)
            embed = discord.Embed(
                title="🔇 Mute",
                description=f"{member.mention} a été mis en sourdine pour **{duration} minutes**.\n**Raison :** {reason}",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed)

            try:
                dm_embed = discord.Embed(
                    title=f"🔇 Mute sur {interaction.guild.name}",
                    description=f"**Durée :** {duration} minutes\n**Raison :** {reason}",
                    color=0xED4245,
                )
                await member.send(embed=dm_embed)
            except Exception:
                pass

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Je n'ai pas la permission de mute ce membre.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erreur : {e}", ephemeral=True
            )

    @app_commands.command(name="kick", description="Expulser un membre")
    @app_commands.describe(member="Le membre à expulser", reason="La raison")
    @app_commands.default_permissions(kick_members=True)
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Aucune raison fournie",
    ):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message(
                "❌ Tu n'as pas la permission.", ephemeral=True
            )
            return

        try:
            dm_embed = discord.Embed(
                title=f"👢 Expulsé de {interaction.guild.name}",
                description=f"**Raison :** {reason}",
                color=0xED4245,
            )
            try:
                await member.send(embed=dm_embed)
            except Exception:
                pass

            await member.kick(reason=reason)
            embed = discord.Embed(
                title="👢 Expulsion",
                description=f"{member.mention} a été expulsé.\n**Raison :** {reason}",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Je n'ai pas la permission d'expulser ce membre.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erreur : {e}", ephemeral=True
            )

    @app_commands.command(name="ban", description="Bannir un membre")
    @app_commands.describe(member="Le membre à bannir", reason="La raison")
    @app_commands.default_permissions(ban_members=True)
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "Aucune raison fournie",
    ):
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                "❌ Tu n'as pas la permission.", ephemeral=True
            )
            return

        try:
            dm_embed = discord.Embed(
                title=f"🔨 Banni de {interaction.guild.name}",
                description=f"**Raison :** {reason}",
                color=0xED4245,
            )
            try:
                await member.send(embed=dm_embed)
            except Exception:
                pass

            await member.ban(reason=reason, delete_message_days=1)
            embed = discord.Embed(
                title="🔨 Ban",
                description=f"{member.mention} a été banni.\n**Raison :** {reason}",
                color=0xED4245,
            )
            await interaction.response.send_message(embed=embed)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ Je n'ai pas la permission de bannir ce membre.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Erreur : {e}", ephemeral=True
            )

    @app_commands.command(name="clearwarns", description="Effacer les avertissements d'un membre")
    @app_commands.describe(member="Le membre")
    @app_commands.default_permissions(manage_messages=True)
    async def clearwarns(
        self, interaction: discord.Interaction, member: discord.Member
    ):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ Tu n'as pas la permission.", ephemeral=True
            )
            return

        automod.clear_warnings(str(interaction.guild_id), str(member.id))
        await interaction.response.send_message(
            f"✅ Les avertissements de {member.mention} ont été effacés.", ephemeral=True
        )

    @app_commands.command(name="stats", description="Statistiques du serveur")
    async def stats(self, interaction: discord.Interaction):
        guild = interaction.guild
        bots = sum(1 for m in guild.members if m.bot)
        humans = guild.member_count - bots
        online = sum(
            1
            for m in guild.members
            if m.status != discord.Status.offline and not m.bot
        )
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles = len(guild.roles) - 1  # exclude @everyone

        embed = discord.Embed(
            title=f"📊 Statistiques — {guild.name}",
            color=0x5865F2,
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="👥 Membres", value=f"**{guild.member_count}**", inline=True)
        embed.add_field(name="👤 Humains", value=f"**{humans}**", inline=True)
        embed.add_field(name="🤖 Bots", value=f"**{bots}**", inline=True)
        embed.add_field(name="🟢 En ligne", value=f"**{online}**", inline=True)
        embed.add_field(name="💬 Salons texte", value=f"**{text_channels}**", inline=True)
        embed.add_field(name="🔊 Salons voix", value=f"**{voice_channels}**", inline=True)
        embed.add_field(name="🎭 Rôles", value=f"**{roles}**", inline=True)
        embed.add_field(
            name="📅 Créé le",
            value=f"<t:{int(guild.created_at.timestamp())}:D>",
            inline=True,
        )
        embed.add_field(name="👑 Propriétaire", value=guild.owner.mention if guild.owner else "Inconnu", inline=True)
        await interaction.response.send_message(embed=embed)

    # ─── /setup ───────────────────────────────────────────────────────────────

    @app_commands.command(name="setup", description="Configurer le serveur (owner/admin uniquement)")
    @app_commands.default_permissions(administrator=True)
    async def setup(self, interaction: discord.Interaction):
        if (
            interaction.user.id != interaction.guild.owner_id
            and not interaction.user.guild_permissions.administrator
        ):
            await interaction.response.send_message(
                "❌ Seul le propriétaire ou un administrateur peut utiliser cette commande.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        try:
            status_lines = []

            # ── 1. Create Roles ──────────────────────────────────────────────
            status_lines.append("⏳ Création des rôles...")
            await interaction.followup.send("\n".join(status_lines), ephemeral=True)

            def find_role(name: str):
                return discord.utils.get(guild.roles, name=name)

            async def get_or_create_role(name: str, **kwargs):
                r = find_role(name)
                if r:
                    return r
                return await guild.create_role(name=name, **kwargs)

            role_en_attente = await get_or_create_role(
                "⏳ En attente", color=discord.Color.greyple()
            )
            role_membre = await get_or_create_role(
                "⭐ Membre", color=discord.Color.blue()
            )
            role_moderateur = await get_or_create_role(
                "🛡️ Modérateur", color=discord.Color.orange()
            )
            role_streamer = await get_or_create_role(
                "🎙️ Streamer", color=discord.Color.purple()
            )

            # Game roles
            game_roles: dict = {}
            for game in ALL_GAMES:
                role_name = f"🎮 {game['label']}"
                r = await get_or_create_role(role_name, color=discord.Color.dark_gray())
                game_roles[game["id"]] = str(r.id)

            status_lines[-1] = "✅ Rôles créés."

            # ── 2. Create Channel Structure ──────────────────────────────────
            status_lines.append("⏳ Création des catégories et salons...")
            await interaction.edit_original_response(content="\n".join(status_lines))

            # Helper permissions
            no_view = discord.PermissionOverwrite(view_channel=False)
            read_no_send = discord.PermissionOverwrite(
                view_channel=True, send_messages=False, read_message_history=True
            )
            full_access = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )
            mod_access = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
            )

            everyone = guild.default_role

            # --- Category: 📢 INFORMATIONS ---
            cat_info = discord.utils.get(guild.categories, name="📢 INFORMATIONS")
            if not cat_info:
                cat_info = await guild.create_category(
                    "📢 INFORMATIONS",
                    overwrites={everyone: no_view, role_membre: read_no_send},
                )

            def find_or_none(name):
                return discord.utils.get(guild.text_channels, name=name)

            async def get_or_create_text(name, category, **kwargs):
                ch = find_or_none(name)
                if ch:
                    return ch
                return await guild.create_text_channel(name, category=category, **kwargs)

            ch_reglement = await get_or_create_text(
                "règlement",
                cat_info,
                overwrites={
                    everyone: discord.PermissionOverwrite(
                        view_channel=True, send_messages=False, read_message_history=True
                    )
                },
            )
            ch_annonces = await get_or_create_text(
                "annonces",
                cat_info,
                overwrites={
                    everyone: discord.PermissionOverwrite(
                        view_channel=True, send_messages=False, read_message_history=True
                    )
                },
            )
            ch_updates = await get_or_create_text(
                "mises-à-jour",
                cat_info,
                overwrites={
                    everyone: discord.PermissionOverwrite(
                        view_channel=True, send_messages=False, read_message_history=True
                    )
                },
            )

            # --- Category: 🎮 GÉNÉRAL ---
            cat_general = discord.utils.get(guild.categories, name="🎮 GÉNÉRAL")
            if not cat_general:
                cat_general = await guild.create_category(
                    "🎮 GÉNÉRAL",
                    overwrites={everyone: no_view, role_membre: full_access},
                )

            ch_general = await get_or_create_text("général", cat_general)
            ch_hors_sujet = await get_or_create_text("hors-sujet", cat_general)
            ch_memes = await get_or_create_text("memes", cat_general)
            ch_suggestions = await get_or_create_text("suggestions", cat_general)
            ch_bot_commands = await get_or_create_text("bot-commands", cat_general)

            # --- Category: 🎯 GAMING ---
            cat_gaming = discord.utils.get(guild.categories, name="🎯 GAMING")
            if not cat_gaming:
                cat_gaming = await guild.create_category(
                    "🎯 GAMING",
                    overwrites={everyone: no_view, role_membre: full_access},
                )

            ch_choix_jeux = await get_or_create_text("choix-de-jeux", cat_gaming)
            ch_recherche = await get_or_create_text("recherche-de-joueurs", cat_gaming)
            ch_clips = await get_or_create_text("clips", cat_gaming)
            ch_events = await get_or_create_text("events-gaming", cat_gaming)

            # --- Category: 🎫 SUPPORT ---
            cat_support = discord.utils.get(guild.categories, name="🎫 SUPPORT")
            if not cat_support:
                cat_support = await guild.create_category(
                    "🎫 SUPPORT",
                    overwrites={
                        everyone: discord.PermissionOverwrite(
                            view_channel=True, send_messages=False
                        )
                    },
                )

            ch_ticket = await get_or_create_text("open-ticket", cat_support)

            # --- Category: 📺 STREAM ---
            cat_stream = discord.utils.get(guild.categories, name="📺 STREAM")
            if not cat_stream:
                cat_stream = await guild.create_category(
                    "📺 STREAM",
                    overwrites={everyone: no_view, role_membre: full_access},
                )

            ch_stream_ann = await get_or_create_text("stream-annonces", cat_stream)
            ch_self_promo = await get_or_create_text("self-promo", cat_stream)

            # --- Category: 📊 LOGS ---
            cat_logs = discord.utils.get(guild.categories, name="📊 LOGS")
            if not cat_logs:
                cat_logs = await guild.create_category(
                    "📊 LOGS",
                    overwrites={everyone: no_view, role_moderateur: mod_access},
                )

            ch_mod_logs = await get_or_create_text(
                "mod-logs",
                cat_logs,
                overwrites={
                    everyone: no_view,
                    role_moderateur: mod_access,
                    guild.me: mod_access,
                },
            )
            ch_stats = await get_or_create_text(
                "stats-serveur",
                cat_logs,
                overwrites={everyone: no_view, role_moderateur: mod_access},
            )

            # --- Category: 🔊 VOCAUX ---
            cat_voice = discord.utils.get(guild.categories, name="🔊 VOCAUX")
            if not cat_voice:
                cat_voice = await guild.create_category(
                    "🔊 VOCAUX",
                    overwrites={everyone: no_view, role_membre: full_access},
                )

            async def get_or_create_voice(name, category):
                vc = discord.utils.get(guild.voice_channels, name=name)
                if vc:
                    return vc
                return await guild.create_voice_channel(name, category=category)

            vc_general = await get_or_create_voice("🎮 Général", cat_voice)
            vc_stream = await get_or_create_voice("🎙️ Stream Room", cat_voice)
            vc_afk = await get_or_create_voice("📞 AFK", cat_voice)

            # Set AFK channel
            try:
                await guild.edit(afk_channel=vc_afk, afk_timeout=300)
            except Exception:
                pass

            status_lines[-1] = "✅ Catégories et salons créés."

            # ── 3. Post content in channels ──────────────────────────────────
            status_lines.append("⏳ Publication du règlement et des panneaux...")
            await interaction.edit_original_response(content="\n".join(status_lines))

            # Post rules embed in #règlement
            from views.rules_view import RulesView
            from utils.embeds import rules_embed
            from utils.i18n import TRANSLATIONS

            # Clear old pins in rules channel
            async for msg in ch_reglement.history(limit=10):
                if msg.author == guild.me:
                    try:
                        await msg.delete()
                    except Exception:
                        pass

            rules_body_fr = TRANSLATIONS["fr"]["rules"]["body"]
            r_embed = rules_embed("fr", guild.name, rules_body_fr)
            await ch_reglement.send(embed=r_embed, view=RulesView())

            # Post game selection in #choix-de-jeux
            from views.games_view import GamesSelectView

            async for msg in ch_choix_jeux.history(limit=20):
                if msg.author == guild.me:
                    try:
                        await msg.delete()
                    except Exception:
                        pass

            categories_list = list(GAMES_BY_CATEGORY.items())
            chunk_size = 5
            for chunk_start in range(0, len(categories_list), chunk_size):
                chunk = categories_list[chunk_start:chunk_start + chunk_size]
                cat_names = " / ".join(cat for cat, _ in chunk)
                g_embed = discord.Embed(
                    title=f"🎮 Choix de jeux — {cat_names}",
                    description="Sélectionne tes jeux pour obtenir les rôles correspondants.",
                    color=0x5865F2,
                )
                view = GamesSelectView(chunk, start_index=chunk_start)
                await ch_choix_jeux.send(embed=g_embed, view=view)

            # Post ticket panel in #open-ticket
            from views.ticket_view import TicketPanel

            async for msg in ch_ticket.history(limit=10):
                if msg.author == guild.me:
                    try:
                        await msg.delete()
                    except Exception:
                        pass

            t_embed = discord.Embed(
                title="🎫 Support & Tickets",
                description=(
                    "Besoin d'aide ? Clique sur le bouton ci-dessous pour ouvrir un ticket privé.\n"
                    "Un membre du staff te répondra dès que possible."
                ),
                color=0x5865F2,
            )
            await ch_ticket.send(embed=t_embed, view=TicketPanel())

            status_lines[-1] = "✅ Panneaux publiés."

            # ── 4. Save config ────────────────────────────────────────────────
            config_data = db.load("config")
            config_data[str(guild.id)] = {
                "lang": "fr",
                "channels": {
                    "reglement": str(ch_reglement.id),
                    "annonces": str(ch_annonces.id),
                    "updates": str(ch_updates.id),
                    "general": str(ch_general.id),
                    "hors_sujet": str(ch_hors_sujet.id),
                    "memes": str(ch_memes.id),
                    "suggestions": str(ch_suggestions.id),
                    "bot_commands": str(ch_bot_commands.id),
                    "choix_jeux": str(ch_choix_jeux.id),
                    "recherche": str(ch_recherche.id),
                    "clips": str(ch_clips.id),
                    "events_gaming": str(ch_events.id),
                    "open_ticket": str(ch_ticket.id),
                    "stream_annonces": str(ch_stream_ann.id),
                    "self_promo": str(ch_self_promo.id),
                    "mod_logs": str(ch_mod_logs.id),
                    "stats_serveur": str(ch_stats.id),
                },
                "roles": {
                    "en_attente": str(role_en_attente.id),
                    "membre": str(role_membre.id),
                    "moderateur": str(role_moderateur.id),
                    "streamer": str(role_streamer.id),
                },
                "game_roles": game_roles,
                "voice": {
                    "general": str(vc_general.id),
                    "stream": str(vc_stream.id),
                    "afk": str(vc_afk.id),
                },
            }
            db.save("config", config_data)

            status_lines.append("✅ **Configuration sauvegardée ! Le serveur est prêt.**")
            await interaction.edit_original_response(content="\n".join(status_lines))

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            await interaction.edit_original_response(
                content=f"❌ Erreur lors de la configuration :\n```\n{e}\n{tb[:800]}\n```"
            )

    # ─── Event Listeners ──────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = str(member.guild.id)
        config = db.load("config").get(guild_id, {})

        # Give En attente role
        en_attente_id = config.get("roles", {}).get("en_attente")
        if en_attente_id:
            role = member.guild.get_role(int(en_attente_id))
            if role:
                try:
                    await member.add_roles(role, reason="Nouveau membre")
                except Exception:
                    pass

        # Welcome in general channel
        general_id = config.get("channels", {}).get("general")
        reglement_id = config.get("channels", {}).get("reglement")
        if general_id:
            channel = member.guild.get_channel(int(general_id))
            if channel:
                reglement_mention = f"<#{reglement_id}>" if reglement_id else "#règlement"
                embed = discord.Embed(
                    title=f"👋 Bienvenue, {member.display_name} !",
                    description=(
                        f"Bienvenue sur **{member.guild.name}** ! 🎮\n\n"
                        f"Va lire le règlement dans {reglement_mention} pour accéder au serveur.\n"
                        f"**Tu es notre {member.guild.member_count}ème membre !**"
                    ),
                    color=0x57F287,
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass

        # Send welcome DM
        try:
            embed = discord.Embed(
                title=f"👋 Bienvenue sur {member.guild.name} !",
                description="Lis le **règlement** et clique sur **Accepter** pour accéder au serveur. À bientôt !",
                color=0x5865F2,
            )
            await member.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_id = str(message.guild.id)
        user_id = str(message.author.id)

        # XP gain
        from utils import xp_system
        result = xp_system.add_xp(guild_id, user_id)
        if result["leveled"]:
            embed = discord.Embed(
                description=(
                    f"🎉 Félicitations {message.author.mention} ! "
                    f"Tu passes au niveau **{result['new_level']}** ! "
                    f"(+{result['new_level'] * 50} 🪙)"
                ),
                color=0xFFD700,
            )
            try:
                leveling_channel = message.guild.get_channel(1485084861101375498)
                target = leveling_channel or message.channel
                await target.send(embed=embed)
            except Exception:
                pass

        # Automod - skip mods
        member = message.guild.get_member(message.author.id)
        if member and not member.guild_permissions.manage_messages:
            from utils import automod
            if automod.check_spam(guild_id, user_id):
                await automod.handle_violation(message, "Spam détecté")
                return
            elif automod.check_bad_words(message.content):
                await automod.handle_violation(message, "Langage inapproprié")
                return
            elif automod.check_mass_mentions(message):
                await automod.handle_violation(message, "Mentions en masse")
                return
            elif automod.check_invite_link(message.content):
                await automod.handle_violation(message, "Lien d'invitation non autorisé")
                return

        # FAQ auto-responses
        content_lower = message.content.lower()
        if any(
            k in content_lower
            for k in ["comment avoir un rôle", "comment avoir un role", "how to get a role"]
        ):
            try:
                await message.reply(
                    "🎮 Va dans **#choix-de-jeux** pour obtenir tes rôles de jeux !",
                    delete_after=10,
                    mention_author=False,
                )
            except Exception:
                pass
        elif any(
            k in content_lower
            for k in ["comment ouvrir un ticket", "how to open a ticket"]
        ):
            try:
                await message.reply(
                    "🎫 Va dans **#open-ticket** et clique sur le bouton !",
                    delete_after=10,
                    mention_author=False,
                )
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if not before.channel:
            return

        rooms_data = db.load("rooms")
        guild_id = str(member.guild.id)
        guild_rooms = rooms_data.get(guild_id, {})

        voice_channel = before.channel
        voice_id = str(voice_channel.id)

        for room_id, room in list(guild_rooms.items()):
            if room.get("voice_id") == voice_id:
                if len(voice_channel.members) == 0:
                    try:
                        await voice_channel.delete(reason="Room vide - auto-suppression")
                    except Exception:
                        pass
                    text_id = room.get("text_id")
                    if text_id:
                        text_channel = member.guild.get_channel(int(text_id))
                        if text_channel:
                            try:
                                await text_channel.delete(reason="Room vide - auto-suppression")
                            except Exception:
                                pass
                    del guild_rooms[room_id]
                    rooms_data[guild_id] = guild_rooms
                    db.save("rooms", rooms_data)
                break


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
