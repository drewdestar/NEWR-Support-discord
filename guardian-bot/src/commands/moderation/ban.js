/**
 * Ban Command - Moderation System
 * 
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY is the parent company (like Meta)
 * NEWR LABS is the development studio/brand (like Instagram under Meta)
 * ────────────────────────────────────────────────────────
 * 
 * Author: NEWR LABS Moderation Team
 * Company: NEWROPLY
 * License: Proprietary - NEWROPLY
 * 
 * ⚠️ This command is property of NEWROPLY.
 * Unauthorized use is strictly prohibited.
 * ────────────────────────────────────────────────────────
 */

const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'ban',
    aliases: ['band'],
    description: 'Ban a user from the server',
    usage: 'ban @user [reason]',
    category: 'moderation',
    permissions: ['BAN_MEMBERS'],
    botPermissions: ['BAN_MEMBERS'],
    
    async execute(message, args, client) {
        const lang = await global.db.get('SELECT language FROM guilds WHERE guild_id = ?', [message.guild.id]) || global.config.defaultLanguage;
        
        if (!message.member.permissions.has('BAN_MEMBERS')) {
            return message.reply(global.lang.get(lang, 'general.permissionDenied'));
        }
        
        const user = message.mentions.users.first();
        if (!user) {
            return message.reply(`Usage: \`${global.config.prefix}ban @user [reason]\``);
        }
        
        const member = message.guild.members.resolve(user);
        if (!member) {
            return message.reply('User not found!');
        }
        
        if (member.id === message.author.id) {
            return message.reply("You can't ban yourself!");
        }
        
        if (member.roles.highest.position >= message.member.roles.highest.position) {
            return message.reply("You can't ban someone with equal or higher role!");
        }
        
        if (!member.bannable) {
            return message.reply("I can't ban this user!");
        }
        
        const reason = args.slice(1).join(' ') || 'No reason provided';
        
        try {
            await member.ban({ reason: `${reason} | Moderator: ${message.author.tag}` });
            
            const embed = new EmbedBuilder()
                .setColor('#ff0000')
                .setTitle('🔨 User Banned')
                .addFields(
                    { name: 'User', value: `${user.tag} (${user.id})`, inline: true },
                    { name: 'Moderator', value: `${message.author.tag}`, inline: true },
                    { name: 'Reason', value: reason, inline: false }
                )
                .setFooter({ text: `ID: ${user.id}` })
                .setTimestamp();
            
            await message.channel.send({ embeds: [embed] });
            
            // Log to database
            await global.db.run(
                'INSERT INTO mod_logs (guild_id, user_id, moderator_id, action, reason) VALUES (?, ?, ?, ?, ?)',
                [message.guild.id, user.id, message.author.id, 'ban', reason]
            );
            
            // Log to channel if set
            const logChannel = await global.db.get('SELECT log_channel FROM guilds WHERE guild_id = ?', [message.guild.id]);
            if (logChannel?.log_channel) {
                const logChan = message.guild.channels.cache.get(logChannel.log_channel);
                if (logChan) {
                    await logChan.send({ embeds: [embed] });
                }
            }
            
        } catch (error) {
            console.error('Ban error:', error);
            message.reply('Failed to ban user!');
        }
    }
};
