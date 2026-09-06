/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'userinfo',
    aliases: ['user-info', 'ui', 'whois', 'profile', 'member-info', 'check-user'],
    description: 'Get information about a user',
    usage: 'userinfo [@user]',
    category: 'info',
    async execute(message, args, client) {
        const mentionedUser = message.mentions.users.first() || message.author;
        const member = message.guild.members.cache.get(mentionedUser.id);
        
        if (!member) {
            return message.reply('User not found in this server.');
        }
        
        const roles = member.roles.cache
            .filter(r => r.id !== message.guild.id)
            .sort((a, b) => b.position - a.position)
            .map(r => r.name)
            .slice(0, 10)
            .join(', ') || 'None';
        
        const embed = new EmbedBuilder()
            .setColor(member.displayHexColor || '#0099ff')
            .setTitle(`👤 User Info: ${mentionedUser.tag}`)
            .setThumbnail(mentionedUser.displayAvatarURL({ dynamic: true, size: 256 }))
            .addFields(
                { name: 'ID', value: mentionedUser.id, inline: true },
                { name: 'Nickname', value: member.nickname || 'None', inline: true },
                { name: 'Joined Discord', value: `<t:${Math.floor(mentionedUser.createdTimestamp / 1000)}:R>`, inline: true },
                { name: 'Joined Server', value: `<t:${Math.floor(member.joinedTimestamp / 1000)}:R>`, inline: true },
                { name: 'Roles', value: roles, inline: false },
                { name: 'Highest Role', value: member.roles.highest.name, inline: true },
                { name: 'Is Bot?', value: mentionedUser.bot ? '✅ Yes' : '❌ No', inline: true }
            )
            .setFooter({ text: `© NEWROPLY - Developed by NEWR LABS | Requested by ${message.author.tag}` })
            .setTimestamp();
        
        message.reply({ embeds: [embed] });
    }
};
