/**
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * ────────────────────────────────────────────────────────
 */

const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'ban',
    aliases: ['ban-user', 'user-ban', 'remove', 'kick-permanent', 'exclude'],
    description: 'Ban a user from the server',
    usage: 'ban @user <reason>',
    category: 'moderation',
    async execute(message, args, client) {
        if (!message.member.permissions.has('BAN_MEMBERS')) {
            return message.reply('❌ You do not have permission to ban users.');
        }
        
        const mentionedUser = message.mentions.users.first();
        const reason = args.slice(1).join(' ') || 'No reason provided';
        
        if (!mentionedUser) {
            return message.reply('Usage: `ban @user <reason>`');
        }
        
        const member = message.guild.members.cache.get(mentionedUser.id);
        
        if (!member) {
            return message.reply('User not found in this server.');
        }
        
        if (!member.bannable) {
            return message.reply('I cannot ban this user (they might have higher permissions).');
        }
        
        try {
            await member.ban({ reason: `${message.author.tag}: ${reason}` });
            
            const embed = new EmbedBuilder()
                .setColor('#ff0000')
                .setTitle('🔨 User Banned')
                .addFields(
                    { name: 'User', value: `${mentionedUser.tag} (${mentionedUser.id})`, inline: true },
                    { name: 'Moderator', value: message.author.tag, inline: true },
                    { name: 'Reason', value: reason, inline: false }
                )
                .setFooter({ text: '© NEWROPLY - Developed by NEWR LABS' })
                .setTimestamp();
            
            message.reply({ embeds: [embed] });
            
            // Log to database
            const db = require('../../handlers/database');
            db.run('INSERT INTO mod_logs (guild_id, action, user_id, moderator, reason) VALUES (?, ?, ?, ?, ?)',
                [message.guild.id, 'ban', mentionedUser.id, message.author.id, reason]);
                
        } catch (error) {
            console.error('[NEWR LABS] Ban error:', error);
            message.reply('Failed to ban the user.');
        }
    }
};
