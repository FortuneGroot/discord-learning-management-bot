from __future__ import annotations

import discord

from ffcu.services.permissions import StaffAccess, access_level, allowed


def interaction_access(interaction: discord.Interaction) -> StaffAccess:
    member = interaction.user
    role_ids = [role.id for role in member.roles] if isinstance(member, discord.Member) else []
    administrator_permission = bool(
        isinstance(member, discord.Member) and member.guild_permissions.administrator
    )
    settings = interaction.client.settings
    return access_level(
        role_ids,
        admin_role_id=settings.admin_role_id,
        professor_role_id=settings.professor_role_id,
        mentor_role_id=settings.mentor_role_id,
        administrator_permission=administrator_permission,
    )


async def require_access(interaction: discord.Interaction, required: StaffAccess) -> bool:
    if allowed(interaction_access(interaction), required):
        return True
    await interaction.response.send_message("You do not have permission to use this staff command.", ephemeral=True)
    return False
