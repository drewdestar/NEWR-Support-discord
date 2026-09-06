/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'serverinfo',
    aliases: ['server-info', 'si', 'guild-info', 'info-server', 'check-server'],
    description: 'Get information about the server',
    usage: 'serverinfo',
    category: 'info',
    async execute(message, args, client) {
        const guild = message.guild;
        
        const channels = guild.channels.cache;
        const roles = guild.roles.cache;
        const emojis = guild.emojis.cache;
        const members = guild.members.cache;
        
        const embed = new EmbedBuilder()
            .setColor('#0099ff')
            .setTitle(`🏠 Server Info: ${guild.name}`)
            .setThumbnail(guild.iconURL({ dynamic: true, size: 256 }))
            .addFields(
                { name: 'Owner', value: `<@${guild.ownerId}>`, inline: true },
                { name: 'Created', value: `<t:${Math.floor(guild.createdTimestamp / 1000)}:R>`, inline: true },
                { name: 'Members', value: `${members.size}`, inline: true },
                { name: 'Channels', value: `${channels.size}`, inline: true },
                { name: 'Roles', value: `${roles.size}`, inline: true },
                { name: 'Emojis', value: `${emojis.size}`, inline: true },
                { name: 'Boost Level', value: `Level ${guild.premiumTier} (${guild.premiumSubscriptionCount || 0} boosts)`, inline: true },
                { name: 'Verification Level', value: guild.verificationLevel.toString(), inline: true }
            )
            .setDescription(`**ID:** ${guild.id}\n**Region:** ${guild.preferredLocale}`)
            .setFooter({ text: `© NEWROPLY - Developed by NEWR LABS | Requested by ${message.author.tag}` })
            .setTimestamp();
        
        message.reply({ embeds: [embed] });
    }
};
