/**
 * Message Create Event Handler
 * 
 * ────────────────────────────────────────────────────────
 * © COPYRIGHT NEWROPLY - ALL RIGHTS RESERVED
 * Developed by NEWR LABS
 * 
 * NEWROPLY is the parent company (like Meta)
 * NEWR LABS is the development studio/brand (like Instagram under Meta)
 * ────────────────────────────────────────────────────────
 * 
 * Author: NEWR LABS Events Team
 * Company: NEWROPLY
 * License: Proprietary - NEWROPLY
 * 
 * ⚠️ This event handler is property of NEWROPLY.
 * Unauthorized use is strictly prohibited.
 * ────────────────────────────────────────────────────────
 */

const { EmbedBuilder } = require('discord.js');

module.exports = {
    name: 'messageCreate',
    once: false,
    async execute(message, client) {
        if (!message.guild || message.author.bot) return;
        
        const prefix = (await global.db.get('SELECT prefix FROM guilds WHERE guild_id = ?', [message.guild.id]))?.prefix || global.config.prefix;
        
        if (!message.content.startsWith(prefix)) return;
        
        const args = message.content.slice(prefix.length).trim().split(/ +/);
        const commandName = args.shift().toLowerCase();
        
        const command = client.commands.get(commandName) || [...client.commands].find(([_, cmd]) => cmd.aliases?.includes(commandName))?.[1];
        
        if (!command) return;
        
        // Check permissions
        if (command.permissions && !message.member.permissions.has(command.permissions)) {
            return message.reply('❌ You don\'t have permission to use this command!');
        }
        
        if (command.botPermissions && !message.guild.members.me.permissions.has(command.botPermissions)) {
            return message.reply('❌ I don\'t have permission to execute this command!');
        }
        
        // Cooldown check
        if (!client.cooldowns.has(command.name)) {
            client.cooldowns.set(command.name, new Map());
        }
        
        const now = Date.now();
        const timestamps = client.cooldowns.get(command.name);
        const cooldownAmount = (command.cooldown || 3) * 1000;
        
        if (timestamps.has(message.author.id)) {
            const expirationTime = timestamps.get(message.author.id) + cooldownAmount;
            if (now < expirationTime) {
                const timeLeft = (expirationTime - now) / 1000;
                return message.reply(`Please wait ${timeLeft.toFixed(1)} seconds!`);
            }
        }
        
        timestamps.set(message.author.id, now);
        setTimeout(() => timestamps.delete(message.author.id), cooldownAmount);
        
        try {
            await command.execute(message, args, client);
        } catch (error) {
            console.error(`Command error (${command.name}):`, error);
            message.reply('❌ An error occurred while executing this command!');
        }
    }
};
